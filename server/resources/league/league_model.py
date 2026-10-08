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

RECENT_WINDOW = 60.0  # seconds of game time kept for recent_context()

# Riot event name → objective label used in recent_context()
_OBJECTIVES = {
    "DragonKill": "dragon",
    "BaronKill": "baron",
    "HeraldKill": "herald",
    "HordeKill": "grubs",       # unverified event name, see CHECKPOINTS
    "TurretKilled": "turret",
    "InhibKilled": "inhib",
}

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

        # rolling window of raw events (last RECENT_WINDOW s) + who-is-who,
        # so recent_context() can say "you died to X" / "enemy took dragon"
        self.recent_events: list[dict] = []
        self.my_names: set[str] = set()
        self.my_team: str | None = None
        self.roster: dict[str, dict] = {}  # any name alias → {"team", "champion"}

    def set_roster(self, active_player_name: str, players: list[dict]):
        """Learn who the player is and every player's team/champion.

        Takes /activeplayername and /playerlist output. Events name players by
        game name, so each player is indexed under riotId, riotIdGameName and
        summonerName.
        """
        self.roster = {}
        self.my_names = set()
        for p in players:
            info = {"team": p.get("team"), "champion": p.get("championName")}
            aliases = {p.get("riotId"), p.get("riotIdGameName"), p.get("summonerName")} - {None, ""}
            for a in aliases:
                self.roster[a] = info
            if active_player_name in aliases:
                self.my_names = aliases
                self.my_team = info["team"]

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
            self.recent_events.append(ev)
            name = ev.get("EventName", "")
            self.seen_event_names.add(name)
            if name == "DragonKill" and ev.get("DragonType") != "Elder":
                self.dragon_count += 1
                self.last_dragon_time = ev.get("EventTime", self.clock)
        self.recent_events = [e for e in self.recent_events
                              if e.get("EventTime", self.clock) >= self.clock - RECENT_WINDOW]
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

    def recent_context(self) -> dict:
        """Compact summary of the last RECENT_WINDOW seconds, for the coach.

        Players are labelled by champion when known; anything else (turrets,
        minions, monsters) keeps its raw Riot name. Objective "by" is
        "ally" / "enemy" / "unknown" relative to the player's team.
        """
        deaths, takedowns, objectives = [], [], []
        for ev in self.recent_events:
            name = ev.get("EventName")
            t = round(ev.get("EventTime", self.clock))
            if name == "ChampionKill":
                assisters = ev.get("Assisters", [])
                if ev.get("VictimName") in self.my_names:
                    deaths.append({"t": t, "killer": self._label(ev.get("KillerName")),
                                   "assisters": [self._label(a) for a in assisters]})
                elif ev.get("KillerName") in self.my_names or self.my_names & set(assisters):
                    takedowns.append({"t": t, "victim": self._label(ev.get("VictimName"))})
            elif name in _OBJECTIVES:
                obj = {"t": t, "type": _OBJECTIVES[name], "by": self._side(ev)}
                if ev.get("DragonType"):
                    obj["detail"] = ev["DragonType"]
                if ev.get("Stolen") == "True":
                    obj["stolen"] = True
                objectives.append(obj)
        return {"t": round(self.clock), "my_deaths": deaths,
                "my_takedowns": takedowns, "objectives": objectives}

    def _label(self, name: str | None) -> str | None:
        info = self.roster.get(name)
        return info["champion"] if info else name

    def _side(self, ev: dict) -> str:
        """Which side took an objective, relative to the player."""
        if self.my_team is None:
            return "unknown"
        # structures encode their owner (T1 = ORDER, T2 = CHAOS); the killer
        # may be a minion, so the owner is the reliable signal
        structure = ev.get("TurretKilled") or ev.get("InhibKilled") or ""
        if "_T1_" in structure or "_T2_" in structure:
            owner = "ORDER" if "_T1_" in structure else "CHAOS"
            return "enemy" if owner == self.my_team else "ally"
        info = self.roster.get(ev.get("KillerName"))
        if not info:
            return "unknown"
        return "ally" if info["team"] == self.my_team else "enemy"
