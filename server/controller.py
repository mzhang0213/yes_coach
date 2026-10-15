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
STATE_POLL_S = 1.0          # how often the state toast's live data / the client phase is refreshed
DRAFT_DEBOUNCE_S = 6        # min wall seconds between champ select advice calls (picks change fast)
DRAFT_MAX_TOKENS = 700      # reads + full rune page + summoners don't fit the one-shot default
DRAFT_TIMEOUT_S = 10        # champ select isn't time-critical, and the reply is long


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
        # champ select advice calls: signature asked for last + when
        self._draft_asked = None
        self._draft_last_start = float('-inf')
        self._draft_raw = None
        self._game_id = model.game.game_id
        threading.Thread(target=self._poll_live_state, daemon=True).start()
        threading.Thread(target=self._load_static, daemon=True).start()
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
        """Worker body: answer a question → game.answer, fast first. If the quick answer says it
        needs more thought (or failed in a way thinking may fix), show it marked "refining" and
        amend it with a slower thinking pass. Dropped if the panel moved on (Cancel/✕/another
        question) while it ran."""
        game = self.model.game
        coach = self._get_coach()
        if coach is None:
            self._set_answer(rid, question, {"action": "", "text": "Coach unavailable — check the console for the init error."})
            return
        quick = self._answer(coach, question)
        ok = not quick.get("error")
        refine = coach.can_think and (quick.get("more_thought") is True if ok
                                      else quick["error"] in ("timeout", "bad_reply"))
        answer = self._answer_card(quick)
        if refine:
            answer["note"] = "Thinking it over…" if ok else "Quick answer failed — thinking it over…"
            answer["refining"] = True
        if not self._set_answer(rid, question, answer) or not refine:
            return
        deep = self._answer(coach, f"Think it through carefully and revise your last answer if it was "
                                   f"wrong or too vague: {question}" if ok else question, deep=True)
        if not deep.get("error"):
            revised = self._answer_card(deep)
            if ok and revised["action"] != answer["action"]:
                revised["note"] = "Revised after a closer look"
            self._set_answer(rid, question, revised)
        elif ok:  # keep the quick answer, just stop the spinner
            self._set_answer(rid, question, self._answer_card(quick))
        else:
            self._set_answer(rid, question, self._answer_card(deep))

    def _answer(self, coach, question, deep=False):
        game = self.model.game
        if game.phase == "ChampSelect":  # no live game yet: the draft is the state
            return coach.get_advice(question, state=game.draft_context(),
                                    context=game.loadout_options(), deep=deep)
        return coach.get_advice(question, context=game.coach_context(), deep=deep)

    @staticmethod
    def _answer_card(result):
        """Coach reply (or get_advice error dict) → {"action", "text"} for the panel."""
        if not result.get("error") and (result.get("why") or result.get("answer")):
            return {"action": str(result.get("action") or ""), "text": str(result.get("why") or result.get("answer"))}
        return {"action": "", "text": f"Couldn't get an answer: {result.get('action') or 'empty reply'}"}

    def _set_answer(self, rid, question, answer):
        """Write game.answer if the panel still waits on this question; False if it moved on."""
        game = self.model.game
        if rid == self._ask_rid and game.question == question:
            game.answer = answer
            return True
        print(f"[coach] dropped stale answer to {question!r}")
        return False

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
            game.suggestions = game.question = game.answer = None  # an open tip card stays
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
                                      f"Facts so far: {tip.detail} Rule-based action: {tip.action}. "
                                      f"Give a sharper, more specific action if the state allows.",
                                      schema_key="tip", context=self.model.game.coach_context(), one_shot=True)
        except Exception as e:
            print(f"[coach] tip detail failed: {e}")
            return
        action = result.get("action") if not result.get("error") else None
        why = result.get("why") if isinstance(result, dict) else None
        if isinstance(action, str) and action.strip():
            tip.action, tip.detail_by = action.strip(), "coach"
            if isinstance(why, str) and why.strip():
                tip.detail = why.strip()
        else:
            print(f"[coach] tip detail failed: {result}")

    def _poll_live_state(self):
        """Worker: follow the League client's phase; in champ select read the session,
        otherwise keep game.live_state (the compressed state the coach gets) fresh for the
        state toast. Off the GUI thread: these are Riot requests. Plain writes only."""
        from server.resources.gemini import compress_game_state
        game = self.model.game
        while True:
            try:
                game.lcu_phase = get_gameflow_phase()  # None = client not running
            except Exception:
                game.lcu_phase = None
            if game.lcu_phase is not None and game.player is None:  # rank + mastery, once per game
                try:
                    game.player = get_player_profile()
                except Exception:
                    pass
            if game.lcu_phase == "ChampSelect":
                try:
                    game.champ_select_raw = get_champ_select_session()
                except Exception:
                    pass
                game.live_state = None
            else:
                try:
                    game.live_state = compress_game_state()
                except Exception:
                    game.live_state = None  # no game / client unreachable
            time.sleep(STATE_POLL_S)

    def _load_static(self):
        """Worker: Data Dragon champion / spell / rune data for champ select (cached per patch)."""
        try:
            self.model.game.static = load_static_data()
        except Exception as e:
            print(f"[coach] couldn't load champion data: {e}")

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
        # champ select offers the fixed draft questions only (situational ones need the live game)
        return (not self._coach_failed and not self._suggest_inflight and self.model.game.phase != "ChampSelect"
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
                    game.llm_suggestions = (game.clock, [str(q) for q in qs][:5])
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

    def _update_draft(self, game):
        """Main thread, champ select: fold in the latest session, ask the coach for comp
        reads + loadout when the picks change (debounced), apply a landed reply."""
        raw = game.champ_select_raw
        if raw is not None and raw is not self._draft_raw:
            self._draft_raw = raw
            game.ingest_draft(raw)
        sig = game.draft_signature
        if (sig and sig != self._draft_asked and not self._coach_failed and game.static
                and (sig[0] or sig[2])  # something to reason about: my pick or enemy picks
                and time.monotonic() - self._draft_last_start >= DRAFT_DEBOUNCE_S):
            self._draft_asked, self._draft_last_start = sig, time.monotonic()
            threading.Thread(target=self._run_draft, args=(sig,), daemon=True).start()
        game.apply_draft_advice()

    def _run_draft(self, sig):
        """Worker body: champ select comp reads + runes/summoners → game.draft_advice."""
        coach = self._get_coach()
        if coach is None:
            return
        game = self.model.game
        result = coach.get_advice(
            "Read both team comps from general matchup / counter knowledge and pick my runes and "
            "summoner spells for this game (only from rune_options / summoner_options). If my champion "
            "isn't picked yet, leave runes and summoners null.",
            schema_key="draft", state=game.draft_context(), context=game.loadout_options(),
            one_shot=True, max_tokens=DRAFT_MAX_TOKENS, timeout_s=DRAFT_TIMEOUT_S)
        if isinstance(result, dict) and ("reads" in result or "runes" in result):
            game.draft_advice = (sig, result)
            print(f"[coach] draft advice for {sig[0]}: {[r.get('headline') for r in result.get('reads') or []]}")
        else:
            print(f"[coach] draft advice failed: {result}")

    def _check_new_game(self, game):
        """The model started a new game: drop per-game controller + coach state too."""
        if game.game_id == self._game_id:
            return
        self._game_id = game.game_id
        self._draft_asked, self._draft_raw = None, None
        self._draft_last_start = float('-inf')
        if self._coach is not None:
            self._coach.new_session()
        print(f"[coach] new game (#{game.game_id})")

    def update_game_state(self, model: OverlayModel):
        #read state from Riot API at curr time (RN) and log in memory
        model.game.set_phase(model.game.lcu_phase)
        self._check_new_game(model.game)
        if model.game.phase == "ChampSelect":
            self._update_draft(model.game)
            return  # no Live Client API until the game loads
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
        self._check_new_game(model.game)  # ingest() notices a new game by the clock going backwards
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
