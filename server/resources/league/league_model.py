from abc import abstractmethod
from dataclasses import dataclass
from typing import Literal, TypeVar

from server.resources.checkpoint import Checkpoint
from server.resources.game_model import GameModel, PlayerType


@dataclass
class LeaguePlayer(PlayerType):
    champion_name:str
    items:list[str]
    level:int
    position:str
    respawnTimer:str
    runes:list[str]
    scores:str
    summonerSpells:str
    team:Literal["Red", "Blue"]

    hp:float
    shield:float #optional
    mana:float #optional
    ad:float
    ap:float
    haste:float
    armor:float
    mr:float
    armor_pen_p:float
    armor_pen_f:float
    magic_pen_p:float
    magic_pen_f:float
    lifesteal:float
    omnivamp:float
    tenacity:float
    health_regen:float
    mana_regen:float

    gold:int


@dataclass(frozen=True)
class LeagueSnapshot:
    """Derived, checkpoint-ready view of the live game, folded from raw Riot data.

    Checkpoints are predicates over this snapshot, not over their own indicator
    type — so LeagueCheckpoint[T]'s T labels the *indicator config* type while
    reached() consumes a LeagueSnapshot.
    """
    clock_seconds: float
    seen_event_names: frozenset[str]
    dragon_count: int
    seconds_since_last_dragon: float | None


T=TypeVar("T")
class LeagueCheckpoint(Checkpoint[T]):
    # NOTE: the base Checkpoint modeled T as both the indicator and the compared
    # state (equality). League checkpoints instead compare a LeagueSnapshot, so
    # here T only types `indicator`; the subclasses below override reached().
    def __init__(self, title:str, indicator:T):
        self.title=title
        self.indicator=indicator
        self.fired=False   # once-only latch; flipped by the eval loop, not reached()

    def reached(self, state: T) ->bool:
        return state == self.indicator


class ClockCheckpoint(LeagueCheckpoint[float]):
    """indicator = game-clock threshold in seconds."""
    def reached(self, s: LeagueSnapshot) -> bool:
        return s.clock_seconds >= self.indicator


class EventCheckpoint(LeagueCheckpoint[str]):
    """indicator = Riot event name (e.g. "InhibKilled")."""
    def reached(self, s: LeagueSnapshot) -> bool:
        return self.indicator in s.seen_event_names


class ElderCheckpoint(LeagueCheckpoint[float]):
    """indicator = seconds elapsed since the last (non-elder) dragon kill."""
    def reached(self, s: LeagueSnapshot) -> bool:
        # TODO: real Elder also requires 4 elemental dragons first (s.dragon_count >= 4)
        return (s.seconds_since_last_dragon is not None
                and s.seconds_since_last_dragon >= self.indicator)


class DragonCheckpoint(LeagueCheckpoint[int]):
    """indicator = number of (non-elder) dragons taken."""
    def reached(self, s: LeagueSnapshot) -> bool:
        return s.dragon_count >= self.indicator




CHECKPOINTS = [
    ClockCheckpoint("15 min ff", 15 * 60),
    ClockCheckpoint("void grubs spawn", 6 * 60),      # Void Grubs
    ClockCheckpoint("rift herald spawn", 14 * 60),    # after grubs despawn
    ClockCheckpoint("first baron spawn", 25 * 60),    # 2024 rework; no Riot baron-spawn event (clock approximation)
    EventCheckpoint("first inhib", "InhibKilled"),
    EventCheckpoint("void grubs taken", "HordeKill"), # undocumented event name — verify vs a live /eventdata
    EventCheckpoint("rift herald taken", "HeraldKill"),
    EventCheckpoint("baron taken", "BaronKill"),
    ElderCheckpoint("elder spawn", 6 * 60),
]

class LeagueModel(GameModel):
    def __init__(self):
        super().__init__(CHECKPOINTS, [])

        # accumulators for folding the raw Riot event feed into snapshots
        self.seen_event_ids = set()
        self.seen_event_names: set[str] = set()
        self.dragon_count = 0
        self.last_dragon_time: float | None = None
        self.clock = 0.0
        self.reached_log: list[str] = []

    def ingest(self, stats: dict, events: dict) -> LeagueSnapshot:
        """Fold raw Riot /gamestats + /eventdata into a LeagueSnapshot.

        Dedupes events by EventID (the feed returns the whole list every poll)
        so counters advance exactly once per event. Does no network I/O — takes
        plain dicts, so it is unit-testable headlessly.
        """
        self.clock = stats.get("gameTime", 0.0)
        for ev in events.get("Events", []):
            key = ev.get("EventID", (ev.get("EventName"), ev.get("EventTime")))
            if key in self.seen_event_ids:
                continue
            self.seen_event_ids.add(key)
            name = ev.get("EventName", "")
            self.seen_event_names.add(name)
            if name == "DragonKill" and ev.get("DragonType") != "Elder":
                self.dragon_count += 1
                self.last_dragon_time = ev.get("EventTime", self.clock)
        return LeagueSnapshot(
            clock_seconds=self.clock,
            seen_event_names=frozenset(self.seen_event_names),
            dragon_count=self.dragon_count,
            seconds_since_last_dragon=(self.clock - self.last_dragon_time
                                       if self.last_dragon_time is not None else None),
        )

    def evaluate_checkpoints(self, snap: LeagueSnapshot) -> list[Checkpoint]:
        """Return checkpoints newly reached this tick, latching each so it fires once."""
        newly = []
        for cp in self.checkpoints:
            if not getattr(cp, "fired", False) and cp.reached(snap):
                cp.fired = True
                self.reached_log.append(cp.title)
                newly.append(cp)
        return newly
