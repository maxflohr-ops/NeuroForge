#!/usr/bin/env python3
"""
Channel Watcher Agent
Discovers every video on the Ridge Club channel (backfill) and new uploads (watch),
registering them in the state store. Uses yt-dlp's flat playlist extraction, so no
YouTube Data API key is needed.
"""

from datetime import datetime

import yt_dlp

from .config import Config
from .state import StateStore


class ChannelWatcher:
    def __init__(self, config: Config, state: StateStore):
        self.config = config
        self.state = state

    def _videos_url(self) -> str:
        # Normalize any channel URL form to its /videos tab
        url = self.config.channel_url.rstrip("/")
        return url if url.endswith("/videos") else url + "/videos"

    def discover(self, limit: int = 0) -> list:
        """
        Scan the channel and register unseen videos.
        limit=0 scans the full channel (backfill); a small limit (e.g. 20) is enough
        for watch mode since new uploads appear at the top of the list.
        Returns the list of newly registered video dicts.
        """
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        if limit:
            opts["playlistend"] = limit
        if self.config.cookies_file:
            opts["cookiefile"] = self.config.cookies_file

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(self._videos_url(), download=False)

        entries = info.get("entries") or []
        new_videos = []
        for entry in entries:
            if not entry or entry.get("id") is None:
                continue
            video_id = entry["id"]
            title = entry.get("title") or video_id
            url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            upload_date = self._fmt_date(entry.get("upload_date"))
            if self.state.add_video(video_id, title, url, upload_date):
                new_videos.append({"video_id": video_id, "title": title, "url": url})
        return new_videos

    @staticmethod
    def _fmt_date(raw) -> str:
        """yt-dlp gives YYYYMMDD; store ISO for sane sorting. Missing → empty."""
        if not raw:
            return ""
        try:
            return datetime.strptime(str(raw), "%Y%m%d").date().isoformat()
        except ValueError:
            return str(raw)
