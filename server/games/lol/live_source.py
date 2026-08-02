"""Background Riot poller — the LOL in-game data source (orchestration seam).

Runs OFF the 60fps render tick on its own daemon thread so a slow/blocking Live
Client HTTP call can never stall rendering. Each cycle it fetches live data via
riot.py, routes it into the session's LOL game state, persists a compressed
snapshot + events, derives trends, runs checkpoint detection, and — when a
checkpoint fires — asks the coach for proactive advice.
"""

import time

import requests

from server.core.datasource import PollingDataSource
from server.games.lol.riot import (
    get_active_player,
    get_game_stats,
    get_player_list,
    get_player_scores,
    get_event_data,
)
from server.games.lol.state import normalize_events


class GameStatePoller(PollingDataSource):
    def __init__(self, session, store=None, coach=None, vision=None,
                 checkpoint_rules=None, trend_rules=None, interval: float = 1.5):
        super().__init__(name="Riot poller", interval=interval)
        self.session = session
        self.store = store
        self.coach = coach
        self.vision = vision
        self.checkpoint_rules = checkpoint_rules
        self.trend_rules = trend_rules
        self._game_id = None
        self._last_game_time = -1.0

    # ── error / stop hooks ───────────────────────────────────────────────────

    def _on_error(self, e):
        # Live Client unreachable or 404 (client up, no active game) →
        # no game running. End any open game and flag it for the UI.
        if isinstance(e, (requests.RequestException, OSError)):
            self._end_game()
        else:
            print(f"Poller error: {e}")

    def _on_stop(self):
        self._end_game()

    # ── poll ─────────────────────────────────────────────────────────────────

    def _poll_once(self):
        active = get_active_player()
        game = get_game_stats()
        players = get_player_list()
        events = get_event_data().get("Events", [])

        riot_id = active.get("riotId", "")
        scores = get_player_scores(riot_id) if riot_id else {}
        game_time = game.get("gameTime", 0.0)

        self._maybe_new_game(active, game, players, riot_id)

        g = self.session.game
        g.update_active_player(active, scores)
        g.update_game_stats(game)
        g.update_players(players)
        g.update_events(events)

        state = g.compressed_state()
        g.map_summary = self.vision.summarize() if self.vision else ""

        if self.store and self._game_id is not None:
            self.store.record_snapshot(self._game_id, state, g.map_summary,
                                       ts=state.get("t", 0.0))
            self.store.record_events(self._game_id, normalize_events(events))

        # Local trends over the last ~5 min, then checkpoint detection.
        snaps = (self.store.recent_snapshots(self._game_id, window_s=300)
                 if (self.store and self._game_id is not None) else [state])
        trends = self.trend_rules.compute(snaps, events) if self.trend_rules else {}

        if self.checkpoint_rules:
            for cp in self.checkpoint_rules.check(state, events, trends):
                self._handle_checkpoint(cp, state, trends)

        self._last_game_time = game_time
        self.session.model.in_game = True

    # ── game lifecycle helpers ──────────────────────────────────────────────

    def _maybe_new_game(self, active, game, players, riot_id):
        """Open a new game row on first poll, or when the clock resets."""
        game_time = game.get("gameTime", 0.0)
        restarted = game_time + 1.0 < self._last_game_time  # clock went backwards
        if self._game_id is None or restarted:
            if restarted:
                self._end_game()
            if self.checkpoint_rules:
                self.checkpoint_rules.reset()
            champion = active.get("championName") or self._champion_from_list(players, riot_id)
            if self.store:
                self._game_id = self.store.start_game(
                    {"champion": champion, "mode": game.get("gameMode", "")}, time.time())
            else:
                self._game_id = -1

    @staticmethod
    def _champion_from_list(players, riot_id):
        for p in players or []:
            if p.get("riotId") == riot_id:
                return p.get("championName", "")
        return ""

    def _end_game(self):
        self.session.model.in_game = False
        if self._game_id is None:
            return
        if self.store and self._game_id != -1:
            state = self.session.game.compressed_state()
            summary = {"kda": f"{state['k']}/{state['d']}/{state['a']}",
                       "cs": state["cs"],
                       "champion": self.session.game.active_player.get("championName", "")}
            self.store.end_game(self._game_id, "unknown", summary, time.time())
        self._game_id = None
        self._last_game_time = -1.0

    # ── checkpoint → coach ───────────────────────────────────────────────────

    def _handle_checkpoint(self, cp, state, trends):
        self.session.model.checkpoints.append({"title": cp.title, "key": cp.key})
        if not self.coach:
            return
        extra = {"trends": trends, "map": self.session.game.map_summary, "checkpoint": cp.title}
        image = self.vision.minimap_image() if (cp.want_image and self.vision) else None
        advice = self.coach.get_advice(
            question=cp.title, schema_key=cp.schema_key,
            state=state, extra=extra, image=image)
        self.session.model.last_advice = advice
        self.session.model.pending_suggestion = {"title": cp.title, "advice": advice}
        print(f"[checkpoint] {cp.title} -> {advice}")
