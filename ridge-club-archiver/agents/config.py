#!/usr/bin/env python3
"""
Configuration for the Ridge Club YouTube Archiver.
Loads from environment (.env supported via python-dotenv).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    channel_url: str = os.getenv("YOUTUBE_CHANNEL_URL", "")
    drive_root_folder_id: str = os.getenv("DRIVE_ROOT_FOLDER_ID", "")
    service_account_file: Path = field(default_factory=lambda: BASE_DIR / os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/service_account.json"))

    opus_enabled: bool = field(default_factory=lambda: _bool("OPUS_ENABLED", True))
    opus_api_key: str = os.getenv("OPUS_API_KEY", "")
    opus_api_base: str = os.getenv("OPUS_API_BASE", "https://api.opus.pro/api")

    # Ayrshare social posting (Instagram + Snapchat are linked to this account).
    # Enabled by default whenever an API key is present.
    ayrshare_api_key: str = os.getenv("AYRSHARE_API_KEY", "")
    ayrshare_enabled: bool = field(default_factory=lambda: _bool(
        "AYRSHARE_ENABLED", bool(os.getenv("AYRSHARE_API_KEY", ""))))
    ayrshare_api_base: str = os.getenv("AYRSHARE_API_BASE", "https://api.ayrshare.com/api")
    ayrshare_profile_key: str = os.getenv("AYRSHARE_PROFILE_KEY", "")
    # X (Twitter) posting via Ayrshare requires bring-your-own-keys: the
    # OAuth 1.0a Consumer Key + Secret from your X developer app, sent as
    # headers on every request that targets X. Same env names the Ayrshare
    # Claude plugin uses.
    x_twitter_api_key: str = os.getenv("X_TWITTER_OAUTH1_API_KEY", "")
    x_twitter_api_secret: str = os.getenv("X_TWITTER_OAUTH1_API_SECRET", "")
    # Default platforms: IG + Snapchat, plus X automatically once its keys are set.
    ayrshare_platforms: list = field(default_factory=lambda: [
        p.strip() for p in os.getenv(
            "AYRSHARE_PLATFORMS",
            "instagram,snapchat,twitter" if os.getenv("X_TWITTER_OAUTH1_API_KEY")
            else "instagram,snapchat").split(",")
        if p.strip()])
    # Post only the top N Opus clips per video (they come back ranked);
    # 0 = post every clip. Keeps a channel backfill from flooding IG/Snap.
    ayrshare_max_clips_per_video: int = int(os.getenv("AYRSHARE_MAX_CLIPS_PER_VIDEO", "3"))
    ayrshare_caption_suffix: str = os.getenv("AYRSHARE_CAPTION_SUFFIX", "")

    download_dir: Path = field(default_factory=lambda: BASE_DIR / os.getenv("DOWNLOAD_DIR", "downloads"))
    state_db: Path = field(default_factory=lambda: BASE_DIR / "state" / "archive.db")
    watch_interval_minutes: int = int(os.getenv("WATCH_INTERVAL_MINUTES", "15"))
    max_video_height: int = int(os.getenv("MAX_VIDEO_HEIGHT", "0"))  # 0 = best available
    keep_local_files: bool = field(default_factory=lambda: _bool("KEEP_LOCAL_FILES", False))
    cookies_file: str = os.getenv("YTDLP_COOKIES_FILE", "")

    full_videos_folder_name: str = "01 Full Videos"
    opus_clips_folder_name: str = "02 Opus Clips"

    def validate(self) -> list:
        """Return a list of human-readable config problems (empty = OK)."""
        problems = []
        if not self.channel_url:
            problems.append("YOUTUBE_CHANNEL_URL is not set")
        if not self.drive_root_folder_id:
            problems.append("DRIVE_ROOT_FOLDER_ID is not set")
        if not self.service_account_file.exists():
            problems.append(f"Google service account key not found at {self.service_account_file}")
        if self.opus_enabled and not self.opus_api_key:
            problems.append("OPUS_ENABLED=true but OPUS_API_KEY is not set "
                            "(set OPUS_ENABLED=false to archive without clipping)")
        if self.ayrshare_enabled and not self.ayrshare_api_key:
            problems.append("AYRSHARE_ENABLED=true but AYRSHARE_API_KEY is not set")
        if self.ayrshare_enabled and not self.opus_enabled:
            problems.append("Ayrshare posting needs Opus clips — enable OPUS_ENABLED "
                            "or set AYRSHARE_ENABLED=false")
        if (self.ayrshare_enabled and "twitter" in self.ayrshare_platforms
                and not (self.x_twitter_api_key and self.x_twitter_api_secret)):
            problems.append("Posting to X requires X_TWITTER_OAUTH1_API_KEY and "
                            "X_TWITTER_OAUTH1_API_SECRET (X developer app Consumer "
                            "Key/Secret), or remove twitter from AYRSHARE_PLATFORMS")
        return problems
