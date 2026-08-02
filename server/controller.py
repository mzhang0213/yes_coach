"""Controller layer — input handling and state transitions.

Reads user input (cursor position, prompt submissions), drives the overlay
state machine, and mutates the model. Asks the view to render each frame, then
hit-tests the geometry the view reports back.
"""
import pyautogui

from server.model import OverlayModel
from server.resources.riot import *
from server.view import PromptWindow



class OverlayController:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self.prompt_window = None

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

    def update_game_state(self, model: OverlayModel):
        #read state from Riot API at curr time (RN) and log in memory
        #read chat updates too
        # model.update_players()
        # model.update_game_stats()
        # model.update_events()
        return


    def tick(self):
        m = self.model

        self.update_game_state(m)

        geom = self.view.render(m)
        if not geom:
            return

        mx, my = pyautogui.position()
        on_main = self._in_box(mx, my, geom['main'])

        # ── idle ──────────────────────────────────────────────
        if m.state == 'idle':
            if on_main:
                m.state = 'filling'
                m.compl = 0.019

        # ── filling ───────────────────────────────────────────
        elif m.state == 'filling':
            if on_main:
                if int(m.compl * 100) / 100 >= 0.98:
                    m.state = 'unfurled'
                    m.compl = 1.0
                    m.has_left = False
                elif m.compl <= 1.0:
                    m.compl += 0.019
            else:
                m.state = 'idle'
                m.compl = 0.0

        # ── unfurled ──────────────────────────────────────────
        elif m.state == 'unfurled':
            m.compl = 0.0

            # ── hover logic ──
            on_any = on_main
            for i, lb in enumerate(geom['left']):
                if self._in_box(mx, my, lb):
                    on_any = True
                    if int(m.left_compls[i] * 100) / 100 >= 0.98:
                        # TODO: trigger left tab action
                        m.left_compls[i] = 0.0
                    elif m.left_compls[i] <= 1.0:
                        m.left_compls[i] += 0.019
                else:
                    m.left_compls[i] = 0.0

            if self._in_box(mx, my, geom['right']):
                on_any = True
                if int(m.right_compl * 100) / 100 >= 0.98:
                    m.right_compl = 0.0
                    self.show_prompt_window()
                elif m.right_compl <= 1.0:
                    m.right_compl += 0.019
            else:
                m.right_compl = 0.0

            if not on_any:
                m.has_left = True

            # re-hover on OG after leaving → start close animation
            if m.has_left and on_main:
                m.state = 'closing'
                m.compl = 0.0
                m.left_compls = [0.0, 0.0, 0.0]
                m.right_compl = 0.0

        # ── closing ──────────────────────────────────────────
        elif m.state == 'closing':
            # bloom on main button to confirm close
            if on_main:
                if int(m.compl * 100) / 100 >= 0.98:
                    m.state = 'cooldown'
                    m.compl = 0.0
                    m.has_left = False
                elif m.compl <= 1.0:
                    m.compl += 0.019
            else:
                # moved off main → cancel close, back to unfurled
                m.state = 'unfurled'
                m.compl = 1.0

        # ── cooldown ─────────────────────────────────────────
        elif m.state == 'cooldown':
            # wait for cursor to leave main button before re-enabling
            if not on_main:
                m.state = 'idle'
