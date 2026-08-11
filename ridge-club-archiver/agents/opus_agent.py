#!/usr/bin/env python3
"""
Opus Agent
Submits archived videos to OpusClip via its API, waits for the auto-clips,
and downloads the finished clip files so the Drive Agent can file them.

API reference: https://docs.opus.pro/
Flow: POST /v1/clip-projects (sourceVideoUrl) → poll GET /v1/clip-projects/{id}
until DONE → GET /v1/clip-projects/{id}/clips → download each clip's downloadUrl.

Endpoint paths are centralized here so an API revision only touches this file.
"""

import time
from pathlib import Path

import requests

from .config import Config
from .downloader import safe_filename

TERMINAL_OK = {"DONE", "COMPLETED", "SUCCESS"}
TERMINAL_BAD = {"FAILED", "ERROR", "CANCELED", "CANCELLED"}


class OpusError(RuntimeError):
    pass


class OpusAgent:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.opus_api_key}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self.config.opus_api_base.rstrip('/')}/{path.lstrip('/')}"

    # ── submit ───────────────────────────────────────────────────
    def submit(self, video: dict) -> str:
        """Create a clip project from the video's YouTube URL. Returns project id."""
        payload = {
            "sourceVideoUrl": video["url"],
            "projectName": f"{video['title']} [{video['video_id']}]",
        }
        resp = self.session.post(self._url("/v1/clip-projects"), json=payload, timeout=60)
        if resp.status_code not in (200, 201, 202):
            raise OpusError(f"Opus submit failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        project_id = data.get("id") or data.get("projectId") or (data.get("data") or {}).get("id")
        if not project_id:
            raise OpusError(f"Opus submit succeeded but no project id in response: {data}")
        return str(project_id)

    # ── poll ─────────────────────────────────────────────────────
    def status(self, project_id: str) -> str:
        resp = self.session.get(self._url(f"/v1/clip-projects/{project_id}"), timeout=60)
        if resp.status_code != 200:
            raise OpusError(f"Opus status failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        state = data.get("status") or data.get("state") or (data.get("data") or {}).get("status")
        return str(state or "UNKNOWN").upper()

    def wait_until_done(self, project_id: str, poll_seconds: int = 120,
                        timeout_minutes: int = 240) -> None:
        """Block until Opus finishes clipping (long videos can take a while)."""
        deadline = time.time() + timeout_minutes * 60
        while True:
            state = self.status(project_id)
            if state in TERMINAL_OK:
                return
            if state in TERMINAL_BAD:
                raise OpusError(f"Opus project {project_id} ended in state {state}")
            if time.time() > deadline:
                raise OpusError(f"Opus project {project_id} still {state} after "
                                f"{timeout_minutes} min — will retry next run")
            time.sleep(poll_seconds)

    # ── fetch clips ──────────────────────────────────────────────
    def list_clips(self, project_id: str) -> list:
        resp = self.session.get(self._url(f"/v1/clip-projects/{project_id}/clips"), timeout=60)
        if resp.status_code != 200:
            raise OpusError(f"Opus clips list failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        clips = data if isinstance(data, list) else (data.get("clips") or data.get("data") or [])
        return clips

    def download_clips(self, project_id: str, dest_dir: Path) -> list:
        """Download every finished clip; returns [{'title','path'}, ...]."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for i, clip in enumerate(self.list_clips(project_id), start=1):
            url = (clip.get("downloadUrl") or clip.get("videoUrl")
                   or clip.get("exportUrl") or clip.get("url"))
            if not url:
                continue
            title = safe_filename(clip.get("title") or clip.get("name") or f"clip {i}", 100)
            path = dest_dir / f"clip_{i:02d} - {title}.mp4"
            if not path.exists():
                with self.session.get(url, stream=True, timeout=300) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)
            out.append({"title": title, "path": str(path)})
        if not out:
            raise OpusError(f"Opus project {project_id} finished but returned no "
                            "downloadable clips")
        return out
