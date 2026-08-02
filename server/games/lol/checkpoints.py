"""LOL checkpoint rules — WHEN the coach proactively speaks in a League game.

Three trigger classes:
  * time-based    — fixed game-clock marks (15:00, 20:00)
  * computed-spawn — objectives the API never announces but whose timing is
                     deterministic (first drake 5:00, respawn 5min after a
                     DragonKill, baron 20:00); pre-warned ~30s ahead
  * event-based   — objective/teamfight events from the Live Client feed, plus
                    death streaks surfaced by trends.py
"""

from server.core.checkpoints import Checkpoint

# Pre-warning lead time before a computed objective spawn.
_LEAD = 30.0
FIRST_DRAGON = 300.0
DRAGON_RESPAWN = 300.0
BARON_SPAWN = 1200.0

# Game-clock marks worth a strategic check-in.
_TIME_MARKS = {900: "15-minute mark", 1200: "20-minute mark"}

# Live Client events we react to, mapped to the schema "event_type" hint.
_EVENT_KINDS = {
    "DragonKill": "dragon",
    "BaronKill": "baron",
    "HeraldKill": "other",
    "TurretKilled": "tower",
    "InhibKilled": "other",
    "Multikill": "kill",
    "FirstBlood": "kill",
    "Ace": "other",
}


class LolCheckpointRules:
    def __init__(self):
        self._fired: set = set()
        self._last_drake_time = 0.0   # EventTime of the most recent DragonKill

    def reset(self) -> None:
        self._fired.clear()
        self._last_drake_time = 0.0

    def _fire(self, out, cp: Checkpoint):
        if cp.key not in self._fired:
            self._fired.add(cp.key)
            out.append(cp)

    def check(self, state: dict, events: list[dict], trends: dict) -> list[Checkpoint]:
        out: list[Checkpoint] = []
        gt = state.get("t", 0.0) or 0.0

        # ── time-based ──────────────────────────────────────────────────────
        for mark, label in _TIME_MARKS.items():
            if gt >= mark:
                self._fire(out, Checkpoint(f"time:{mark}", label))

        # ── computed objective spawns (pre-warn ~30s ahead) ─────────────────
        # Track the latest DragonKill so we know when the next drake is up.
        for e in events:
            if e.get("EventName") == "DragonKill":
                self._last_drake_time = max(self._last_drake_time,
                                            e.get("EventTime", 0.0))

        next_drake = (self._last_drake_time + DRAGON_RESPAWN
                      if self._last_drake_time else FIRST_DRAGON)
        if next_drake - _LEAD <= gt < next_drake:
            self._fire(out, Checkpoint(
                f"drake_soon:{int(next_drake)}",
                "Dragon spawning soon — take it or trade?",
                want_image=True))

        if BARON_SPAWN - _LEAD <= gt < BARON_SPAWN:
            self._fire(out, Checkpoint(
                "baron_soon", "Baron spawning soon — set up vision?",
                want_image=True))

        # ── event-based ─────────────────────────────────────────────────────
        for e in events:
            name = e.get("EventName")
            kind = _EVENT_KINDS.get(name)
            if kind is None:
                continue
            eid = e.get("EventID")
            self._fire(out, Checkpoint(
                f"event:{eid}", f"{name}", schema_key="event", event_type=kind))

        # ── death streak (from trends) ──────────────────────────────────────
        streak = trends.get("death_streak", 0)
        if streak >= 2:
            self._fire(out, Checkpoint(
                f"deaths:{streak}", f"{streak} deaths in a row — reset and play safe",
                schema_key="event", event_type="death"))

        return out
