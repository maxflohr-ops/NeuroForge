#!/usr/bin/env python3
"""
Downloader Agent
Pulls the full-quality video file from YouTube with yt-dlp.
"""

import re
from pathlib import Path

import yt_dlp

from .config import Config


def safe_filename(name: str, max_len: int = 150) -> str:
    """Strip characters that upset filesystems and Drive."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name).strip().rstrip(".")
    return cleaned[:max_len] or "untitled"


class Downloader:
    def __init__(self, config: Config):
        self.config = config
        self.config.download_dir.mkdir(parents=True, exist_ok=True)

    def _find_existing(self, video_id: str):
        # glob treats [] as character classes, so match the id tag manually
        tag = f"[{video_id}]"
        for path in self.config.download_dir.glob("*.mp4"):
            if tag in path.name:
                return path
        return None

    def download(self, video: dict) -> Path:
        """Download a video; returns the path of the merged mp4."""
        video_id = video["video_id"]
        out_dir = self.config.download_dir

        # Resume-friendly: if a previous run already fetched it, reuse the file.
        existing = self._find_existing(video_id)
        if existing:
            return existing

        height_cap = f"[height<={self.config.max_video_height}]" if self.config.max_video_height else ""
        prefix = f"{video.get('upload_date') or 'unknown-date'} - {safe_filename(video['title'])}"
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": f"bestvideo{height_cap}+bestaudio/best{height_cap}",
            "merge_output_format": "mp4",
            "outtmpl": str(out_dir / f"{prefix} [%(id)s].%(ext)s"),
            "retries": 5,
            "fragment_retries": 5,
            "noprogress": True,
        }
        if self.config.cookies_file:
            opts["cookiefile"] = self.config.cookies_file
        js_runtimes = self.config.ytdlp_js_runtimes_opt()
        if js_runtimes:
            opts["js_runtimes"] = js_runtimes

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video["url"]])

        result = self._find_existing(video_id)
        if not result:
            raise RuntimeError(f"yt-dlp finished but no mp4 found for {video_id}")
        return result
