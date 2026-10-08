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
)


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
