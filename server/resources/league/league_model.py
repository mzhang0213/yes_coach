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
LLM_SUGGESTION_TTL = 30.0  # game s a Gemini question list stays on offer after it was generated

# dragon timers (game s) — sent to the coach so it doesn't guess spawn times
FIRST_DRAGON_S = 5 * 60
DRAGON_RESPAWN_S = 5 * 60

# Riot event name → objective label used in recent_context()
_OBJECTIVES = {
    "DragonKill": "dragon",
    "BaronKill": "baron",
    "HeraldKill": "herald",
    "HordeKill": "grubs",       # unverified event name, see CHECKPOINTS
    "TurretKilled": "turret",
    "InhibKilled": "inhib",
}

# tips — thresholds (game s / per minute / gold)
CS_CHECK_FROM_S = 5 * 60    # don't judge CS/min before this
CS_PER_MIN_LOW = 5.0        # below → "CS is low" (skipped for supports)
GOLD_UNSPENT = 1500         # at or above → "Gold to spend"
DRAGON_HEADS_UP_S = 45      # "Dragon at m:ss" this long before it spawns
CHECKPOINT_TIP_TTL = 90     # checkpoint tips stay up this long after the moment they mark

# enemy objective (recent_context type) → (headline, rule-written detail). Baron/herald/grubs/inhib
# come from CHECKPOINTS instead, so they aren't tipped twice.
_EVENT_TIPS = {
    "dragon": ("Enemy took dragon",
               "Don't fight a buffed team head-on — trade for a turret, grubs or a side wave elsewhere."),
    "turret": ("Lost a turret",
               "That lane is now exposed. Don't farm it alone under the next turret — group or swap lanes."),
}

# checkpoint title → (priority, bubble category, headline, rule-written detail)
_CHECKPOINT_TIPS = {
    "15 min ff":         (1, "macro", "Surrender vote open",
                          "/ff is available. If you're behind, play for picks and side waves instead of coin-flip fights."),
    "void grubs spawn":  (3, "objective", "Void Grubs are up",
                          "Shove your lane so you can help your jungler take grubs — or ward to see if the enemy starts them."),
    "rift herald spawn": (3, "objective", "Rift Herald is up",
                          "Herald lets you crash a turret. Shove first, then group with your jungler top side."),
    "first baron spawn": (4, "objective", "Baron is up",
                          "Get vision around the pit. Only start it when the enemy is down members or far away."),
    "first inhib":       (3, "macro", "First inhibitor down",
                          "Super minions now push that lane. Use the pressure to take objectives elsewhere — or collapse to defend."),
    "void grubs taken":  (2, "macro", "Grubs taken",
                          "If your team has them, push a side lane — they speed up turret damage. If not, expect pressure there."),
    "rift herald taken": (2, "macro", "Herald taken",
                          "Expect it to be released on a turret soon — be ready to defend or follow up."),
    "baron taken":       (5, "macro", "Baron taken",
                          "With it: group and siege. Against it: clear waves near your base and don't fight in the open."),
    "elder spawn":       (5, "objective", "Elder Dragon is up",
                          "Elder executes low-HP enemies. Set up vision early and don't let the enemy start it for free."),
}

GENERIC_QUESTIONS = ["What should I do now?", "Where should I be now?", "What should I buy next?"]

# (objective, side that took it) → suggested question
_OBJECTIVE_QUESTIONS = {
    ("dragon", "enemy"): "Should I have contested dragon?",
    ("dragon", "ally"):  "What do we do after dragon?",
    ("baron", "enemy"):  "How do we defend baron push?",
    ("baron", "ally"):   "How do we use baron?",
    ("herald", "enemy"): "Should I have contested herald?",
    ("herald", "ally"):  "Where should we use herald?",
    ("grubs", "enemy"):  "Should I have contested grubs?",
    ("grubs", "ally"):   "What do we do after grubs?",
    ("turret", "enemy"): "What now after losing that turret?",
    ("turret", "ally"):  "Where do I go after turret?",
    ("inhib", "enemy"):  "How do we defend our base?",
    ("inhib", "ally"):   "How do we close the game?",
}


def _mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def suggest_questions(ctx: dict, limit: int = 5) -> list[str]:
    """Rule-based questions the player probably wants answered, most specific first.

    Takes recent_context() output. Always returns `limit` questions, padded
    with generic ones.
    """
    qs = []
    if ctx["my_deaths"]:
        last = ctx["my_deaths"][-1]
        qs.append("Why did I die?")
        if len(last["assisters"]) >= 2:
            qs.append("Was I caught out of position?")
        elif (last["killer"] or "").startswith("Turret"):
            qs.append("Should I have dived there?")
        else:
            qs.append("Could I have won that fight?")
    for obj in reversed(ctx["objectives"]):  # newest first
        q = _OBJECTIVE_QUESTIONS.get((obj["type"], obj["by"]))
        if q and q not in qs:
            qs.append(q)
    if ctx["my_takedowns"]:
        qs.append("How do I use this lead?")
    for q in GENERIC_QUESTIONS:
        if q not in qs:
            qs.append(q)
    return qs[:limit]


class LeagueModel(GameModel):
    def __init__(self):
        super().__init__(CHECKPOINTS, [])
        self.pinned_questions = list(GENERIC_QUESTIONS)

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

        # background suggestions: ingest() sets suggest_trigger to a fresh event
        # worth reacting to (my death / an objective); the controller consumes it,
        # and its worker writes llm_suggestions = (event game time, [questions])
        self.suggest_trigger: dict | None = None
        self.llm_suggestions: tuple[float, list[str]] | None = None

    def set_roster(self, active_player_name: str, players: list[dict]):
        """Learn who the player is and every player's team/champion.

        Takes /activeplayername and /playerlist output. Events name players by
        game name, so each player is indexed under riotId, riotIdGameName and
        summonerName.
        """
        self.roster = {}
        self.my_names = set()
        for p in players:
            info = {"team": p.get("team"), "champion": p.get("championName"), "position": p.get("position", "")}
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
            if ((name in _OBJECTIVES or (name == "ChampionKill" and ev.get("VictimName") in self.my_names))
                    and ev.get("EventTime", self.clock) >= self.clock - RECENT_WINDOW):
                self.suggest_trigger = ev
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

    def state_lines(self) -> list[str]:
        """Readable lines for the overlay's state toast: live_state (polled from the
        Riot API — the same fields the coach gets) + the recent-events window."""
        s = self.live_state
        if s is None:
            return ["Riot API · no live game"]
        champ = next((self.roster[n]["champion"] for n in self.my_names if n in self.roster), None)
        lines = [
            f"Riot API · {_mmss(s['t'])} · {s['mode']}",
            f"{champ or '?'} · lvl {s['lvl']} · {s['g']}g",
            f"HP {s['hp']}/{s['mhp']}   MP {s['mp']}/{s['mmp']}",
            f"KDA {s['k']}/{s['d']}/{s['a']}   CS {s['cs']}",
            f"AD {s['ad']}   AP {s['ap']}",
        ]
        ctx = self.recent_context()
        recent = [(d["t"], f"died to {d['killer']}" + (f" +{len(d['assisters'])}" if d["assisters"] else ""))
                  for d in ctx["my_deaths"]]
        recent += [(d["t"], f"killed {d['victim']}") for d in ctx["my_takedowns"]]
        recent += [(o["t"], " ".join(filter(None, [o["by"], o.get("detail", "").lower(), o["type"],
                                                   "(stolen)" if o.get("stolen") else ""])))
                   for o in ctx["objectives"]]
        lines.append(f"Last {int(RECENT_WINDOW)}s:" + ("" if recent else " quiet"))
        lines += [f"  {_mmss(t)}  {text}" for t, text in sorted(recent)]
        return lines

    def coach_context(self) -> dict:
        """recent_context() plus what the coach needs to stay in the present: the
        clock as m:ss and the next dragon (from the event feed, not guessed)."""
        ctx = {"clock": _mmss(self.clock), **self.recent_context()}
        spawn = self._next_dragon_spawn()
        if spawn is not None:
            ctx["dragon"] = "alive now" if self.clock >= spawn else f"spawns at {_mmss(spawn)}"
        return ctx

    def _next_dragon_spawn(self) -> float | None:
        """Game s the next elemental dragon spawns (may be past = alive), or None
        after 4 drakes — soul/elder rules apply there and aren't modelled."""
        if self.dragon_count >= 4:
            return None
        return FIRST_DRAGON_S if self.last_dragon_time is None else self.last_dragon_time + DRAGON_RESPAWN_S

    # ── tips ──
    def update_tips(self) -> list:
        """Offer / clear tips from live stats, the dragon timer and recent events.
        Call after ingest(); returns the newly offered Tips."""
        now, new = self.clock, []
        self.expire_tips(now)

        def offer(*args, ttl, category):
            tip = self.offer_tip(*args, now=now, ttl=ttl, category=category)
            if tip:
                new.append(tip)

        s = self.live_state
        if s:
            me = next((self.roster[n] for n in self.my_names if n in self.roster), {})
            minutes = now / 60
            cpm = s["cs"] / minutes if minutes else 0
            if now >= CS_CHECK_FROM_S and me.get("position") != "UTILITY" and cpm < CS_PER_MIN_LOW:
                offer("cs_low", "CS is low",
                      f"{s['cs']} CS at {_mmss(now)} — {cpm:.1f}/min. Aim for 7+: last-hit every wave "
                      f"before you roam and catch side waves.", 1, ttl=120, category="farm")
            elif cpm >= CS_PER_MIN_LOW + 0.5:
                self.clear_tip("cs_low", now)
            if s["g"] >= GOLD_UNSPENT:
                offer("gold", "Gold to spend",
                      f"{s['g']}g unspent. Next time your wave is pushed, recall and buy your next item.",
                      1, ttl=120, category="economy")
            elif s["g"] < GOLD_UNSPENT - 500:
                self.clear_tip("gold", now)

        spawn = self._next_dragon_spawn()
        if spawn is not None and 0 < spawn - now <= DRAGON_HEADS_UP_S:
            offer(f"dragon_soon@{round(spawn)}", f"Dragon at {_mmss(spawn)}",
                  f"Dragon spawns in ~{round(spawn - now)}s. Shove your wave and move toward the pit "
                  f"with your team so you get there first.", 5, ttl=spawn - now + 30,
                  category="objective")

        ctx = self.recent_context()
        for d in ctx["my_deaths"]:
            killers = " + ".join(filter(None, [d["killer"], *d["assisters"]]))
            offer(f"death@{d['t']}", "Why you died",
                  f"Died to {killers} at {_mmss(d['t'])}. Before stepping up, check where the enemy "
                  f"jungler was last seen and whether your wave was pushed.", 4, ttl=d["t"] + 60 - now,
                  category="death")
        for o in ctx["objectives"]:
            if o["by"] == "enemy" and o["type"] in _EVENT_TIPS:
                headline, detail = _EVENT_TIPS[o["type"]]
                offer(f"{o['type']}@{o['t']}", headline, detail, 4, ttl=o["t"] + 60 - now, category="macro")
        return new

    def checkpoint_tip(self, cp: Checkpoint):
        """Turn a fired checkpoint into a tip — unless it happened a while ago
        (e.g. launching mid-game fires every past checkpoint at once)."""
        if cp.title not in _CHECKPOINT_TIPS:
            return None
        if isinstance(cp, ElderCheckpoint) and self.dragon_count < 4:
            return None  # elder needs soul first; ElderCheckpoint alone ignores that
        happened = self._checkpoint_time(cp)
        if happened is None or self.clock - happened > CHECKPOINT_TIP_TTL:
            return None
        priority, category, headline, detail = _CHECKPOINT_TIPS[cp.title]
        return self.offer_tip(f"cp:{cp.title}", headline, detail, priority, category=category,
                              now=self.clock, ttl=happened + CHECKPOINT_TIP_TTL - self.clock)

    def _checkpoint_time(self, cp: Checkpoint) -> float | None:
        if isinstance(cp, ClockCheckpoint):
            return cp.indicator
        if isinstance(cp, ElderCheckpoint):
            return None if self.last_dragon_time is None else self.last_dragon_time + cp.indicator
        if isinstance(cp, EventCheckpoint):  # latest such event still in the recent window
            times = [e.get("EventTime", self.clock) for e in self.recent_events
                     if e.get("EventName") == cp.indicator]
            return max(times) if times else None
        return None

    def current_suggestions(self, limit: int = 3) -> list[str]:
        """Questions to offer right now: up to `limit` about the situation (fresh
        background LLM ones first, then rules), then the always-there pinned_questions.
        llm_suggestions is (game time generated, questions)."""
        qs = []
        if self.llm_suggestions and self.clock - self.llm_suggestions[0] <= LLM_SUGGESTION_TTL:
            qs = list(self.llm_suggestions[1])
        qs += suggest_questions(self.recent_context())
        seen = {q.lower() for q in self.pinned_questions}
        situational = []
        for q in qs:
            if q.lower() not in seen:
                situational.append(q)
                seen.add(q.lower())
        return situational[:limit] + self.pinned_questions

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
