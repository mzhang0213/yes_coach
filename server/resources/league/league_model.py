import copy
import os
import re
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




# Objective timers (game s), Summoner's Rift — checked against the LoL wiki's patch history
# (Oct 2026): grubs 8:00 since V25.09 (no respawn, gone at 14:45), herald 15:00, baron 20:00 since
# V26.01 (was 25:00), dragon 5:00 then +5:00. Riot moves these between seasons — re-check on a
# new season.
FIRST_DRAGON_S = 5 * 60
DRAGON_RESPAWN_S = 5 * 60
GRUBS_SPAWN_S = 8 * 60
GRUBS_DESPAWN_S = 14 * 60 + 45
HERALD_SPAWN_S = 15 * 60
BARON_SPAWN_S = 20 * 60
BARON_RESPAWN_S = 6 * 60

CHECKPOINTS = [
    ClockCheckpoint("15 min ff", 15 * 60),
    ClockCheckpoint("void grubs spawn", GRUBS_SPAWN_S),
    ClockCheckpoint("rift herald spawn", HERALD_SPAWN_S),
    ClockCheckpoint("first baron spawn", BARON_SPAWN_S),  # no Riot baron-spawn event (clock approximation)
    EventCheckpoint("first inhib", "InhibKilled"),
    EventCheckpoint("void grubs taken", "HordeKill"), # undocumented event name — verify vs a live /eventdata
    EventCheckpoint("rift herald taken", "HeraldKill"),
    EventCheckpoint("baron taken", "BaronKill"),
    ElderCheckpoint("elder spawn", 6 * 60),
]

RECENT_WINDOW = 60.0  # seconds of game time kept for recent_context()
NEW_GAME_CLOCK_DROP_S = 30  # game clock jumping back more than this means a new game
LLM_SUGGESTION_TTL = 30.0  # game s a Gemini question list stays on offer after it was generated

# Riot event name → objective label used in recent_context()
_OBJECTIVES = {
    "DragonKill": "dragon",
    "BaronKill": "baron",
    "HeraldKill": "herald",
    "HordeKill": "grubs",       # unverified event name, see CHECKPOINTS
    "TurretKilled": "turret",
    "InhibKilled": "inhib",
}

# levels of play (rank → bracket) and experience (champion mastery points)
_BRACKETS = {"IRON": "low", "BRONZE": "low", "SILVER": "low", "GOLD": "mid", "PLATINUM": "mid",
             "EMERALD": "mid", "DIAMOND": "high", "MASTER": "high", "GRANDMASTER": "high", "CHALLENGER": "high"}
_BRACKET_LABELS = {"new": "new to League", "low": "low elo (Iron–Silver)", "mid": "mid elo (Gold–Emerald)",
                   "high": "high elo (Diamond+)"}
# (warn below, aim for) CS/min per bracket
CS_TARGETS = {"new": (3.5, 5.0), "low": (4.5, 6.0), "mid": (5.5, 7.0), "high": (6.5, 8.0)}
NEW_ACCOUNT_LEVEL = 30      # unranked and below this → "new" bracket
MASTERY_STEPS = [(10_000, "new to this champion"), (50_000, "some games on this champion"),
                 (150_000, "experienced on this champion")]  # ≥ last → "main"
MINION_GOLD = 20            # rough average gold per CS, to put a CS gap in gold

# tips — thresholds (game s / per minute / gold)
CS_CHECK_FROM_S = 5 * 60    # don't judge CS/min before this
GOLD_UNSPENT = 1500         # at or above → "Gold to spend"
DRAGON_HEADS_UP_S = 45      # "Dragon at m:ss" this long before it spawns
CHECKPOINT_TIP_TTL = 90     # checkpoint tips stay up this long after the moment they mark

# enemy objective (recent_context type) → (headline, action, why). Baron/herald/grubs/inhib
# come from CHECKPOINTS instead, so they aren't tipped twice.
_EVENT_TIPS = {
    "dragon": ("Enemy took dragon", "Hit a turret or grubs on the other side now",
               "They just spent 4 people on dragon — trade objectives instead of fighting their buff."),
    "turret": ("Lost a turret", "Don't farm that lane alone — swap or group",
               "The next turret is far from help; that's where you get collapsed on."),
}

# checkpoint title → (priority, bubble category, headline, action, why). Only moments that change
# what you should do right now — "/ff is open" or "grubs were taken" aren't tips.
_CHECKPOINT_TIPS = {
    "void grubs spawn":  (3, "objective", "Grubs are up", "Shove your wave, then help top side",
                          "Grubs give your team bonus turret damage; the side with lane prio gets them."),
    "rift herald spawn": (3, "objective", "Herald is up", "Shove, then group top with your jungler",
                          "A Herald charge takes ~1 turret plate-free — worth more than a wave."),
    "first baron spawn": (4, "objective", "Baron is up", "Ward the pit before anyone starts it",
                          "Baron decides games from here; start it only when an enemy is dead or far."),
    "first inhib":       (3, "macro", "Inhibitor down", "Play the side lane opposite the open inhib",
                          "Super minions push that lane for you — use the pressure, don't stand in it."),
    "baron taken":       (5, "macro", "Baron taken", "Group: siege with it, or clear waves at home",
                          "Baron buff lasts 3 min — that window decides the next turrets."),
    "elder spawn":       (5, "objective", "Elder is up", "Get vision on Elder now",
                          "Elder executes low-HP enemies — whoever takes it usually wins the next fight."),
}


# champ select
DRAFT_QUESTIONS = ["What runes should I take?", "Which summoners?", "How does our comp win?"]
_TIMER_PHASES = {"PLANNING": "planning", "BAN_PICK": "picks & bans", "FINALIZATION": "finalizing",
                 "GAME_STARTING": "game starting"}


def parse_draft(session: dict, static: dict | None) -> dict:
    """Boil an LCU /lol-champ-select/v1/session down to what the coach needs. Champion and
    spell ids become names via Data Dragon static data ("#<id>" if it isn't loaded)."""
    champs = (static or {}).get("champions", {})
    spells = (static or {}).get("spells", {})

    def champ(cid):
        if not cid:
            return None
        c = champs.get(str(cid))
        return c["name"] if c else f"#{cid}"

    actions = [a for turn in session.get("actions", []) for a in turn]
    locked = {a.get("actorCellId") for a in actions if a.get("type") == "pick" and a.get("completed")}
    bans = [champ(a.get("championId")) for a in actions
            if a.get("type") == "ban" and a.get("completed") and a.get("championId")]

    me_cell, me, allies = session.get("localPlayerCellId"), None, []
    for p in session.get("myTeam", []):
        entry = {"position": (p.get("assignedPosition") or "").lower(),
                 "champion": champ(p.get("championId") or p.get("championPickIntent")),
                 "locked": p.get("cellId") in locked}
        if p.get("cellId") == me_cell:
            me = {**entry, "spells": [spells.get(str(p.get(k)), f"#{p.get(k)}")
                                      for k in ("spell1Id", "spell2Id") if p.get(k)]}
        else:
            allies.append(entry)
    return {
        "timer": (session.get("timer") or {}).get("phase", ""),
        "me": me or {"position": "", "champion": None, "locked": False, "spells": []},
        "allies": allies,
        "enemies": [n for n in (champ(p.get("championId")) for p in session.get("theirTeam", [])) if n],
        "bans": bans,
    }


def _format_loadout(adv: dict, static: dict | None) -> tuple[str, str] | None:
    """Coach draft reply → (card action "Keystone · Spell + Spell", card detail: the rune pages + why),
    or None if it's missing or names a keystone that doesn't exist this patch (stale model knowledge)."""
    runes, summs = adv.get("runes"), adv.get("summoners")
    if not isinstance(runes, dict) or not runes.get("keystone"):
        return None
    keystones = {k for tree in (static or {}).get("runes", {}).values() for k in tree[0]}
    if keystones and runes["keystone"] not in keystones:
        print(f"[coach] draft: ignoring unknown keystone {runes['keystone']!r}")
        return None
    action = runes["keystone"] + (" · " + " + ".join(map(str, summs)) if isinstance(summs, list) and summs else "")
    lines = [f"{runes.get('primary_tree', '')}: " + ", ".join(runes.get("primary") or []),
             f"{runes.get('secondary_tree', '')}: " + ", ".join(runes.get("secondary") or [])]
    if adv.get("why"):
        lines.append(str(adv["why"]))
    return action, "\n".join(lines)



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


GENERIC_QUESTIONS = ["What should I do now?", "Where should I be now?", "What should I buy next?"]


# question topic → keywords. A suggestion list keeps one question per topic (the first: Gemini's,
# else the rule one), so "Why did I die?" and "Was I overextended?" never both show. Order matters:
# the first matching topic wins.
_QUESTION_TOPICS = [
    ("death", ("die", "died", "death", "dead", "killed", "kill me", "overextend", "caught", "out of position",
               "gank", "that fight", "won that", "lose that", "lost that")),
    ("dragon", ("dragon", "drake", "soul", "elder")),
    ("baron", ("baron", "nashor")),
    ("herald", ("herald",)),
    ("grubs", ("grub",)),
    ("structures", ("turret", "tower", "inhib", "base")),
    ("build", ("buy", "item", "build", "gold", "back", "recall")),
    ("farm", ("cs", "farm", "wave", "minion")),
    ("lead", ("lead", "ahead", "snowball")),
]


def question_topic(q: str) -> str | None:
    """Coarse topic of a suggested question, or None if it matches none (never deduped)."""
    q = q.lower()
    for topic, keys in _QUESTION_TOPICS:  # whole words, plus plural / -ed / -ing
        if any(re.search(rf"\b{re.escape(k)}(s|es|ed|ing)?\b", q) for k in keys):
            return topic
    return None


def _mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def suggest_questions(ctx: dict, limit: int = 5) -> list[str]:
    """Rule-based questions the player probably wants answered, most specific first.

    Takes recent_context() output. Returns at most `limit` — possibly none: no generic
    padding (empty slots show as "--" rather than filler).
    """
    qs = []
    if ctx["my_deaths"]:
        qs.append("Why did I die?")  # covers "overextended?" / "could I have won?" — one per topic
    for obj in reversed(ctx["objectives"]):  # newest first
        q = _OBJECTIVE_QUESTIONS.get((obj["type"], obj["by"]))
        if q and q not in qs:
            qs.append(q)
    if ctx["my_takedowns"]:
        qs.append("How do I use this lead?")
    return qs[:limit]


class LeagueModel(GameModel):
    def __init__(self):
        super().__init__([], [])
        self.pinned_questions = list(GENERIC_QUESTIONS)
        self.game_id = 0  # bumped by new_game(), so the controller can reset its own per-game state

        # League client (LCU) phase + champ select. The controller's poller writes lcu_phase /
        # champ_select_raw and the static data; the main thread folds them in (set_phase /
        # ingest_draft). draft_advice = (draft signature, coach reply), written by a coach worker.
        self.phase: str | None = None
        self.lcu_phase: str | None = None
        self.champ_select_raw: dict | None = None
        self.static: dict | None = None
        self.draft: dict | None = None
        self.draft_advice: tuple | None = None
        self._draft_applied = None
        self.new_game()

    def new_game(self):
        """Reset everything that belongs to one game. Riot restarts EventIDs at 0 each game
        and checkpoints latch once, so without this a second game would be ignored."""
        self.game_id += 1
        self.checkpoints = copy.deepcopy(CHECKPOINTS)  # fresh .fired latches
        self.reset_tips()
        self.my_position = ""  # from champ select; outlives it (the Live API's position is often empty)
        self.player = None  # raw get_player_profile() for this game, written by the controller's poller

        # accumulators for folding the raw Riot event feed into snapshots
        self.seen_event_ids = set()
        self.seen_event_names: set[str] = set()
        self.dragon_count = 0
        self.last_dragon_time: float | None = None
        self.last_baron_time: float | None = None
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
        if stats.get("gameTime", 0.0) < self.clock - NEW_GAME_CLOCK_DROP_S:
            self.new_game()  # clock went backwards: a new game started (fallback when the client API is unavailable)
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
            elif name == "BaronKill":
                self.last_baron_time = ev.get("EventTime", self.clock)
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
        if self.phase == "ChampSelect":
            return self._draft_lines()
        s = self.live_state
        if s is None:
            return [f"League client · {self.phase}" if self.phase else "Riot API · no live game"]
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
        clock as m:ss and every objective timer (from the event feed, not guessed)."""
        return {"clock": _mmss(self.clock), "player": self.player_context(),
                "timers": self.objective_timers(), **self.recent_context()}

    def objective_timers(self) -> dict:
        """Where each objective stands right now, e.g. {"dragon": "spawns at 11:30",
        "grubs": "alive until 14:45 (if not taken)", "herald": "spawns at 15:00", ...}."""
        now, seen = self.clock, self.seen_event_names

        def at(spawn):
            return "alive now" if now >= spawn else f"spawns at {_mmss(spawn)}"

        timers = {}
        dragon = self._next_dragon_spawn()
        timers["dragon"] = at(dragon) if dragon is not None else "soul/elder phase (timer not tracked)"
        if "HordeKill" in seen:
            timers["grubs"] = "taken"
        elif now >= GRUBS_DESPAWN_S:
            timers["grubs"] = "gone (despawned 14:45)"
        else:
            timers["grubs"] = f"alive until {_mmss(GRUBS_DESPAWN_S)}" if now >= GRUBS_SPAWN_S else at(GRUBS_SPAWN_S)
        timers["herald"] = "taken" if "HeraldKill" in seen else at(HERALD_SPAWN_S)
        baron = BARON_SPAWN_S if self.last_baron_time is None else self.last_baron_time + BARON_RESPAWN_S
        timers["baron"] = at(baron)
        return timers

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

        def offer(*args, ttl, category, action=""):
            tip = self.offer_tip(*args, now=now, ttl=ttl, category=category, action=action)
            if tip:
                new.append(tip)

        s = self.live_state
        if s:
            me = next((self.roster[n] for n in self.my_names if n in self.roster), {})
            minutes = now / 60
            cpm = s["cs"] / minutes if minutes else 0
            position = (me.get("position") or self.my_position).upper()
            warn, aim = CS_TARGETS[self.bracket]
            if now >= CS_CHECK_FROM_S and position != "UTILITY" and cpm < warn:
                gap = round(aim * minutes - s["cs"])
                offer("cs_low", "CS is low", f"{s['cs']} CS at {_mmss(now)} ({cpm:.1f}/min) — {gap} CS "
                      f"(~{gap * MINION_GOLD}g) behind {aim:g}/min.", 1, ttl=120, category="farm",
                      action="Catch every wave until your next recall — no roams")
            elif cpm >= warn + 0.5:
                self.clear_tip("cs_low", now)
            if s["g"] >= GOLD_UNSPENT:
                offer("gold", "Gold to spend", f"{s['g']}g unspent is a component you're fighting without.",
                      1, ttl=120, category="economy", action="Recall on the next crash and buy")
            elif s["g"] < GOLD_UNSPENT - 500:
                self.clear_tip("gold", now)

        spawn = self._next_dragon_spawn()
        if spawn is not None and 0 < spawn - now <= DRAGON_HEADS_UP_S:
            offer(f"dragon_soon@{round(spawn)}", f"Dragon at {_mmss(spawn)}",
                  f"It spawns in ~{round(spawn - now)}s; the team that's there first with prio gets it.",
                  5, ttl=spawn - now + 30, category="objective", action="Shove your wave now, then walk to dragon")

        ctx = self.recent_context()
        for d in ctx["my_deaths"]:
            killer, helpers = d["killer"] or "?", d["assisters"]
            if (killer or "").startswith("Turret"):
                action, why = "Don't dive without a wave under their turret", f"The turret killed you at {_mmss(d['t'])}."
            elif len(helpers) >= 2:
                action = "Don't push past river without seeing their jungler"
                why = f"{killer} + {', '.join(helpers)} collapsed at {_mmss(d['t'])} — a gank, not a duel."
            elif helpers:
                action = "Count enemies on the map before trading"
                why = f"{killer} + {helpers[0]} killed you at {_mmss(d['t'])} — it was a 2v1."
            else:
                action = f"Check {killer}'s level and items before the next trade"
                why = f"You lost a 1v1 to {killer} at {_mmss(d['t'])}."
            offer(f"death@{d['t']}", "Why you died", why, 4, ttl=d["t"] + 60 - now,
                  category="death", action=action)
        for o in ctx["objectives"]:
            if o["by"] == "enemy" and o["type"] in _EVENT_TIPS:
                headline, action, why = _EVENT_TIPS[o["type"]]
                offer(f"{o['type']}@{o['t']}", headline, why, 4, ttl=o["t"] + 60 - now,
                      category="macro", action=action)
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
        priority, category, headline, action, detail = _CHECKPOINT_TIPS[cp.title]
        return self.offer_tip(f"cp:{cp.title}", headline, detail, priority, category=category, action=action,
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

    # ── champ select ──
    def set_phase(self, phase: str | None):
        """Follow the client's gameflow phase. A new champ select starts a new game; its
        tips are cleared again when it ends."""
        if phase == self.phase:
            return
        if self.phase == "ChampSelect":
            self.drop_tips("draft:")
            self.draft = self.draft_advice = self._draft_applied = None
        if phase == "ChampSelect" and self.phase is not None:
            self.new_game()  # each champ select starts a game (also after a dodge)
        self.phase = phase
        self.pinned_questions = list(DRAFT_QUESTIONS if phase == "ChampSelect" else GENERIC_QUESTIONS)

    @property
    def draft_signature(self) -> tuple | None:
        """What the coach's draft advice depends on: my champion + both teams' champions."""
        d = self.draft
        if not d:
            return None
        return (d["me"]["champion"], tuple(a["champion"] for a in d["allies"]), tuple(d["enemies"]))

    def ingest_draft(self, session: dict) -> bool:
        """Fold a champ select session in. Returns True if the picks changed — the old
        advice is dropped and instant rule-based comp reads are offered instead."""
        before = self.draft_signature
        self.draft = parse_draft(session, self.static)
        if self.draft["me"]["position"]:
            self.my_position = self.draft["me"]["position"]
        if self.draft_signature == before:
            return False
        self.drop_tips("draft:")
        self._draft_applied = None
        for kind, headline, action, detail, category in self._draft_rule_reads():
            self.offer_tip(f"draft:rule:{kind}", headline, detail, 3, now=self.clock, ttl=1e9,
                           category=category, action=action)
        return True

    def _draft_rule_reads(self) -> list[tuple[str, str, str, str]]:
        """Instant comp reads from Data Dragon tags / damage ratings: (kind, headline, action, why, category)."""
        champs = {c["name"]: c for c in (self.static or {}).get("champions", {}).values()}
        d = self.draft
        mine = [n for n in [d["me"]["champion"], *(a["champion"] for a in d["allies"])] if n in champs]
        theirs = [n for n in d["enemies"] if n in champs]
        picking = not d["me"]["locked"]
        reads = []

        def physical(names):
            return [n for n in names if champs[n]["attack"] > champs[n]["magic"]]

        def magic(names):
            return [n for n in names if champs[n]["magic"] > champs[n]["attack"]]

        if len(mine) >= 4:
            if not magic(mine):
                reads.append(("ad", "Team is all AD",
                              "Pick a magic-damage champion" if picking else "Build armor pen; look for picks",
                              f"{len(mine)} of {len(mine)} deal physical damage — the enemy can stack armor.", "ally"))
            elif not physical(mine):
                reads.append(("ap", "Team is all AP",
                              "Pick a physical-damage champion" if picking else "Build magic pen; look for picks",
                              f"{len(mine)} of {len(mine)} deal magic damage — the enemy can stack MR.", "ally"))
            if not any("Tank" in champs[n]["tags"] for n in mine) and \
                    sum("Fighter" in champs[n]["tags"] for n in mine) <= 1:
                reads.append(("frontline", "No frontline",
                              "Pick a tank or bruiser" if picking else "Play for picks and poke, not long fights",
                              "Nobody on your team can soak damage or start fights.", "ally"))
        assassins = [n for n in theirs if "Assassin" in champs[n]["tags"]]
        if len(assassins) >= 2:
            reads.append(("assassins", "Enemy has assassins", "Group up and don't face-check brush",
                          f"{' and '.join(assassins)} want to catch you alone.", "enemy"))
        if len(theirs) >= 4:
            if not magic(theirs):
                reads.append(("enemy_ad", "Enemy mostly AD", "Rush Plated Steelcaps and an armor item",
                              "Almost all their damage is physical.", "enemy"))
            elif not physical(theirs):
                reads.append(("enemy_ap", "Enemy mostly magic", "Rush Mercury's Treads and an MR item",
                              "Almost all their damage is magic.", "enemy"))
        return reads

    # ── levels of play / experience ──
    @property
    def bracket(self) -> str:
        """Level of play: "new" | "low" | "mid" | "high". COACH_RANK (e.g. "gold") overrides;
        otherwise solo rank, then flex, then account level; unknown → "low"."""
        override = os.environ.get("COACH_RANK", "").strip().upper()
        if override:
            return _BRACKETS.get(override.split()[0], "new" if override == "NEW" else "low")
        p = self.player or {}
        rank = p.get("solo") or p.get("flex")
        if rank:
            return _BRACKETS.get(rank.split()[0], "low")
        if p.get("account_level") is not None and p["account_level"] < NEW_ACCOUNT_LEVEL:
            return "new"
        return "low"

    def my_champion(self) -> str | None:
        if self.phase == "ChampSelect" and self.draft:
            return self.draft["me"]["champion"]
        return next((self.roster[n]["champion"] for n in self.my_names if n in self.roster), None)

    def champ_experience(self) -> str | None:
        """Experience on the current champion from mastery points; COACH_EXPERIENCE overrides."""
        override = os.environ.get("COACH_EXPERIENCE", "").strip()
        if override:
            return override
        champ = self.my_champion()
        ids = {c["name"]: cid for cid, c in (self.static or {}).get("champions", {}).items()}
        if not champ or champ not in ids or not self.player:
            return None
        points = self.player.get("mastery", {}).get(ids[champ], 0)
        label = next((lbl for limit, lbl in MASTERY_STEPS if points < limit), "main")
        return f"{label} ({points // 1000}k mastery)"

    def player_context(self) -> dict:
        """Who the coach is talking to — sets the depth of advice."""
        p = self.player or {}
        ctx = {"level_of_play": _BRACKET_LABELS[self.bracket]}
        if p.get("solo") or p.get("flex"):
            tier, *division = (p.get("solo") or p.get("flex")).split()
            ctx["rank"] = " ".join([tier.title(), *division])  # "Silver III"
        if p.get("account_level") is not None:
            ctx["account_level"] = p["account_level"]
        exp = self.champ_experience()
        if exp:
            ctx["champion_experience"] = exp
        return ctx

    def draft_context(self) -> dict:
        """The champ select as the coach sees it (stands in for live state + recent_context)."""
        d = self.draft or parse_draft({}, None)
        me = d["me"]
        return {
            "phase": "champ select (" + _TIMER_PHASES.get(d["timer"], d["timer"].lower() or "?") + ")",
            "my_position": me["position"] or "unknown",
            "my_champion": (me["champion"] or "not picked yet") + ("" if me["locked"] or not me["champion"] else " (hovering)"),
            "my_spells": me["spells"],
            "allies": [f"{a['champion'] or '?'} ({a['position'] or '?'})" for a in d["allies"]],
            "enemies": d["enemies"] or "not visible yet",
            "bans": d["bans"],
            "player": self.player_context(),
        }

    def loadout_options(self) -> dict:
        """Current-patch runes + summoner spells, so the coach only picks ones that exist."""
        s = self.static or {}
        return {"rune_options": s.get("runes", {}), "summoner_options": sorted(s.get("spells", {}).values())}

    def apply_draft_advice(self):
        """Main thread: turn a landed coach draft reply into tips (loadout + comp reads),
        replacing the rule reads — but only if it's for the current picks."""
        if not self.draft_advice or self.draft_advice[0] != self.draft_signature \
                or self._draft_applied == self.draft_advice[0]:
            return
        sig, adv = self.draft_advice
        self._draft_applied = sig
        reads = [r for r in (adv.get("reads") or []) if isinstance(r, dict) and r.get("headline")][:3]
        loadout = _format_loadout(adv, self.static)  # (action, detail) or None
        if not reads and not loadout:
            return
        self.drop_tips("draft:")
        if loadout:
            self.offer_tip("draft:loadout", "Runes & summs", loadout[1], 5, now=self.clock, ttl=1e9,
                           category="loadout", action=loadout[0])
        for i, r in enumerate(reads):
            self.offer_tip(f"draft:read:{i}", str(r["headline"]), str(r.get("why") or r.get("detail") or ""), 3,
                           now=self.clock, ttl=1e9, category="enemy" if r.get("side") == "enemy" else "ally",
                           action=str(r.get("action") or ""))

    def _draft_lines(self) -> list[str]:
        d = self.draft
        if not d:
            return ["Champ select · loading…"]
        me = d["me"]
        you = (me["champion"] or "—") + ("" if me["locked"] or not me["champion"] else " (hover)")
        lines = [f"Champ select · {_TIMER_PHASES.get(d['timer'], d['timer'].lower())}",
                 f"You: {you} · {me['position'] or '?'}"]
        if me["spells"]:
            lines.append("Spells: " + " + ".join(me["spells"]))
        lines.append("Allies: " + ", ".join(a["champion"] or "…" for a in d["allies"]))
        lines.append("Enemies: " + (", ".join(d["enemies"]) or "hidden"))
        if d["bans"]:
            lines.append("Bans: " + ", ".join(d["bans"]))
        return lines

    def current_suggestions(self, limit: int = 5) -> list[str]:
        """Up to `limit` situational questions, then the always-there pinned_questions.
        Situational: fresh background LLM ones first, then rules — one per topic
        (question_topic), none repeating a pinned question's topic. Fewer than `limit` is fine — the panel shows the empty
        slots as "--". llm_suggestions is (game time generated, questions). In champ
        select the situational ones are matchup questions for the visible enemies."""
        if self.phase == "ChampSelect":
            qs = [f"How do I play vs {e}?" for e in (self.draft or {}).get("enemies", [])]
        else:
            qs = []
            if self.llm_suggestions and self.clock - self.llm_suggestions[0] <= LLM_SUGGESTION_TTL:
                qs = list(self.llm_suggestions[1])
            qs += suggest_questions(self.recent_context(), limit)
        seen = {q.lower() for q in self.pinned_questions}
        topics = {question_topic(q) for q in self.pinned_questions} - {None}
        situational = []
        for q in qs:
            topic = question_topic(q)
            if q.lower() in seen or (topic and topic in topics):
                continue  # same question, or a narrower one on a topic already offered
            situational.append(q)
            seen.add(q.lower())
            if topic:
                topics.add(topic)
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
