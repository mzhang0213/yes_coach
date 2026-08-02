"""Controller layer — input handling and state transitions.

Reads user input (cursor, prompt submissions), drives the generic overlay state
machine, and mutates the session's UI state. Asks the view to render each frame,
then hit-tests the geometry the view reports back. Game-specific behaviour — tab
intents, the on-demand advice payload, and action-zone actions — comes from the
injected adapter, so the controller has no game knowledge.
"""
import threading

import pyautogui

from server.view import PromptWindow


class OverlayController:
    def __init__(self, session, view, adapter, coach=None):
        self.session = session
        self.view = view
        self.adapter = adapter
        self.coach = coach
        self.cards = adapter.ui_cards()
        self.tabs = adapter.tab_actions()
        self.prompt_window = None

    @staticmethod
    def _in_box(x, y, box):
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def _run_advice(self, question=None, schema_key="situation"):
        """Ask the coach off the UI thread and stash the result on the session."""
        if not self.coach:
            print("Coach unavailable (no API key configured).")
            return

        def worker():
            advice = self.coach.get_advice(
                question=question, schema_key=schema_key,
                state=self.adapter.current_state(self.session),
                extra=self.adapter.current_extra(self.session))
            self.session.model.last_advice = advice
            self.session.model.pending_suggestion = {"title": question or "Live advice",
                                                  "advice": advice}
            print(f"[advice] {question or schema_key} -> {advice}")

        threading.Thread(target=worker, daemon=True).start()

    def run_prompt(self):
        """Trigger live situational advice for the current state."""
        self._run_advice(schema_key="situation")

    def _run_tab(self, index: int):
        if 0 <= index < len(self.tabs):
            tab = self.tabs[index]
            self._run_advice(question=tab.question, schema_key=tab.schema_key)

    def show_prompt_window(self):
        if self.prompt_window and self.prompt_window.isVisible():
            return

        def on_submit(text):
            self.session.model.user_question = text
            print(f"User question: {text}")
            self._run_advice(question=text, schema_key="question")

        self.prompt_window = PromptWindow(callback=on_submit)
        self.prompt_window.show()

    def _handle_action_zone(self, zone, mx, my):
        """Hover-fill a game-provided action button; fire on full fill."""
        ui = self.session.model
        if self._in_box(mx, my, zone.box) and zone.guard():
            cur = getattr(ui, zone.fill_key)
            if int(cur * 100) / 100 >= 0.98:
                setattr(ui, zone.fill_key, 0.0)
                zone.on_complete()
            elif cur <= 1.0:
                setattr(ui, zone.fill_key, cur + 0.019)
        else:
            setattr(ui, zone.fill_key, 0.0)

    def tick(self):
        model = self.session.model

        # Game state is fetched off-thread by the data sources; tick only reads it.
        geom = self.view.render(self.session, self.cards)
        if not geom:
            return

        mx, my = pyautogui.position()

        # Game-provided action zones (e.g. pre-game "Apply runes") are interactive
        # in any phase.
        for zone in geom.get('zones', []):
            self._handle_action_zone(zone, mx, my)

        # No main button this frame (pre-game) → only zones were interactive.
        if 'main' not in geom:
            return

        on_main = self._in_box(mx, my, geom['main'])

        # ── idle ──────────────────────────────────────────────
        if model.state == 'idle':
            if on_main:
                model.state = 'filling'
                model.compl = 0.019

        # ── filling ───────────────────────────────────────────
        elif model.state == 'filling':
            if on_main:
                if int(model.compl * 100) / 100 >= 0.98:
                    model.state = 'unfurled'
                    model.compl = 1.0
                    model.has_left = False
                elif model.compl <= 1.0:
                    model.compl += 0.019
            else:
                model.state = 'idle'
                model.compl = 0.0

        # ── unfurled ──────────────────────────────────────────
        elif model.state == 'unfurled':
            model.compl = 0.0

            on_any = on_main
            for i, lb in enumerate(geom['left']):
                if self._in_box(mx, my, lb):
                    on_any = True
                    if int(model.left_compls[i] * 100) / 100 >= 0.98:
                        self._run_tab(i)
                        model.left_compls[i] = 0.0
                    elif model.left_compls[i] <= 1.0:
                        model.left_compls[i] += 0.019
                else:
                    model.left_compls[i] = 0.0

            if geom['right'] and self._in_box(mx, my, geom['right']):
                on_any = True
                if int(model.right_compl * 100) / 100 >= 0.98:
                    model.right_compl = 0.0
                    self.show_prompt_window()
                elif model.right_compl <= 1.0:
                    model.right_compl += 0.019
            else:
                model.right_compl = 0.0

            if not on_any:
                model.has_left = True

            # re-hover on OG after leaving → start close animation
            if model.has_left and on_main:
                model.state = 'closing'
                model.compl = 0.0
                model.left_compls = [0.0] * len(model.left_compls)
                model.right_compl = 0.0

        # ── closing ──────────────────────────────────────────
        elif model.state == 'closing':
            if on_main:
                if int(model.compl * 100) / 100 >= 0.98:
                    model.state = 'cooldown'
                    model.compl = 0.0
                    model.has_left = False
                elif model.compl <= 1.0:
                    model.compl += 0.019
            else:
                model.state = 'unfurled'
                model.compl = 1.0

        # ── cooldown ─────────────────────────────────────────
        elif model.state == 'cooldown':
            if not on_main:
                model.state = 'idle'
