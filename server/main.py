import os
import sys

import cv2 as cv
from PyQt6.QtCore import QTimer

from server.utils import app, stop_screen_capture, screen_capture
from server.model import OverlayModel, GameSession
from server.view import OverlayView, ButtonPlacer
from server.controller import OverlayController
from server.core import registry
from server.core.coach import GeminiCoach
from server.core.snapshot_store import SnapshotStore
from server.core.adapter import Services


def _select_adapter():
    """Pick the active game: env override → auto-detect → default 'lol'."""
    registry.discover()
    name = os.environ.get("YESCOACH_GAME")
    if name:
        return registry.get(name)
    return registry.active() or registry.get("lol")


def _build_coach(profile):
    """Instantiate the coach from GEMINI_API_KEY* env vars, or None if unset."""
    keys = [v for k, v in os.environ.items() if k.startswith("GEMINI_API_KEY")]
    if not keys:
        print("No GEMINI_API_KEY* set — coaching disabled, data pipeline only.")
        return None
    try:
        return GeminiCoach(api_keys=keys, profile=profile)
    except Exception as e:
        print(f"Coach init failed ({e}) — continuing without coaching.")
        return None


adapter = _select_adapter()
print(f"Active game: {adapter.display_name}")

model = OverlayModel(tab_labels=[t.label for t in adapter.tab_actions()])
session = GameSession(model=model, game=adapter.new_state())

view = OverlayView()
coach = _build_coach(adapter.coach_profile())
controller = OverlayController(session, view, adapter, coach=coach)

# Background services + the game's data sources (built by the adapter).
store = SnapshotStore()
services = Services(store=store, coach=coach)
sources = adapter.data_sources(session, services)

screen_capture()   # start frame grabber for vision (no-op data if unpermitted)
for src in sources:
    src.start()

model.button_pos = ButtonPlacer().pick()

# QTimer fires tick() every 16ms (~60fps) on the main thread inside app.exec()
timer = QTimer()
timer.timeout.connect(controller.tick)
timer.start(16)

try:
    sys.exit(app.exec())
except KeyboardInterrupt:
    print("\nStopping...")
    for src in sources:
        src.stop()
    stop_screen_capture()
    store.close()
    cv.destroyAllWindows()
