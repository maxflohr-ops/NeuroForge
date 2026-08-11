#!/usr/bin/env python3
"""
SQLite-backed pipeline state.

Each video moves through:
    discovered → downloaded → uploaded → clipping → clips_uploaded → done
(`uploaded` jumps straight to `done` when Opus is disabled.)

Every mutation is committed immediately, so a crash at any point is recoverable —
re-running the pipeline resumes each video from its recorded stage.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Ordered pipeline stages
DISCOVERED = "discovered"
DOWNLOADED = "downloaded"
UPLOADED = "uploaded"          # full video is in Drive
CLIPPING = "clipping"          # submitted to Opus, waiting for clips
CLIPS_UPLOADED = "clips_uploaded"
DONE = "done"
FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    upload_date     TEXT,
    stage           TEXT NOT NULL DEFAULT 'discovered',
    local_path      TEXT,
    drive_file_id   TEXT,
    opus_project_id TEXT,
    clips_json      TEXT,
    error           TEXT,
    updated_at      TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    # ── discovery ────────────────────────────────────────────────
    def add_video(self, video_id: str, title: str, url: str, upload_date: str = ""):
        """Register a video if we haven't seen it before. Returns True if new."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO videos (video_id, title, url, upload_date, stage, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, title, url, upload_date, DISCOVERED, _now()))
        self.conn.commit()
        return cur.rowcount == 1

    # ── lookups ──────────────────────────────────────────────────
    def get(self, video_id: str):
        row = self.conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return dict(row) if row else None

    def pending(self):
        """All videos that still need work, oldest upload first."""
        rows = self.conn.execute(
            "SELECT * FROM videos WHERE stage NOT IN (?, ?) ORDER BY upload_date, video_id",
            (DONE, FAILED)).fetchall()
        return [dict(r) for r in rows]

    def failed(self):
        rows = self.conn.execute("SELECT * FROM videos WHERE stage = ?", (FAILED,)).fetchall()
        return [dict(r) for r in rows]

    def all_videos(self):
        rows = self.conn.execute("SELECT * FROM videos ORDER BY upload_date, video_id").fetchall()
        return [dict(r) for r in rows]

    # ── stage transitions ────────────────────────────────────────
    def _set(self, video_id: str, **fields):
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE videos SET {cols} WHERE video_id = ?",
                          (*fields.values(), video_id))
        self.conn.commit()

    def mark_downloaded(self, video_id: str, local_path: str):
        self._set(video_id, stage=DOWNLOADED, local_path=local_path, error=None)

    def mark_uploaded(self, video_id: str, drive_file_id: str):
        self._set(video_id, stage=UPLOADED, drive_file_id=drive_file_id, error=None)

    def mark_clipping(self, video_id: str, opus_project_id: str):
        self._set(video_id, stage=CLIPPING, opus_project_id=opus_project_id, error=None)

    def mark_clips_uploaded(self, video_id: str, clips: list):
        self._set(video_id, stage=CLIPS_UPLOADED, clips_json=json.dumps(clips), error=None)

    def mark_done(self, video_id: str):
        self._set(video_id, stage=DONE, error=None)

    def mark_failed(self, video_id: str, error: str):
        # Keep the current stage's progress; just record the error so the next
        # run retries from where it left off.
        self._set(video_id, stage=FAILED, error=error[:2000])

    def retry_failed(self):
        """Reset failed videos to re-enter the pipeline (kept fields decide the resume point)."""
        self.conn.execute(
            "UPDATE videos SET stage = CASE "
            " WHEN opus_project_id IS NOT NULL THEN ? "
            " WHEN drive_file_id IS NOT NULL THEN ? "
            " WHEN local_path IS NOT NULL THEN ? "
            " ELSE ? END, error = NULL, updated_at = ? "
            "WHERE stage = ?",
            (CLIPPING, UPLOADED, DOWNLOADED, DISCOVERED, _now(), FAILED))
        self.conn.commit()
