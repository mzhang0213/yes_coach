"""Headless tests for the League checkpoint feature.

Imports only server.resources.league.league_model (Qt-free — no window is
constructed). Run from anywhere:

    python3 testing/checkpoints/test_checkpoints.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from server.resources.league.league_model import (
    ClockCheckpoint,
    DragonCheckpoint,
    ElderCheckpoint,
    EventCheckpoint,
    LeagueModel,
    LeagueSnapshot,
    CHECKPOINTS,
    DRAFT_QUESTIONS,
    GENERIC_QUESTIONS,
    parse_draft,
    suggest_questions,
)
from server.resources.game_model import TIP_COOLDOWN_S


def snap(clock=0.0, events=(), dragons=0, since_dragon=None):
    return LeagueSnapshot(
        clock_seconds=clock,
        seen_event_names=frozenset(events),
        dragon_count=dragons,
        seconds_since_last_dragon=since_dragon,
    )


def test_clock_checkpoint():
    cp = ClockCheckpoint("t", 900)
    assert cp.reached(snap(clock=899)) is False
    assert cp.reached(snap(clock=900)) is True
    assert cp.reached(snap(clock=1000)) is True


def test_event_checkpoint():
    cp = EventCheckpoint("t", "InhibKilled")
    assert cp.reached(snap(events=())) is False
    assert cp.reached(snap(events=("ChampionKill",))) is False
    assert cp.reached(snap(events=("InhibKilled",))) is True


def test_elder_checkpoint():
    cp = ElderCheckpoint("t", 360)
    assert cp.reached(snap(since_dragon=None)) is False  # no dragon yet
    assert cp.reached(snap(since_dragon=359)) is False
    assert cp.reached(snap(since_dragon=360)) is True


def test_dragon_checkpoint():
    cp = DragonCheckpoint("t", 4)
    assert cp.reached(snap(dragons=3)) is False
    assert cp.reached(snap(dragons=4)) is True
    assert cp.reached(snap(dragons=5)) is True


def test_ingest_dedup_and_elder_exclusion():
    m = LeagueModel()
    events = {"Events": [
        {"EventID": 1, "EventName": "DragonKill", "EventTime": 600.0, "DragonType": "Fire"},
        {"EventID": 2, "EventName": "DragonKill", "EventTime": 700.0, "DragonType": "Elder"},  # excluded
        {"EventID": 3, "EventName": "InhibKilled", "EventTime": 900.0},
    ]}

    s1 = m.ingest({"gameTime": 1000.0}, events)
    assert s1.dragon_count == 1                      # elder not counted
    assert "InhibKilled" in s1.seen_event_names
    assert "DragonKill" in s1.seen_event_names
    assert s1.seconds_since_last_dragon == 400.0     # 1000 - 600

    # same feed again (Riot returns the whole list every poll) -> no double count
    s2 = m.ingest({"gameTime": 1100.0}, events)
    assert s2.dragon_count == 1                       # dedup by EventID
    assert s2.seconds_since_last_dragon == 500.0      # 1100 - 600


def test_ingest_no_dragon_yet():
    m = LeagueModel()
    s = m.ingest({"gameTime": 300.0}, {"Events": []})
    assert s.dragon_count == 0
    assert s.seconds_since_last_dragon is None


def test_latch_fires_once():
    m = LeagueModel()
    # 1000s (16:40): reaches "15 min ff" (900) but not "first baron spawn" (1500)
    s = snap(clock=1000.0)
    newly1 = [cp.title for cp in m.evaluate_checkpoints(s)]
    assert "15 min ff" in newly1
    assert "first baron spawn" not in newly1
    assert "15 min ff" in m.reached_log

    newly2 = [cp.title for cp in m.evaluate_checkpoints(s)]
    assert "15 min ff" not in newly2                  # latched, not re-fired


def test_hardcoded_checkpoints_present():
    titles = {cp.title for cp in LeagueModel().checkpoints}
    assert titles == {
        "15 min ff", "void grubs spawn", "rift herald spawn", "first baron spawn",
        "first inhib", "void grubs taken", "rift herald taken", "baron taken",
        "elder spawn",
    }


# ── recent_context ─────────────────────────────────────────────────────────

ROSTER = [
    {"riotId": "Me#NA1", "riotIdGameName": "Me", "summonerName": "Me",
     "championName": "Ahri", "team": "ORDER"},
    {"riotId": "Buddy#NA1", "riotIdGameName": "Buddy", "summonerName": "Buddy",
     "championName": "Vi", "team": "ORDER"},
    {"riotId": "Foe#EUW", "riotIdGameName": "Foe", "summonerName": "Foe",
     "championName": "Zed", "team": "CHAOS"},
    {"riotId": "Jungler#EUW", "riotIdGameName": "Jungler", "summonerName": "Jungler",
     "championName": "Lee Sin", "team": "CHAOS"},
]


def rostered_model():
    m = LeagueModel()
    m.set_roster("Me#NA1", ROSTER)
    return m


def test_recent_context_death_labels_champions():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 480.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": ["Jungler"]},
    ]})
    ctx = m.recent_context()
    assert ctx["t"] == 500
    assert ctx["my_deaths"] == [{"t": 480, "killer": "Zed", "assisters": ["Lee Sin"]}]
    assert ctx["my_takedowns"] == []


def test_recent_context_takedown_as_assister():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 490.0,
         "KillerName": "Buddy", "VictimName": "Foe", "Assisters": ["Me"]},
        {"EventID": 2, "EventName": "ChampionKill", "EventTime": 495.0,  # not involved
         "KillerName": "Buddy", "VictimName": "Jungler", "Assisters": []},
    ]})
    ctx = m.recent_context()
    assert ctx["my_takedowns"] == [{"t": 490, "victim": "Zed"}]
    assert ctx["my_deaths"] == []


def test_recent_context_window_prunes_old_events():
    m = rostered_model()
    feed = {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 100.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []},
    ]}
    m.ingest({"gameTime": 120.0}, feed)
    assert len(m.recent_context()["my_deaths"]) == 1
    m.ingest({"gameTime": 161.0}, feed)                # 61 s later, same full feed
    assert m.recent_context()["my_deaths"] == []       # pruned and not re-added


def test_recent_context_objective_sides():
    m = rostered_model()
    m.ingest({"gameTime": 900.0}, {"Events": [
        {"EventID": 1, "EventName": "DragonKill", "EventTime": 870.0,
         "DragonType": "Fire", "Stolen": "False", "KillerName": "Jungler", "Assisters": []},
        {"EventID": 2, "EventName": "BaronKill", "EventTime": 880.0,
         "Stolen": "True", "KillerName": "Buddy", "Assisters": []},
        # our (T1 = ORDER) turret falls to a minion → enemy took it
        {"EventID": 3, "EventName": "TurretKilled", "EventTime": 890.0,
         "TurretKilled": "Turret_T1_C_05_A", "KillerName": "Minion_T200L0S16N0040"},
        {"EventID": 4, "EventName": "InhibKilled", "EventTime": 895.0,
         "InhibKilled": "Barracks_T2_L1", "KillerName": "Me"},
    ]})
    objs = m.recent_context()["objectives"]
    assert objs == [
        {"t": 870, "type": "dragon", "by": "enemy", "detail": "Fire"},
        {"t": 880, "type": "baron", "by": "ally", "stolen": True},
        {"t": 890, "type": "turret", "by": "enemy"},
        {"t": 895, "type": "inhib", "by": "ally"},
    ], objs


def test_recent_context_without_roster():
    m = LeagueModel()                                  # roster never set
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 480.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []},
        {"EventID": 2, "EventName": "DragonKill", "EventTime": 490.0,
         "DragonType": "Water", "KillerName": "Foe"},
    ]})
    ctx = m.recent_context()
    assert ctx["my_deaths"] == []                      # can't tell who "me" is
    assert ctx["objectives"] == [{"t": 490, "type": "dragon", "by": "unknown", "detail": "Water"}]


# ── suggestions ────────────────────────────────────────────────────────────

def ctx(deaths=(), takedowns=(), objectives=()):
    return {"t": 600, "my_deaths": list(deaths), "my_takedowns": list(takedowns),
            "objectives": list(objectives)}


def test_suggest_nothing_happened_is_empty_not_filler():
    assert suggest_questions(ctx()) == []


def test_suggest_death_is_one_question():
    for assisters in ([], ["Lee Sin", "Vi"]):
        assert suggest_questions(ctx(deaths=[{"t": 1, "killer": "Zed", "assisters": assisters}])) == ["Why did I die?"]


def test_suggest_objectives_newest_first_and_capped():
    qs = suggest_questions(ctx(
        deaths=[{"t": 1, "killer": "Zed", "assisters": []}],
        takedowns=[{"t": 2, "victim": "Zed"}],
        objectives=[
            {"t": 3, "type": "dragon", "by": "enemy"},
            {"t": 4, "type": "turret", "by": "ally"},
            {"t": 5, "type": "baron", "by": "unknown"},   # unknown side → no question
        ]))
    assert qs == ["Why did I die?", "Where do I go after turret?", "Should I have contested dragon?",
                  "How do I use this lead?"]


def test_suggest_trigger_on_my_death_and_objectives_only():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 490.0,
         "KillerName": "Me", "VictimName": "Foe", "Assisters": []},   # my kill: no trigger
    ]})
    assert m.suggest_trigger is None
    m.ingest({"gameTime": 510.0}, {"Events": [
        {"EventID": 2, "EventName": "ChampionKill", "EventTime": 505.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []},
    ]})
    assert m.suggest_trigger["EventID"] == 2


def test_suggest_trigger_ignores_old_history_on_launch():
    m = rostered_model()
    # app started mid-game: feed holds a death from long ago
    m.ingest({"gameTime": 1200.0}, {"Events": [
        {"EventID": 1, "EventName": "DragonKill", "EventTime": 300.0, "KillerName": "Foe"},
    ]})
    assert m.suggest_trigger is None


def test_current_suggestions_prefers_fresh_llm():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 490.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []},
    ]})
    m.llm_suggestions = (490.0, ["Why did Zed kill me?", "why did i die?"])
    qs = m.current_suggestions()
    assert qs == ["Why did Zed kill me?"] + GENERIC_QUESTIONS   # one death question, Gemini's first
    assert "Why did I die?" not in qs

    m.ingest({"gameTime": 560.0}, {"Events": []})       # 70 s after: LLM ones are stale
    assert m.current_suggestions() == GENERIC_QUESTIONS  # death left the window → 5 × "--" + defaults


def test_current_suggestions_capped_at_five():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 490.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []}]})
    m.llm_suggestions = (499.0, ["what should i do now?", "Is dragon worth it?", "How's my CS?",
                                 "Who to watch?", "Can I 1v1 Zed?", "Where's their jungler?"])
    assert m.current_suggestions() == ["Is dragon worth it?", "How's my CS?", "Who to watch?",
                                       "Can I 1v1 Zed?", "Where's their jungler?"] + GENERIC_QUESTIONS


def test_one_question_per_topic():
    m = rostered_model()
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 490.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []}]})
    m.llm_suggestions = (499.0, ["Why did I die?", "Was I overextended?", "Could I have won that fight?",
                                 "Should we take dragon?", "Is the drake worth contesting?",
                                 "Should I buy armor?", "Can I dive bot?"])
    assert m.current_suggestions() == ["Why did I die?", "Should we take dragon?", "Can I dive bot?"] \
        + GENERIC_QUESTIONS   # build topic is already covered by the pinned "What should I buy next?"


def test_question_topic_whole_words():
    from server.resources.league.league_model import question_topic
    assert question_topic("Should I back now?") == "build"
    assert question_topic("How do I hit their backline?") is None   # "back" ≠ "backline"
    assert question_topic("Was I overextended?") == "death"
    assert question_topic("Are grubs worth it?") == "grubs"


def test_current_suggestions_llm_expire_30s_after_generation():
    m = rostered_model()
    m.ingest({"gameTime": 330.0}, {"Events": []})
    m.llm_suggestions = (300.0, ["Clear wave for dragon?"])
    assert "Clear wave for dragon?" in m.current_suggestions()
    m.ingest({"gameTime": 331.0}, {"Events": []})
    assert "Clear wave for dragon?" not in m.current_suggestions()


# ── coach_context ──────────────────────────────────────────────────────────

def test_coach_context_clock_and_first_dragon():
    m = rostered_model()
    m.ingest({"gameTime": 245.0}, {"Events": []})
    ctx = m.coach_context()
    assert ctx["clock"] == "4:05" and ctx["timers"]["dragon"] == "spawns at 5:00"
    assert ctx["t"] == 245 and "my_deaths" in ctx   # still carries recent_context()
    m.ingest({"gameTime": 360.0}, {"Events": []})
    assert m.coach_context()["timers"]["dragon"] == "alive now"


def test_coach_context_dragon_respawn_after_kill():
    m = rostered_model()
    m.ingest({"gameTime": 400.0}, {"Events": [
        {"EventID": 1, "EventName": "DragonKill", "EventTime": 390.0, "KillerName": "Buddy",
         "DragonType": "Fire", "Stolen": "False"},
    ]})
    assert m.coach_context()["timers"]["dragon"] == "spawns at 11:30"


def test_coach_context_no_dragon_timer_after_four():
    m = rostered_model()
    m.ingest({"gameTime": 2000.0}, {"Events": [
        {"EventID": i, "EventName": "DragonKill", "EventTime": 300.0 * i, "KillerName": "Buddy",
         "DragonType": "Fire", "Stolen": "False"} for i in range(1, 5)]})
    assert m.coach_context()["timers"]["dragon"].startswith("soul/elder")


def test_tip_categories():
    m = tip_model(290.0, {"cs": 0, "g": 1700}, [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 280.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": []},
        {"EventID": 2, "EventName": "TurretKilled", "EventTime": 285.0, "KillerName": "Foe",
         "TurretKilled": "Turret_T1_L_03_A"}])
    m.update_tips()
    assert {t.kind.split("@")[0]: t.category for t in m.tips} == {
        "gold": "economy", "dragon_soon": "objective", "death": "death", "turret": "macro"}
    m = tip_model(600.0, {"cs": 10, "g": 0}); m.update_tips()
    assert m.tips[0].category == "farm"
    grubs = next(cp for cp in CHECKPOINTS if cp.title == "void grubs spawn")
    assert tip_model(365.0, {"cs": 60}).checkpoint_tip(grubs).category == "objective"


def test_objective_timers_current_patch():
    m = rostered_model()
    m.ingest({"gameTime": 300.0}, {"Events": []})
    assert m.objective_timers() == {"dragon": "alive now", "grubs": "spawns at 8:00",
                                    "herald": "spawns at 15:00", "baron": "spawns at 20:00"}
    m.ingest({"gameTime": 600.0}, {"Events": []})
    assert m.objective_timers()["grubs"] == "alive until 14:45"
    m.ingest({"gameTime": 900.0}, {"Events": []})
    assert m.objective_timers()["grubs"].startswith("gone") and m.objective_timers()["herald"] == "alive now"
    m.ingest({"gameTime": 1300.0}, {"Events": [
        {"EventID": 1, "EventName": "HeraldKill", "EventTime": 960.0},
        {"EventID": 2, "EventName": "BaronKill", "EventTime": 1250.0}]})
    t = m.objective_timers()
    assert t["herald"] == "taken" and t["baron"] == "spawns at 26:50"   # 20:50 + 6:00 respawn


def test_checkpoint_clock_times_current_patch():
    times = {cp.title: cp.indicator for cp in CHECKPOINTS if isinstance(cp, ClockCheckpoint)}
    assert times["void grubs spawn"] == 480 and times["rift herald spawn"] == 900
    assert times["first baron spawn"] == 1200


# ── champ select ───────────────────────────────────────────────────────────

STATIC = {
    "champions": {
        "103": {"name": "Ahri", "tags": ["Mage", "Assassin"], "attack": 3, "magic": 8},
        "122": {"name": "Darius", "tags": ["Fighter", "Tank"], "attack": 9, "magic": 0},
        "64": {"name": "Lee Sin", "tags": ["Fighter", "Assassin"], "attack": 8, "magic": 0},
        "22": {"name": "Ashe", "tags": ["Marksman", "Support"], "attack": 7, "magic": 2},
        "412": {"name": "Thresh", "tags": ["Support", "Fighter"], "attack": 5, "magic": 6},
        "238": {"name": "Zed", "tags": ["Assassin"], "attack": 9, "magic": 1},
        "91": {"name": "Talon", "tags": ["Assassin"], "attack": 9, "magic": 1},
        "51": {"name": "Caitlyn", "tags": ["Marksman"], "attack": 8, "magic": 2},
        "86": {"name": "Garen", "tags": ["Fighter", "Tank"], "attack": 7, "magic": 1},
        "157": {"name": "Yasuo", "tags": ["Fighter", "Assassin"], "attack": 8, "magic": 4},
        "67": {"name": "Vayne", "tags": ["Marksman", "Assassin"], "attack": 10, "magic": 1},
    },
    "spells": {"4": "Flash", "14": "Ignite", "3": "Exhaust", "12": "Teleport"},
    "runes": {"Domination": [["Electrocute", "Dark Harvest"], ["Cheap Shot"], ["Eyeball Collection"], ["Ultimate Hunter"]],
              "Sorcery": [["Arcane Comet"], ["Manaflow Band"], ["Transcendence"], ["Scorch"]]},
}


def session(me_champ=103, me_locked=True, allies=(122, 64, 22, 412), enemies=(238, 91, 51, 86), timer="BAN_PICK"):
    team = [{"cellId": 0, "championId": me_champ if me_locked else 0,
             "championPickIntent": 0 if me_locked else me_champ,
             "assignedPosition": "middle", "spell1Id": 4, "spell2Id": 14}]
    team += [{"cellId": i + 1, "championId": c, "assignedPosition": p}
             for i, (c, p) in enumerate(zip(allies, ["top", "jungle", "bottom", "utility"]))]
    picks = [{"actorCellId": c["cellId"], "type": "pick", "completed": True, "championId": c["championId"]}
             for c in team if c["championId"]]
    return {"localPlayerCellId": 0, "myTeam": team,
            "theirTeam": [{"cellId": 5 + i, "championId": c} for i, c in enumerate(enemies)],
            "actions": [[{"actorCellId": 5, "type": "ban", "completed": True, "championId": 157},
                         {"actorCellId": 1, "type": "ban", "completed": True, "championId": 67}], picks],
            "timer": {"phase": timer}}


def draft_model(**kw):
    m = LeagueModel()
    m.static = STATIC
    m.set_phase("ChampSelect")
    m.ingest_draft(session(**kw))
    return m


def test_parse_draft():
    d = parse_draft(session(me_locked=False), STATIC)
    assert d["me"] == {"position": "middle", "champion": "Ahri", "locked": False, "spells": ["Flash", "Ignite"]}
    assert [a["champion"] for a in d["allies"]] == ["Darius", "Lee Sin", "Ashe", "Thresh"]
    assert d["allies"][3] == {"position": "utility", "champion": "Thresh", "locked": True}
    assert d["enemies"] == ["Zed", "Talon", "Caitlyn", "Garen"] and d["bans"] == ["Yasuo", "Vayne"]
    assert parse_draft(session(), None)["me"]["champion"] == "#103"   # static data not loaded yet


def test_draft_rule_reads():
    m = draft_model(enemies=(238, 91))
    assert {t.kind for t in m.tips} == {"draft:rule:assassins"}
    assert "Zed and Talon" in m.tips[0].detail and m.tips[0].category == "enemy"
    m = draft_model(me_champ=51, allies=(64, 238, 22, 91), enemies=(103, 412, 22, 86))   # all AD, no tank
    kinds = {t.kind for t in m.tips}
    assert {"draft:rule:ad", "draft:rule:frontline"} <= kinds, kinds
    assert next(t for t in m.tips if t.kind == "draft:rule:ad").category == "ally"


def test_draft_ingest_only_changes_on_new_picks():
    m = draft_model()
    sig = m.draft_signature
    assert sig == ("Ahri", ("Darius", "Lee Sin", "Ashe", "Thresh"), ("Zed", "Talon", "Caitlyn", "Garen"))
    assert m.ingest_draft(session(timer="FINALIZATION")) is False      # timer tick, same picks
    assert m.ingest_draft(session(enemies=(238, 91, 51, 86, 22))) is True


def test_draft_advice_applies_for_current_picks_only():
    m = draft_model()
    adv = {"reads": [{"headline": "Dive their backline", "detail": "x", "side": "ally"},
                     {"headline": "Zed snowballs", "detail": "y", "side": "enemy"}],
           "runes": {"primary_tree": "Domination", "keystone": "Electrocute",
                     "primary": ["Cheap Shot", "Eyeball Collection", "Ultimate Hunter"],
                     "secondary_tree": "Sorcery", "secondary": ["Manaflow Band", "Transcendence"]},
           "summoners": ["Flash", "Ignite"], "why": "Burst Zed before he burst you."}
    m.draft_advice = (("someone else",), adv)
    m.apply_draft_advice(); assert all(t.kind.startswith("draft:rule") for t in m.tips)   # stale → ignored
    m.draft_advice = (m.draft_signature, adv)
    m.apply_draft_advice()
    tips = {t.kind: t for t in m.tips}
    assert set(tips) == {"draft:loadout", "draft:read:0", "draft:read:1"}           # rule reads replaced
    assert tips["draft:loadout"].category == "loadout" and tips["draft:read:1"].category == "enemy"
    assert tips["draft:loadout"].action == "Electrocute · Flash + Ignite"
    assert tips["draft:loadout"].detail.startswith("Domination: Cheap Shot, Eyeball Collection, Ultimate Hunter")
    assert m.tips_on_offer()[0].kind == "draft:loadout"


def test_draft_advice_with_stale_keystone_drops_loadout_only():
    m = draft_model()
    m.draft_advice = (m.draft_signature, {"reads": [{"headline": "Poke them", "side": "ally"}],
                                          "runes": {"keystone": "Thunderlord's Decree"}})
    m.apply_draft_advice()
    assert {t.kind for t in m.tips} == {"draft:read:0"}


def test_draft_phase_questions_toast_and_cleanup():
    m = draft_model()
    assert m.current_suggestions() == ["How do I play vs Zed?", "How do I play vs Talon?",
                                       "How do I play vs Caitlyn?", "How do I play vs Garen?"] + DRAFT_QUESTIONS
    lines = m.state_lines()
    assert lines[:3] == ["Champ select · picks & bans", "You: Ahri · middle", "Spells: Flash + Ignite"]
    assert lines[-1] == "Bans: Yasuo, Vayne"
    m.set_phase("InProgress")
    assert m.tips == [] and m.draft is None and m.current_suggestions() == GENERIC_QUESTIONS
    assert m.my_position == "middle"                                   # outlives champ select


def test_draft_position_fixes_support_cs_tip():
    m = draft_model(); m.draft["me"]["position"] = "utility"; m.my_position = "utility"
    m.set_phase("InProgress")
    m.live_state = {**LIVE, "cs": 10}
    m.ingest({"gameTime": 600.0}, {"Events": []})                       # no roster position from Live API
    m.update_tips()
    assert "cs_low" not in {t.kind for t in m.tips}


def test_draft_context_for_coach():
    ctx = draft_model(me_locked=False).draft_context()
    assert ctx["my_champion"] == "Ahri (hovering)" and ctx["phase"] == "champ select (picks & bans)"
    assert ctx["allies"][0] == "Darius (top)" and ctx["enemies"][0] == "Zed"


# ── new game reset ─────────────────────────────────────────────────────────

DEATH_EV = {"EventID": 7, "EventName": "ChampionKill", "EventTime": 590.0,
            "KillerName": "Foe", "VictimName": "Me", "Assisters": []}


def play_first_game(m):
    m.set_roster("Me#NA1", ROSTER)
    m.live_state = {**LIVE, "cs": 40, "g": 0}
    m.ingest({"gameTime": 600.0}, {"Events": [DEATH_EV]})
    fired = m.evaluate_checkpoints(m.ingest({"gameTime": 600.0}, {"Events": []}))
    m.update_tips()
    return fired


def test_second_game_via_champ_select_is_fresh():
    m = LeagueModel(); m.static = STATIC
    m.set_phase("InProgress")
    fired = play_first_game(m)
    assert "void grubs spawn" in [cp.title for cp in fired] and m.tips and m.roster
    gid = m.game_id

    m.set_phase("EndOfGame"); m.set_phase("Lobby"); m.set_phase("ChampSelect")
    assert m.game_id == gid + 1
    assert m.roster == {} and m.tips == [] and m.recent_events == [] and m.clock == 0.0
    assert m.dragon_count == 0 and m.llm_suggestions is None and m.seen_event_ids == set()
    m.ingest_draft(session())
    assert m.my_position == "middle"

    m.set_phase("InProgress")                          # game loads: no second reset
    assert m.game_id == gid + 1 and m.my_position == "middle"
    m.set_roster("Me#NA1", ROSTER)
    m.ingest({"gameTime": 600.0}, {"Events": [DEATH_EV]})   # same EventID as last game
    assert m.recent_context()["my_deaths"], "event ignored as already seen"
    fired = m.evaluate_checkpoints(m.ingest({"gameTime": 600.0}, {"Events": []}))
    assert "void grubs spawn" in [cp.title for cp in fired]   # latches reset


def test_checkpoints_not_shared_between_models():
    a, b = LeagueModel(), LeagueModel()
    a.evaluate_checkpoints(a.ingest({"gameTime": 500.0}, {"Events": []}))
    assert [cp.title for cp in b.evaluate_checkpoints(b.ingest({"gameTime": 500.0}, {"Events": []}))] \
        == ["void grubs spawn"]


def test_new_game_fallback_when_clock_goes_backwards():
    m = LeagueModel()
    play_first_game(m)
    gid = m.game_id
    m.ingest({"gameTime": 590.0}, {"Events": []})      # small jitter: same game
    assert m.game_id == gid
    m.ingest({"gameTime": 5.0}, {"Events": [DEATH_EV]})   # no client API, new game started
    assert m.game_id == gid + 1 and m.tips == [] and m.roster == {}
    assert len(m.recent_events) == 1                   # its events are ingested fresh


def test_dodge_restarts_champ_select():
    m = LeagueModel(); m.static = STATIC
    m.set_phase("Lobby"); m.set_phase("ChampSelect"); m.ingest_draft(session())
    gid = m.game_id
    m.set_phase("Lobby"); m.set_phase("ChampSelect")
    assert m.game_id == gid + 1 and m.draft is None and m.my_position == ""


# ── levels of play / experience ────────────────────────────────────────────

PROFILE = {"solo": "SILVER III", "flex": "GOLD IV", "account_level": 211, "mastery": {"103": 74994}}


def test_bracket_from_rank_flex_account_and_override():
    m = LeagueModel()
    assert m.bracket == "low"                                         # unknown
    m.player = PROFILE; assert m.bracket == "low"                     # solo Silver
    m.player = {**PROFILE, "solo": None}; assert m.bracket == "mid"   # falls back to flex Gold
    m.player = {"solo": None, "flex": None, "account_level": 12}; assert m.bracket == "new"
    m.player = {**PROFILE, "solo": "DIAMOND II"}; assert m.bracket == "high"
    os.environ["COACH_RANK"] = "emerald"
    try:
        assert m.bracket == "mid"
    finally:
        del os.environ["COACH_RANK"]


def test_champ_experience_from_mastery():
    m = draft_model()                                                  # Ahri in champ select
    m.player = PROFILE
    assert m.champ_experience() == "experienced on this champion (74k mastery)"
    m.player = {**PROFILE, "mastery": {}}
    assert m.champ_experience() == "new to this champion (0k mastery)"
    assert m.draft_context()["player"] == {"level_of_play": "low elo (Iron–Silver)", "rank": "Silver III",
                                           "account_level": 211,
                                           "champion_experience": "new to this champion (0k mastery)"}


def test_cs_tip_scales_with_bracket_and_shows_gap():
    m = tip_model(600.0, {"cs": 50, "g": 0})                           # 5.0/min at 10:00
    m.player = {**PROFILE, "solo": "IRON II"}; m.update_tips()
    assert "cs_low" not in kinds(m)                                    # fine for low elo (warn < 4.5)
    m = tip_model(600.0, {"cs": 50, "g": 0}); m.player = {**PROFILE, "solo": "DIAMOND I"}; m.update_tips()
    tip = next(t for t in m.tips if t.kind == "cs_low")
    assert "30 CS (~600g) behind 8/min" in tip.detail and tip.action


def test_tips_have_actions():
    m = tip_model(500.0, {"cs": 10, "g": 1600}, [DEATH_EV | {"EventTime": 480.0, "Assisters": ["Jungler", "Buddy"]}])
    m.update_tips()
    assert m.tips and all(t.action for t in m.tips), [(t.kind, t.action) for t in m.tips]


# ── state toast ────────────────────────────────────────────────────────────

LIVE = {"t": 500, "mode": "CLASSIC", "hp": 820, "mhp": 1500, "mp": 300, "mmp": 600,
        "g": 1240, "lvl": 9, "k": 3, "d": 1, "a": 4, "cs": 85, "ad": 120, "ap": 40}


def test_state_lines_no_game():
    assert LeagueModel().state_lines() == ["Riot API · no live game"]


def test_state_lines_live_with_recent_events():
    m = rostered_model()
    m.live_state = LIVE
    m.ingest({"gameTime": 500.0}, {"Events": [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 480.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": ["Jungler"]},
        {"EventID": 2, "EventName": "DragonKill", "EventTime": 470.0,
         "KillerName": "Buddy", "DragonType": "Fire", "Stolen": "True"},
    ]})
    assert m.state_lines() == [
        "Riot API · 8:20 · CLASSIC",
        "Ahri · lvl 9 · 1240g",
        "HP 820/1500   MP 300/600",
        "KDA 3/1/4   CS 85",
        "AD 120   AP 40",
        "Last 60s:",
        "  7:50  ally fire dragon (stolen)",
        "  8:00  died to Zed +1",
    ], m.state_lines()


def test_state_lines_quiet_and_unknown_champion():
    m = LeagueModel()
    m.live_state = LIVE
    lines = m.state_lines()
    assert lines[1].startswith("? ·") and lines[-1] == "Last 60s: quiet"


# ── tips ───────────────────────────────────────────────────────────────────

def tip_model(clock, live=None, events=()):
    m = rostered_model()
    m.live_state = {**LIVE, **(live or {})}
    m.ingest({"gameTime": clock}, {"Events": list(events)})
    return m


def kinds(m):
    return {t.kind for t in m.tips}


def test_tips_cs_low_offered_cleared_and_cools_down():
    m = tip_model(600.0, {"cs": 40, "g": 0})           # 4.0/min at 10:00
    new = m.update_tips()
    assert [t.kind for t in new] == ["cs_low"] and "4.0/min" in new[0].detail
    assert m.update_tips() == []                       # not offered twice
    m.live_state = {**m.live_state, "cs": 70}           # 7.0/min → clears
    m.update_tips(); assert "cs_low" not in kinds(m)
    m.live_state = {**m.live_state, "cs": 40}           # low again, but cooling down
    m.update_tips(); assert "cs_low" not in kinds(m)
    m.ingest({"gameTime": 600.0 + TIP_COOLDOWN_S}, {"Events": []})
    m.live_state = {**m.live_state, "cs": 10}
    m.update_tips(); assert "cs_low" in kinds(m)


def test_tips_cs_not_judged_early_or_for_supports():
    assert "cs_low" not in kinds((lambda m: (m.update_tips(), m)[1])(tip_model(240.0, {"cs": 0})))
    m = tip_model(600.0, {"cs": 10})
    m.roster["Me#NA1"]["position"] = "UTILITY"
    m.update_tips(); assert "cs_low" not in kinds(m)


def test_tips_gold_and_hysteresis():
    m = tip_model(600.0, {"g": 1600, "cs": 80}); m.update_tips()
    assert kinds(m) == {"gold"}
    m.live_state = {**m.live_state, "g": 1200}; m.update_tips()
    assert "gold" in kinds(m)                           # still up until well below threshold
    m.live_state = {**m.live_state, "g": 900}; m.update_tips()
    assert "gold" not in kinds(m)


def test_tips_dragon_heads_up_and_expiry():
    m = tip_model(270.0, {"cs": 0}); m.update_tips()   # 30 s before 5:00
    tip = next(t for t in m.tips if t.kind.startswith("dragon_soon"))
    assert tip.headline == "Dragon at 5:00" and tip.priority == 5
    m.ingest({"gameTime": 331.0}, {"Events": []}); m.update_tips()
    assert not any(t.kind.startswith("dragon_soon") for t in m.tips)


def test_tips_death_and_enemy_dragon():
    m = tip_model(500.0, {"cs": 80}, [
        {"EventID": 1, "EventName": "ChampionKill", "EventTime": 480.0,
         "KillerName": "Foe", "VictimName": "Me", "Assisters": ["Jungler"]},
        {"EventID": 2, "EventName": "DragonKill", "EventTime": 470.0, "KillerName": "Foe",
         "DragonType": "Fire", "Stolen": "False"}])
    m.update_tips()
    death = next(t for t in m.tips if t.kind == "death@480")
    assert "Zed + Lee Sin" in death.detail and death.expires == 540.0
    assert "dragon@470" in kinds(m)
    ordered = [t.kind for t in m.tips_on_offer()]
    assert ordered[:2] == ["death@480", "dragon@470"]   # same priority → newest first


def test_tips_pop_logs_and_opens_card():
    m = tip_model(600.0, {"cs": 40, "g": 0}); tip = m.update_tips()[0]
    assert m.pop_tip(tip.id, 610.0) is tip and m.open_tip is tip and m.tips == []
    assert m.tip_log == [{"t": 610, "kind": "cs_low", "headline": "CS is low"}]
    assert m.pop_tip(tip.id, 611.0) is None


def test_checkpoint_tips_fresh_only():
    by_title = {cp.title: cp for cp in CHECKPOINTS}
    m = tip_model(365.0, {"cs": 60})
    grubs = m.checkpoint_tip(by_title["void grubs spawn"])
    assert grubs.headline == "Grubs are up" and grubs.action.startswith("Shove")
    m = tip_model(20 * 60.0, {"cs": 200})               # launched mid-game: 6:00 is long gone
    assert m.checkpoint_tip(by_title["void grubs spawn"]) is None
    m = tip_model(1600.0, {"cs": 200}, [{"EventID": 9, "EventName": "BaronKill", "EventTime": 1590.0}])
    assert m.checkpoint_tip(by_title["baron taken"]).priority == 5
    m = tip_model(1600.0, {"cs": 200}, [{"EventID": 9, "EventName": "BaronKill", "EventTime": 1400.0}])
    assert m.checkpoint_tip(by_title["baron taken"]) is None   # old history


def test_checkpoint_tip_elder_needs_soul():
    elder = next(cp for cp in CHECKPOINTS if cp.title == "elder spawn")
    m = tip_model(700.0, {"cs": 80}, [{"EventID": 1, "EventName": "DragonKill", "EventTime": 320.0,
                                       "KillerName": "Buddy", "DragonType": "Fire", "Stolen": "False"}])
    assert m.checkpoint_tip(elder) is None              # 1 drake + 6 min isn't elder


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
