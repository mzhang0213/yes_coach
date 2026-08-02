"""Pre-game poller / phase coordinator — the LOL champ-select data source.

Polls the LCU gameflow-phase on its own daemon thread and drives the overlay's
pre-game behaviour: sets the session phase, parses the champ-select draft into
the game state, and asks the coach for ban/pick/rune advice when the draft
meaningfully changes. The in-game phase is owned by the live source on :2999.
"""

import json
import threading

from server.core.datasource import PollingDataSource
from server.games.lol.lcu import (
    LCUUnavailable,
    get_gameflow_phase,
    get_champ_select_session,
    get_champion_summary,
    get_perks_metadata,
    get_styles_metadata,
)
from server.games.lol.rune_mapper import build_rune_payload


# ── champ-select parsing (pure; unit-testable against saved session JSON) ────

def parse_draft(session: dict, champ_names: dict[int, str]) -> dict:
    """Reduce a raw champ-select session to a compact, coaching-relevant dict."""
    def name(cid):
        return champ_names.get(cid) if cid and cid > 0 else None

    local_id = session.get("localPlayerCellId")
    my_team = session.get("myTeam") or []
    their_team = session.get("theirTeam") or []

    my_role, my_champion, my_champion_locked = "", None, False
    for c in my_team:
        if c.get("cellId") == local_id:
            my_role = c.get("assignedPosition", "") or ""
            locked = name(c.get("championId"))          # set once the pick is locked
            my_champion = locked or name(c.get("championPickIntent"))  # else hover
            my_champion_locked = bool(locked)

    ally_picks = [
        {"role": c.get("assignedPosition", "") or "", "champion": name(c.get("championId"))}
        for c in my_team if name(c.get("championId"))
    ]
    enemy_picks = [name(c.get("championId")) for c in their_team if name(c.get("championId"))]

    # Bans: prefer the explicit list, else derive from completed ban actions.
    bans = []
    explicit = session.get("bans") or {}
    for key in ("myTeamBans", "theirTeamBans"):
        bans += [name(cid) for cid in (explicit.get(key) or []) if name(cid)]
    if not bans:
        for group in session.get("actions") or []:
            for a in group:
                if a.get("type") == "ban" and a.get("completed") and name(a.get("championId")):
                    bans.append(name(a.get("championId")))

    # What's happening right now, and whether it's my turn.
    phase_action, on_the_clock = None, False
    for group in session.get("actions") or []:
        for a in group:
            if not a.get("isInProgress"):
                continue
            if a.get("actorCellId") == local_id:
                phase_action, on_the_clock = a.get("type"), True
            elif phase_action is None:
                phase_action = a.get("type")  # someone else's turn — for context

    return {
        "my_role": my_role,
        "my_champion": my_champion,
        "my_champion_locked": my_champion_locked,
        "ally_picks": ally_picks,
        "enemy_picks": enemy_picks,
        "bans": bans,
        "phase_action": phase_action,   # "ban" | "pick" | None
        "on_the_clock": on_the_clock,
    }


def draft_signature(draft: dict) -> str:
    """Stable hash of the coaching-relevant draft state, for change dedup."""
    return json.dumps({
        "action": draft.get("phase_action"),
        "clock": draft.get("on_the_clock"),
        "mine": draft.get("my_champion"),
        "locked": draft.get("my_champion_locked"),
        "ally": [(p["role"], p["champion"]) for p in draft.get("ally_picks", [])],
        "enemy": draft.get("enemy_picks"),
        "bans": draft.get("bans"),
    }, sort_keys=True)


# ── data source ──────────────────────────────────────────────────────────────

class ClientPoller(PollingDataSource):
    def __init__(self, session, coach=None, interval: float = 1.5):
        super().__init__(name="LCU client poller", interval=interval)
        self.session = session
        self.coach = coach
        self._champ_names: dict[int, str] = {}
        self._last_sig = None
        self._loadout_champ = None  # champ we've already given a rune loadout for

    def _on_error(self, e):
        if isinstance(e, LCUUnavailable):
            self.session.model.phase = "NotRunning"
            self._reset()
        else:
            print(f"Client poller error: {e}")

    def _poll_once(self):
        phase = get_gameflow_phase() or "None"
        self.session.model.phase = phase

        if phase != "ChampSelect":
            self._reset()
            return

        if not self._champ_names:
            try:
                self._champ_names = get_champion_summary()
            except Exception:
                self._champ_names = {}

        cs_session = get_champ_select_session()
        if not cs_session:
            return
        draft = parse_draft(cs_session, self._champ_names)
        self.session.game.draft = draft
        self._on_draft_change(draft)

    def _on_draft_change(self, draft: dict):
        """Coach hook — only acts when the draft meaningfully changes, and only
        asks for advice when it's actually the player's turn to act."""
        sig = draft_signature(draft)
        if sig == self._last_sig:
            return
        self._last_sig = sig
        if not self.coach:
            return

        # Once our champion is locked, give a rune+spell loadout (once per champ).
        if draft.get("my_champion_locked") and draft.get("my_champion") != self._loadout_champ:
            self._loadout_champ = draft.get("my_champion")
            self._advise_loadout(draft)
        elif draft.get("on_the_clock") and draft.get("phase_action") in ("ban", "pick"):
            self._advise(draft["phase_action"], draft)

    def _advise(self, schema_key: str, draft: dict):
        """Ask the coach off-thread; stash the result for the overlay to render.

        Pass state={} — no live game exists during champ select, so there's no
        in-game state to send.
        """
        title = "Ban suggestion" if schema_key == "ban" else "Pick suggestion"

        def worker():
            try:
                advice = self.coach.get_advice(schema_key=schema_key, state={}, extra=draft)
            except Exception as e:
                print(f"pre-game advice error: {e}")
                return
            self.session.game.pregame_suggestion = {"title": title, "advice": advice}
            print(f"[pregame] {title} -> {advice}")

        threading.Thread(target=worker, daemon=True).start()

    def _advise_loadout(self, draft: dict):
        """Champ locked → recommend runes + spells and resolve names→IDs for apply."""
        def worker():
            try:
                advice = self.coach.get_advice(schema_key="loadout", state={}, extra=draft)
            except Exception as e:
                print(f"pre-game loadout error: {e}")
                return
            rec = dict(advice)
            try:
                rec["payload"] = build_rune_payload(
                    advice, get_perks_metadata(), get_styles_metadata())
            except Exception as e:
                print(f"rune name→ID mapping failed: {e}")
                rec["payload"] = None
            self.session.game.rune_recommendation = rec
            self.session.game.pregame_suggestion = {"title": "Runes & spells", "advice": advice}
            print(f"[pregame] loadout -> {advice}")

        threading.Thread(target=worker, daemon=True).start()

    def _reset(self):
        """Clear pre-game state when we leave champ select."""
        self._last_sig = None
        self._loadout_champ = None
        if self.session.game.draft:
            self.session.game.draft = {}
        self.session.game.pregame_suggestion = None
        self.session.game.rune_recommendation = None
