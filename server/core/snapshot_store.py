"""SQLite persistence for game snapshots, events, and per-game summaries.

Game-agnostic: a snapshot's coaching state is stored as a JSON blob (the
adapter's compact state dict), so no per-game columns are needed — adding a
game never touches the DB schema. The only structured snapshot columns are the
generic ones every game shares: a game id, an ordering timestamp `ts`, and the
local vision summary. Events use a normalized {id, name, time, raw} shape;
per-game metadata (e.g. champion, mode) rides along as an opaque JSON `meta`.

`sqlite3` is stdlib — no new dependency. The connection is opened with
`check_same_thread=False` and guarded by a lock because writers run on
background poll threads.
"""

import json
import os
import sqlite3
import threading

_DB_PATH = os.path.join(os.path.dirname(__file__), "coach_history.db")


class SnapshotStore:
    def __init__(self, db_path: str = _DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock, self._conn:
            self._reset_legacy_cache_if_stale()
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS games (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at REAL,
                    ended_at   REAL,
                    result     TEXT,
                    summary    TEXT,
                    meta       TEXT
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id     INTEGER,
                    ts          REAL,
                    map_summary TEXT,
                    state       TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_game_ts
                    ON snapshots(game_id, ts);
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id    INTEGER,
                    event_id   INTEGER,
                    name       TEXT,
                    event_time REAL,
                    raw        TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_game
                    ON events(game_id, event_id);
            """)

    def _reset_legacy_cache_if_stale(self):
        """The pre-refactor schema stored one column per LOL stat, which is
        incompatible with the JSON-blob layout. Snapshots/events/games are a
        rolling analytics cache (never authored content), so if the legacy
        layout is detected, drop and recreate rather than crash on insert."""
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'")
        if not cur.fetchone():
            return
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(snapshots)")}
        if "state" not in cols:
            print("SnapshotStore: legacy cache schema detected — resetting history tables.")
            self._conn.executescript(
                "DROP TABLE IF EXISTS snapshots;"
                "DROP TABLE IF EXISTS events;"
                "DROP TABLE IF EXISTS games;")

    # ── game lifecycle ──────────────────────────────────────────────────────

    def start_game(self, meta: dict, now: float) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO games (started_at, meta) VALUES (?, ?)",
                (now, json.dumps(meta or {})),
            )
            return cur.lastrowid

    def end_game(self, game_id: int, result: str, summary: dict, now: float):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE games SET ended_at = ?, result = ?, summary = ? WHERE id = ?",
                (now, result, json.dumps(summary), game_id),
            )

    # ── writes ──────────────────────────────────────────────────────────────

    def record_snapshot(self, game_id: int, state: dict, map_summary: str = "",
                        ts: float = 0.0):
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO snapshots (game_id, ts, map_summary, state) "
                "VALUES (?, ?, ?, ?)",
                (game_id, ts, map_summary, json.dumps(state)),
            )

    def record_events(self, game_id: int, events: list[dict]):
        """Insert normalized events not already stored for this game (dedup on id)."""
        if not events:
            return
        with self._lock, self._conn:
            seen = {row["event_id"] for row in self._conn.execute(
                "SELECT event_id FROM events WHERE game_id = ?", (game_id,))}
            for e in events:
                eid = e.get("id")
                if eid in seen:
                    continue
                self._conn.execute(
                    "INSERT INTO events (game_id, event_id, name, event_time, raw) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (game_id, eid, e.get("name", ""),
                     e.get("time", 0.0), json.dumps(e.get("raw", e))),
                )

    # ── reads ───────────────────────────────────────────────────────────────

    def recent_snapshots(self, game_id: int, window_s: float | None = None) -> list[dict]:
        """State dicts for a game, optionally only those within the last `window_s`."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, state FROM snapshots WHERE game_id = ? ORDER BY ts",
                (game_id,),
            ).fetchall()
        snaps = [(r["ts"], json.loads(r["state"])) for r in rows]
        if window_s is not None and snaps:
            latest_ts = snaps[-1][0] or 0
            snaps = [s for s in snaps if (s[0] or 0) >= latest_ts - window_s]
        return [state for _, state in snaps]

    def close(self):
        with self._lock:
            self._conn.close()
