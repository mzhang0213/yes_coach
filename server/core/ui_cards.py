"""UI-card seam — game-specific overlay compositions on the generic toolkit.

The generic Overlay owns primitive draws (rectangles, text, circles, buttons).
A game's `UICards` composes those primitives into game-specific cards (e.g. a
rune card) and returns any `ActionZone`s — hover-fill hitboxes the controller
drives and fires on completion. This keeps all game knowledge out of the view.
"""

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class ActionZone:
    box: tuple                                    # (x1, y1, x2, y2) hit-test rect
    fill_key: str                                 # OverlayUIState attr for the bloom
    on_complete: Callable[[], None]               # fired on full hover-fill
    guard: Callable[[], bool] = lambda: True      # only interactive while True


class UICards(Protocol):
    def phase_label(self, phase: str) -> str: ...
    def draw_pregame(self, overlay, session) -> list: ...   # -> list[ActionZone]
    def draw_ingame(self, overlay, session) -> list: ...    # -> list[ActionZone]
