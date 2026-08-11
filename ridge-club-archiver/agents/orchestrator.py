#!/usr/bin/env python3
"""
Orchestrator
Drives each video through the full pipeline:

    discovered → downloaded → uploaded → clipping → clips_uploaded → done

Each stage transition is persisted, so any crash resumes cleanly on the next run.
"""

import shutil
import time
from datetime import datetime
from pathlib import Path

from . import state as st
from .channel_watcher import ChannelWatcher
from .config import Config
from .downloader import Downloader, safe_filename
from .drive_agent import DriveAgent
from .opus_agent import OpusAgent
from .state import StateStore


class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateStore(config.state_db)
        self.watcher = ChannelWatcher(config, self.state)
        self.downloader = Downloader(config)
        # Drive/Opus clients are built lazily so credential-free commands
        # (e.g. `status`) work without a service account on disk.
        self._drive = None
        self._opus = None

    @property
    def drive(self) -> DriveAgent:
        if self._drive is None:
            self._drive = DriveAgent(self.config)
        return self._drive

    @property
    def opus(self):
        if self.config.opus_enabled and self._opus is None:
            self._opus = OpusAgent(self.config)
        return self._opus

    # ── logging ──────────────────────────────────────────────────
    def log(self, message: str, prefix: str = "ℹ️"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{prefix} [{timestamp}] {message}", flush=True)

    # ── top-level modes ──────────────────────────────────────────
    def backfill(self):
        """Discover the entire channel history, then process everything pending."""
        self.log("Scanning full channel history...", "🔍")
        new = self.watcher.discover(limit=0)
        self.log(f"Registered {len(new)} new videos", "📋")
        self.process_pending()

    def watch_once(self):
        """One watch pass: pick up recent uploads and process everything pending."""
        new = self.watcher.discover(limit=25)
        if new:
            for v in new:
                self.log(f"New upload: {v['title']}", "🆕")
        self.process_pending()

    def watch_forever(self):
        interval = self.config.watch_interval_minutes * 60
        self.log(f"Watching channel every {self.config.watch_interval_minutes} min "
                 "(Ctrl-C to stop)", "👀")
        while True:
            try:
                self.watch_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # keep the daemon alive across transient failures
                self.log(f"Watch pass failed: {exc}", "❌")
            time.sleep(interval)

    def process_pending(self):
        pending = self.state.pending()
        if not pending:
            self.log("Nothing to do — archive is up to date", "✅")
            return
        self.log(f"{len(pending)} video(s) in the pipeline", "🏗️")
        for video in pending:
            try:
                self.process_video(video)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.log(f"{video['title']}: {exc}", "❌")
                self.state.mark_failed(video["video_id"], str(exc))

    # ── per-video pipeline ───────────────────────────────────────
    def process_video(self, video: dict):
        video_id = video["video_id"]
        stage = video["stage"]
        self.log(f"▶ {video['title']} (stage: {stage})", "🎬")

        if stage == st.DISCOVERED:
            path = self.downloader.download(video)
            self.state.mark_downloaded(video_id, str(path))
            video = self.state.get(video_id)
            self.log("Downloaded", "⬇️")

        if video["stage"] == st.DOWNLOADED:
            folder_id = self.drive.full_videos_folder()
            file_id = self.drive.upload_file(Path(video["local_path"]), folder_id)
            self.state.mark_uploaded(video_id, file_id)
            video = self.state.get(video_id)
            self.log("Full video uploaded to Drive", "☁️")

        if video["stage"] == st.UPLOADED:
            if not self.opus:
                self._cleanup(video)
                self.state.mark_done(video_id)
                self.log("Archived (Opus disabled)", "✅")
                return
            project_id = self.opus.submit(video)
            self.state.mark_clipping(video_id, project_id)
            video = self.state.get(video_id)
            self.log(f"Submitted to OpusClip (project {project_id})", "✂️")

        if video["stage"] == st.CLIPPING:
            self.opus.wait_until_done(video["opus_project_id"])
            clip_dir = self.config.download_dir / f"clips_{video_id}"
            clips = self.opus.download_clips(video["opus_project_id"], clip_dir)
            folder_name = f"{safe_filename(video['title'])} [{video_id}]"
            folder_id = self.drive.clips_folder_for(folder_name)
            for clip in clips:
                self.drive.upload_file(Path(clip["path"]), folder_id)
            self.state.mark_clips_uploaded(
                video_id, [{"title": c["title"]} for c in clips])
            video = self.state.get(video_id)
            self.log(f"{len(clips)} Opus clips uploaded to Drive", "🎞️")

        if video["stage"] == st.CLIPS_UPLOADED:
            self._cleanup(video)
            self.state.mark_done(video_id)
            self.log("Done — full video + clips archived", "✅")

    def _cleanup(self, video: dict):
        if self.config.keep_local_files:
            return
        local = video.get("local_path")
        if local and Path(local).exists():
            Path(local).unlink()
        clip_dir = self.config.download_dir / f"clips_{video['video_id']}"
        if clip_dir.exists():
            shutil.rmtree(clip_dir, ignore_errors=True)

    # ── reporting ────────────────────────────────────────────────
    def print_status(self):
        videos = self.state.all_videos()
        if not videos:
            print("No videos tracked yet — run `python run.py backfill` first.")
            return
        counts = {}
        for v in videos:
            counts[v["stage"]] = counts.get(v["stage"], 0) + 1
        print(f"\n📦 Ridge Club archive — {len(videos)} videos tracked")
        for stage in (st.DISCOVERED, st.DOWNLOADED, st.UPLOADED, st.CLIPPING,
                      st.CLIPS_UPLOADED, st.DONE, st.FAILED):
            if counts.get(stage):
                print(f"   {stage:<15} {counts[stage]}")
        failed = self.state.failed()
        if failed:
            print("\n❌ Failures (re-run with `python run.py retry`):")
            for v in failed:
                print(f"   - {v['title']}: {v['error']}")
        print()
