"""Local LOL trend derivation over stored snapshots + the raw event feed.

Pure functions, no I/O and no LLM. `LolTrendRules` adapts them to the
`TrendRules` seam; the active player's riotId (needed for death-streak
attribution) is supplied by an injected callable so the generic seam stays
player-agnostic.

Snapshots are the compressed dicts produced by build_state (fields: t, cs, g,
k, d, a, lvl, ...). Events are raw Riot Live Client events.
"""


def _cs_per_min(snap: dict) -> float | None:
    t = snap.get("t") or 0
    cs = snap.get("cs")
    if not t or cs is None:
        return None
    return round(cs / (t / 60.0), 1)


def death_streak(events: list[dict], player_riot_id: str) -> int:
    """Consecutive deaths of the active player with no kill/assist in between.

    Walks events in chronological order; a kill or assist by the player resets
    the streak. Returns the trailing streak (0 if the last relevant event was a
    takedown or there are no deaths yet).
    """
    if not player_riot_id:
        return 0
    streak = 0
    for e in sorted(events, key=lambda x: x.get("EventTime", 0.0)):
        if e.get("EventName") != "ChampionKill":
            continue
        if e.get("VictimName") == player_riot_id:
            streak += 1
        elif (e.get("KillerName") == player_riot_id
              or player_riot_id in e.get("Assisters", [])):
            streak = 0
    return streak


def compute_trends(snapshots: list[dict], events: list[dict],
                   player_riot_id: str = "") -> dict:
    """Derive coaching-relevant deltas from a window of snapshots + events.

    Args:
        snapshots: chronological compressed-state dicts (oldest -> newest).
        events:    raw Riot Live Client events for the game.
        player_riot_id: active player's riotId, for death-streak attribution.

    Returns a compact dict; keys are omitted when not derivable yet.
    """
    trends: dict = {}
    if snapshots:
        latest = snapshots[-1]
        oldest = snapshots[0]

        cs_now = _cs_per_min(latest)
        if cs_now is not None:
            trends["cs_per_min"] = cs_now
            cs_then = _cs_per_min(oldest)
            if cs_then is not None and oldest is not latest:
                trends["cs_per_min_delta"] = round(cs_now - cs_then, 1)

        if latest.get("g") is not None and oldest.get("g") is not None:
            trends["gold_delta"] = latest["g"] - oldest["g"]

        # KDA velocity over the window
        dk = (latest.get("k", 0) - oldest.get("k", 0))
        dd = (latest.get("d", 0) - oldest.get("d", 0))
        da = (latest.get("a", 0) - oldest.get("a", 0))
        if any((dk, dd, da)):
            trends["kda_delta"] = f"{dk}/{dd}/{da}"

    streak = death_streak(events, player_riot_id)
    if streak >= 2:
        trends["death_streak"] = streak

    return trends


class LolTrendRules:
    """Adapts compute_trends to the TrendRules seam. `riot_id_fn` yields the
    active player's riotId at call time (kept out of the generic signature)."""

    def __init__(self, riot_id_fn):
        self._riot_id_fn = riot_id_fn

    def compute(self, snapshots: list[dict], events: list) -> dict:
        return compute_trends(snapshots, events, self._riot_id_fn())
