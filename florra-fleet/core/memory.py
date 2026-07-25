"""Ops state in SQLite: per-channel rolling context + URL dedupe.

SQLite is disposable — Notion is the source of truth for lore data.
The db lives in a mounted volume so it survives container restarts.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    agent      TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    author     TEXT NOT NULL,
    content    TEXT NOT NULL,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_chan ON memory (agent, channel_id, ts);

CREATE TABLE IF NOT EXISTS dedupe (
    agent TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    ts    REAL NOT NULL,
    PRIMARY KEY (agent, key)
);
"""


class Memory:
    def __init__(self, db_path: Path, agent: str, context_window: int = 12):
        self.agent = agent
        self.context_window = context_window
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- rolling per-channel context ------------------------------------

    def remember(self, channel_id: int, author: str, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory (agent, channel_id, author, content, ts) VALUES (?, ?, ?, ?, ?)",
                (self.agent, channel_id, author, content[:2000], time.time()),
            )
            # keep the table bounded: drop entries beyond 5x the window
            self._conn.execute(
                """DELETE FROM memory WHERE agent = ? AND channel_id = ? AND ts NOT IN (
                       SELECT ts FROM memory WHERE agent = ? AND channel_id = ?
                       ORDER BY ts DESC LIMIT ?)""",
                (self.agent, channel_id, self.agent, channel_id, self.context_window * 5),
            )
            self._conn.commit()

    def recent(self, channel_id: int, limit: int | None = None) -> list[tuple[str, str]]:
        """Most recent (author, content) pairs, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT author, content FROM memory
                   WHERE agent = ? AND channel_id = ? ORDER BY ts DESC LIMIT ?""",
                (self.agent, channel_id, limit or self.context_window),
            ).fetchall()
        return list(reversed(rows))

    # -- dedupe ----------------------------------------------------------

    def dedupe_get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM dedupe WHERE agent = ? AND key = ?",
                (self.agent, key),
            ).fetchone()
        return row[0] if row else None

    def dedupe_set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO dedupe (agent, key, value, ts) VALUES (?, ?, ?, ?)",
                (self.agent, key, value, time.time()),
            )
            self._conn.commit()
