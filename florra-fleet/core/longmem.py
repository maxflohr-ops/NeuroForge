"""Long-term memory: durable facts, extracted by the cheap tier, recalled by
keyword rank.

Design follows the L0/L1 pattern of TencentDB-Agent-Memory: raw conversation
(L0, in core/memory.py) -> extracted durable facts (L1, here) -> recall
injection into prompts. Storage is SQLite FTS5 on the mounted volume, so it
needs no extra service and survives redeploys.

Pluggable by design: anything exposing add_fact/recall/recent can replace
this class — e.g. the TencentDB Agent Memory hub over HTTP — if the fleet
ever adds an embedding provider and wants true semantic recall.

Nothing is ever deleted. The office keeps everything.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path

from core.llm import CLASSIFY, ModelRouter

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id      INTEGER PRIMARY KEY,
    agent   TEXT NOT NULL,
    scope   TEXT NOT NULL,
    kind    TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    source  TEXT NOT NULL DEFAULT '',
    norm    TEXT NOT NULL,
    ts      REAL NOT NULL,
    UNIQUE (agent, scope, norm)
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content, content=facts, content_rowid=id, tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

EXTRACTION_SYSTEM = """You keep the long-term memory of an office bot. From a \
conversation excerpt, extract durable facts worth remembering weeks from now: \
decisions made, corrections to earlier beliefs, stated preferences, people and \
their roles, deadlines, ongoing projects and their state. Skip small talk, \
one-off status, questions, and anything a bot would already know from its own \
instructions. Each fact must stand alone without the conversation.

Output ONLY JSON: {"facts": ["...", "..."]} with zero to five short facts.
When nothing is worth keeping: {"facts": []}."""


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()[:300]


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9']{2,}", query)[:12]
    return " OR ".join(f'"{t}"' for t in tokens)


class LongMemory:
    def __init__(self, db_path: Path, agent: str):
        self.agent = agent
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        try:
            self._conn.executescript(_FTS_SCHEMA)
            self._fts = True
        except sqlite3.OperationalError:  # sqlite built without FTS5
            self._fts = False
        self._conn.commit()

    def add_fact(
        self, scope: str, content: str, kind: str = "fact", source: str = ""
    ) -> bool:
        """Store one durable fact. Returns False when it was already known."""
        content = content.strip()
        if not content:
            return False
        norm = _normalize(content)
        with self._lock:
            cursor = self._conn.execute(
                """INSERT OR IGNORE INTO facts (agent, scope, kind, content, source, norm, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.agent, scope, kind, content[:600], source[:120], norm, time.time()),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def recall(self, scope: str, query: str, limit: int = 4) -> list[str]:
        """Best-matching facts for a query, keyword-ranked; recent facts when
        the query gives nothing to match on."""
        match = _fts_query(query) if self._fts else ""
        with self._lock:
            rows: list[tuple[str]] = []
            if match:
                try:
                    rows = self._conn.execute(
                        """SELECT f.content FROM facts_fts
                           JOIN facts f ON f.id = facts_fts.rowid
                           WHERE facts_fts MATCH ? AND f.agent = ? AND f.scope = ?
                           ORDER BY bm25(facts_fts) LIMIT ?""",
                        (match, self.agent, scope, limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                rows = self._conn.execute(
                    """SELECT content FROM facts WHERE agent = ? AND scope = ?
                       ORDER BY ts DESC LIMIT ?""",
                    (self.agent, scope, limit),
                ).fetchall()
        return [r[0] for r in rows]

    def recent(self, scope: str, limit: int = 10) -> list[tuple[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT kind, content FROM facts WHERE agent = ? AND scope = ?
                   ORDER BY ts DESC LIMIT ?""",
                (self.agent, scope, limit),
            ).fetchall()
        return rows

    def count(self, scope: str | None = None) -> int:
        with self._lock:
            if scope:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM facts WHERE agent = ? AND scope = ?",
                    (self.agent, scope),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM facts WHERE agent = ?", (self.agent,)
                ).fetchone()
        return row[0]


async def extract_facts(
    llm: ModelRouter,
    longmem: LongMemory,
    scope: str,
    conversation: str,
    source: str = "",
    logger: logging.Logger | None = None,
) -> int:
    """Cheap-tier extraction pass over a conversation excerpt. Returns how
    many new facts were kept. Never raises — memory must not break replies."""
    try:
        parsed = await llm.complete_json(
            CLASSIFY,
            EXTRACTION_SYSTEM,
            f"Conversation excerpt:\n{conversation[:6000]}",
            max_tokens=400,
        )
        facts = (parsed or {}).get("facts", [])
        kept = 0
        for fact in facts[:5]:
            if isinstance(fact, str) and longmem.add_fact(scope, fact, source=source):
                kept += 1
        if logger and kept:
            from core.log import log_event

            log_event(logger, "facts_extracted", scope=scope, kept=kept)
        return kept
    except Exception as exc:
        if logger:
            from core.log import log_event

            log_event(logger, "fact_extraction_failed", error=str(exc)[:200])
        return 0
