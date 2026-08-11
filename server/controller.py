"""Controller layer — input handling and state transitions.

Reads user input (cursor position, prompt submissions), drives the overlay
state machine, and mutates the model. Asks the view to render each frame, then
hit-tests the geometry the view reports back.
"""
import os
import threading

import pyautogui

from server.model import OverlayModel
from server.resources.riot import *
from server.view import PromptWindow



class OverlayController:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self.prompt_window = None
        # Gemini coach: built lazily on a worker thread, guarded (see _get_coach)
        self._coach = None
        self._coach_failed = False
        self._coach_lock = threading.Lock()

    @staticmethod
    def _in_box(x, y, box):
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def run_prompt(self):
        return

    def show_prompt_window(self):
        if self.prompt_window and self.prompt_window.isVisible():
            return

        def on_submit(text):
            self.model.user_question = text
            print(f"User question: {text}")
            # TODO: pass to gemini coach

        self.prompt_window = PromptWindow(callback=on_submit)
        self.prompt_window.show()

    def _get_coach(self):
        """Build the Gemini coach once, thread-safe. Returns None if unavailable.

        Import is deferred here (not at module load) so a missing/broken Gemini
        SDK degrades to status-only instead of crashing startup. A failure is
        latched so we don't re-attempt disk/network I/O on every checkpoint.
        """
        with self._coach_lock:
            if self._coach is None and not self._coach_failed:
                keys = [v for k, v in os.environ.items() if k.startswith("GEMINI_API_KEY")]
                if not keys:
                    self._coach_failed = True
                else:
                    try:
                        from server.resources.gemini import LoLCoach
                        self._coach = LoLCoach(api_keys=keys)
                    except Exception as e:
                        print(f"[coach] init failed: {e}")
                        self._coach_failed = True
            return self._coach

    def _run_coach(self, cp):
        """Worker body: fetch event advice off the main thread and marshal it
        back onto the model (plain attribute writes only — no Qt from here)."""
        coach = self._get_coach()
        if coach is None:
            return
        try:
            result = coach.get_advice(schema_key="event")
        except Exception as e:
            print(f"[coach] advice failed: {e}")
            return
        game = self.model.game
        game.advice = result
        reaction = result.get("reaction") if isinstance(result, dict) else None
        game.status = f"{cp.title} — {reaction}" if reaction else f"Checkpoint: {cp.title}"

    def update_game_state(self, model: OverlayModel):
        #read state from Riot API at curr time (RN) and log in memory
        try:
            stats = get_game_stats()
            events = get_event_data()
        except Exception:
            return  # no live game / client unreachable — keep prior state

        snap = model.game.ingest(stats, events)
        for cp in model.game.evaluate_checkpoints(snap):
            # show the hit immediately; the coach thread refines the text later
            model.game.status = f"Checkpoint: {cp.title}"
            threading.Thread(target=self._run_coach, args=(cp,), daemon=True).start()

    def tick(self):
        m = self.model

        self.update_game_state(m)

        geom = self.view.render(m)
        if not geom:
            return

        mx, my = pyautogui.position()
        hover = {
            'main': self._in_box(mx, my, geom['main']),
            'left': [self._in_box(mx, my, lb) for lb in geom['left']],
            'right': geom['right'] is not None and self._in_box(mx, my, geom['right']),
        }

        # view advances its own button animations + state machine and reports
        # any button that crossed its activation threshold this frame
        press = self.view.advance(hover)
        if press:
            m.record_press(press)
            if press == 'right':
                self.show_prompt_window()
            # elif press.startswith('left:'):
            #     TODO: trigger the corresponding quick action
