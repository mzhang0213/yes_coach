"""Controller layer — input handling and state transitions.

Reads user input (cursor position, prompt submissions), drives the overlay
state machine, and mutates the model. Asks the view to render each frame, then
hit-tests the geometry the view reports back.
"""
import os
import threading
import time

import pyautogui
from dotenv import load_dotenv

from server.model import OverlayModel
from server.resources.riot import *
from server.utils import SCREEN_CAP
from server.view import PromptWindow

# load .env before anything reads COACH_* / GEMINI_* / LMSTUDIO_* settings
load_dotenv()

# screenshots for the coach's vision calls — off unless COACH_SCREENSHOTS=1
SCREENSHOT_HISTORY_S = 10   # seconds of frames kept
SCREENSHOT_INTERVAL_S = 0.5 # seconds between grabs
SCREENSHOT_LEAD_S = 2.0     # use the frame this long before the event (pre-death, not the grey screen)

QUICK_FRESH_S = 15          # Gemini suggestions younger than this (game s) open instantly instead of re-asking
SUGGEST_RETRY_S = 5         # min wall seconds between suggest calls (stops a failing call re-firing every frame)
STATE_POLL_S = 1.0          # how often the state toast's live data is refreshed


class OverlayController:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self.prompt_window = None
        # Gemini coach: built lazily on a worker thread, guarded (see _get_coach)
        self._coach = None
        self._coach_failed = False
        self._coach_lock = threading.Lock()
        # suggest calls: latest request id + ids still in flight (set ops are atomic)
        self._suggest_rid = 0
        self._suggest_inflight = set()
        self._suggest_last_start = float('-inf')
        self._suggest_landed = False  # a suggest call finished → refresh the open panel's rows
        # answer calls: only the latest id may write game.answer (Cancel/✕/new question bump it)
        self._ask_rid = 0
        threading.Thread(target=self._poll_live_state, daemon=True).start()
        self._screenshots = os.environ.get("COACH_SCREENSHOTS") == "1"
        if self._screenshots:
            SCREEN_CAP.start_capture(history_seconds=SCREENSHOT_HISTORY_S,
                                     frame_interval=SCREENSHOT_INTERVAL_S)

    @staticmethod
    def _in_box(x, y, box):
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def run_prompt(self):
        return

    def show_prompt_window(self):
        if self.prompt_window and self.prompt_window.isVisible():
            return

        def on_submit(text):
            self.ask(text)

        self.prompt_window = PromptWindow(callback=on_submit)
        self.prompt_window.show()

    def ask(self, question):
        """Put a question on the panel (answering state) and ask the coach on a worker."""
        game = self.model.game
        game.question = question
        game.answer = None
        self._ask_rid += 1
        threading.Thread(target=self._run_ask, args=(self._ask_rid, question), daemon=True).start()

    def _run_ask(self, rid, question):
        """Worker body: answer a question → game.answer. Dropped if the panel
        moved on (Cancel/✕/another question) while it ran."""
        game = self.model.game
        try:
            coach = self._get_coach()
            if coach is None:
                answer = "Coach unavailable — check the console for the init error."
            else:
                result = coach.get_advice(question, context=game.coach_context())
                if isinstance(result, dict) and result.get("answer"):
                    answer = str(result["answer"])
                    if result.get("follow_up"):
                        answer += f"\n\nNext: {result['follow_up']}"
                else:  # get_advice error dict: {priority, action, warning}
                    answer = f"Couldn't get an answer: {result.get('action') if isinstance(result, dict) else result}"
        except Exception as e:
            answer = f"Couldn't get an answer: {e}"
        if rid == self._ask_rid and game.question == question:
            game.answer = answer
        else:
            print(f"[coach] dropped stale answer to {question!r}")

    def handle_press(self, press):
        """Turn a view press into model changes."""
        game = self.model.game
        if press == 'open':
            game.question = game.answer = None
            self._show_suggestions()
        elif press == 'next':                 # answer read → back to (refreshed) questions
            self._ask_rid += 1
            game.question = game.answer = None
            self._show_suggestions()
        elif press == 'close':
            self._ask_rid += 1                # drop any answer still in flight
            game.suggestions = game.question = game.answer = None
            game.open_tip = None
        elif press.startswith('tip:'):        # bubble popped → detail card
            game.pop_tip(int(press.split(':')[1]), game.clock)
        elif press == 'tip_close':
            game.open_tip = None
        elif press == 'cancel':
            if game.suggestions is None:      # cancel analyzing → rule-based
                game.suggestions = game.current_suggestions()
            else:                             # cancel answering → back to suggestions
                self._ask_rid += 1
                game.question = game.answer = None
        elif press == 'prompt':
            self.show_prompt_window()
        elif press.startswith('suggest:'):
            i = int(press.split(':')[1])
            if game.suggestions and i < len(game.suggestions):
                self.ask(game.suggestions[i])

    def _show_suggestions(self):
        """Show what we have now (rules + any fresh Gemini questions); a pending or
        new suggest call swaps its questions in when it lands (see tick)."""
        self.model.game.suggestions = self.model.game.current_suggestions()
        if not self._fresh_llm_suggestions() and self._can_suggest():
            self._start_suggest()

    def _get_coach(self):
        """Build the coach once, thread-safe. Returns None if unavailable.

        Backend/model/keys come from env vars (COACH_BACKEND, see .env.example).
        Import is deferred here (not at module load) so a missing/broken SDK
        degrades to rule-only tips/questions instead of crashing startup. A failure is
        latched so we don't re-attempt disk/network I/O on every checkpoint.
        """
        with self._coach_lock:
            if self._coach is None and not self._coach_failed:
                try:
                    from server.resources.gemini import coach_from_env
                    self._coach = coach_from_env()
                    print(f"[coach] using {self._coach.name}")
                except Exception as e:
                    print(f"[coach] init failed: {e}")
                    self._coach_failed = True
            return self._coach

    def _run_tip_detail(self, tip):
        """Worker body: have the coach write a tip's detail from the live game.
        Keeps the rule-written detail if the coach is unavailable or fails."""
        coach = self._get_coach()
        if coach is None:
            return
        try:
            result = coach.get_advice(f"Quick tip for the player about: {tip.headline}. "
                                      f"Facts so far: {tip.detail}",
                                      schema_key="tip", context=self.model.game.coach_context(), one_shot=True)
        except Exception as e:
            print(f"[coach] tip detail failed: {e}")
            return
        detail = result.get("detail") if isinstance(result, dict) else None
        if isinstance(detail, str) and detail.strip():
            tip.detail, tip.detail_by = detail.strip(), "coach"
        else:
            print(f"[coach] tip detail failed: {result}")

    def _poll_live_state(self):
        """Worker: keep game.live_state (the compressed state the coach gets) fresh
        for the view's state toast. Off the GUI thread: it's 3 Riot requests."""
        from server.resources.gemini import compress_game_state
        while True:
            try:
                self.model.game.live_state = compress_game_state()
            except Exception:
                self.model.game.live_state = None  # no game / client unreachable
            time.sleep(STATE_POLL_S)

    def _screenshot_for(self, event_time):
        """JPEG from just before a game-time event, or None if screenshots are off.
        Maps game time to wall time assuming the clock runs at real speed."""
        if not self._screenshots or event_time is None:
            return None
        wall = time.time() - (self.model.game.clock - event_time) - SCREENSHOT_LEAD_S
        return SCREEN_CAP.frame_at(wall)

    def _fresh_llm_suggestions(self):
        s = self.model.game.llm_suggestions
        return s is not None and self.model.game.clock - s[0] <= QUICK_FRESH_S

    def _can_suggest(self):
        return (not self._coach_failed and not self._suggest_inflight
                and time.monotonic() - self._suggest_last_start >= SUGGEST_RETRY_S)

    def _start_suggest(self, event_time=None):
        """Ask Gemini for suggested questions on a worker. event_time is the
        game time it is about (an event), or None for "right now"."""
        self._suggest_rid += 1
        self._suggest_last_start = time.monotonic()
        self._suggest_inflight.add(self._suggest_rid)
        threading.Thread(target=self._run_suggest, args=(self._suggest_rid, event_time), daemon=True).start()

    def _run_suggest(self, rid, event_time):
        """Worker body: quick one-shot Gemini suggest call → game.llm_suggestions.
        If the panel is open and waiting on this call, fill it — with rules if
        Gemini failed, so it never spins forever."""
        game = self.model.game
        t = game.clock if event_time is None else event_time
        try:
            coach = self._get_coach()
            if coach is not None:
                image = self._screenshot_for(t)
                result = coach.get_advice(schema_key="suggest", context=game.coach_context(),
                                          image=image, one_shot=True)
                qs = result.get("questions") if isinstance(result, dict) else None
                if isinstance(qs, list) and qs:
                    # stamped with the clock when they arrive (not the event time) so
                    # freshness measures how old the questions really are
                    game.llm_suggestions = (game.clock, [str(q) for q in qs][:3])
                    print(f"[coach] suggestions ({'with' if image else 'no'} screenshot): {game.llm_suggestions[1]}")
                else:
                    print(f"[coach] suggest failed: {result}")
        except Exception as e:
            print(f"[coach] suggest failed: {e}")
        finally:
            self._suggest_inflight.discard(rid)
            if rid == self._suggest_rid:
                self._suggest_landed = True

    def _refresh_suggestions(self):
        """Swap freshly landed Gemini questions into the open suggestion list —
        but not while a row is filling, so the pick never changes under the cursor."""
        if not self._suggest_landed:
            return
        game = self.model.game
        if self.view.state != 'open':
            self._suggest_landed = False
        elif game.question is None and not any(
                fill for name, fill in self.view.fills.items() if name.startswith('suggest:')):
            game.suggestions = game.current_suggestions()
            self._suggest_landed = False

    def update_game_state(self, model: OverlayModel):
        #read state from Riot API at curr time (RN) and log in memory
        try:
            stats = get_game_stats()
            events = get_event_data()
        except Exception:
            return  # no live game / client unreachable — keep prior state

        if not model.game.roster:
            try:
                model.game.set_roster(get_active_player_name(), get_player_list())
            except Exception:
                pass  # retry next tick

        snap = model.game.ingest(stats, events)
        if model.game.suggest_trigger:
            ev, model.game.suggest_trigger = model.game.suggest_trigger, None
            self._start_suggest(ev.get("EventTime"))
        # tips: rules + fired checkpoints; the coach refines each new tip's detail in the background
        new_tips = model.game.update_tips()
        new_tips += filter(None, map(model.game.checkpoint_tip, model.game.evaluate_checkpoints(snap)))
        for tip in new_tips:
            print(f"[coach] tip: {tip.headline}")
            if not self._coach_failed:
                threading.Thread(target=self._run_tip_detail, args=(tip,), daemon=True).start()

    def tick(self):
        m = self.model

        self.update_game_state(m)
        self._refresh_suggestions()

        geom = self.view.render(m)
        if not geom:
            return

        mx, my = pyautogui.position()
        hover = {
            'main': geom['main'] is not None and self._in_box(mx, my, geom['main']),
            'buttons': {name: self._in_box(mx, my, box) for name, box in geom['buttons'].items()},
            'rows': [self._in_box(mx, my, box) for box in geom['rows']],
            'tips': {tid: self._in_box(mx, my, box) for tid, box in geom['tips'].items()},
            'card': geom['card'] is not None and self._in_box(mx, my, geom['card']),
        }

        # prefetch: start the suggest call as soon as the pill starts filling,
        # so Gemini's latency hides behind the ~0.85 s hover-fill
        if (self.view.state == 'idle' and hover['main']
                and not self._fresh_llm_suggestions() and self._can_suggest()):
            self._start_suggest()

        # view advances its own hover-fills + state machine and reports any
        # target that finished filling this frame
        press = self.view.advance(hover)
        if press:
            m.record_press(press)
            self.handle_press(press)
