#!/usr/bin/env python3
"""
Social Publisher Agent
Posts finished Opus clips to Instagram + Snapchat (or any Ayrshare-linked
platforms) through the Ayrshare API — the same account/key the Ayrshare
Claude plugin uses (AYRSHARE_API_KEY).

Flow per clip:
    GET  /media/uploadUrl   → presigned upload slot
    PUT  <uploadUrl>        → upload the clip file
    POST /post              → publish accessUrl to the configured platforms

API reference: https://www.ayrshare.com/docs/
"""

from pathlib import Path

import requests

from .config import Config


class AyrshareError(RuntimeError):
    pass


class SocialPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        headers = {"Authorization": f"Bearer {config.ayrshare_api_key}"}
        if config.ayrshare_profile_key:
            headers["Profile-Key"] = config.ayrshare_profile_key
        if "twitter" in config.ayrshare_platforms:
            # X posting is bring-your-own-keys: Ayrshare doesn't store them,
            # they ride along as headers on every request targeting X.
            headers["X-Twitter-OAuth1-Api-Key"] = config.x_twitter_api_key
            headers["X-Twitter-OAuth1-Api-Secret"] = config.x_twitter_api_secret
        self.session.headers.update(headers)

    def _url(self, path: str) -> str:
        return f"{self.config.ayrshare_api_base.rstrip('/')}/{path.lstrip('/')}"

    # ── media upload ─────────────────────────────────────────────
    def upload_media(self, path: Path) -> str:
        """
        Upload a local clip to Ayrshare media storage; returns its access URL.
        GET /media/uploadUrl takes the extension as contentType ("mp4"), returns a
        presigned uploadUrl (single-use, 30 min, 5 GB max) plus the Content-Type
        to send with the PUT.
        """
        resp = self.session.get(
            self._url("/media/uploadUrl"),
            params={"fileName": path.name,
                    "contentType": path.suffix.lstrip(".").lower() or "mp4"},
            timeout=60)
        if resp.status_code != 200:
            raise AyrshareError(f"uploadUrl failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        upload_url, access_url = data.get("uploadUrl"), data.get("accessUrl")
        if not upload_url or not access_url:
            raise AyrshareError(f"uploadUrl response missing fields: {data}")
        put_content_type = data.get("contentType") or "video/mp4"

        with open(path, "rb") as f:
            put = requests.put(upload_url, data=f,
                               headers={"Content-Type": put_content_type}, timeout=600)
        if put.status_code not in (200, 201):
            raise AyrshareError(f"media PUT failed ({put.status_code}): {put.text[:300]}")
        return access_url

    # ── posting ──────────────────────────────────────────────────
    def post_clip(self, caption: str, media_url: str) -> str:
        """Publish one clip to all configured platforms; returns the Ayrshare post id."""
        payload = {
            "post": caption,
            "platforms": self.config.ayrshare_platforms,
            "mediaUrls": [media_url],
            "isVideo": True,
        }
        resp = self.session.post(self._url("/post"), json=payload, timeout=120)
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200 or data.get("status") == "error":
            raise AyrshareError(f"post failed ({resp.status_code}): {resp.text[:500]}")
        return str(data.get("id", ""))

    def publish_clips(self, video: dict, clips: list) -> list:
        """
        Post up to `ayrshare_max_clips_per_video` clips for a video
        (0 = post them all). Returns [{'title', 'post_id'}, ...].
        Skips clips whose local file is gone instead of failing the video.
        """
        limit = self.config.ayrshare_max_clips_per_video
        selected = clips if limit <= 0 else clips[:limit]
        results = []
        for clip in selected:
            path = Path(clip.get("path") or "")
            if not clip.get("path") or not path.exists():
                print(f"⚠️  clip file missing, skipping post: {clip.get('title')}", flush=True)
                continue
            caption = clip["title"]
            if self.config.ayrshare_caption_suffix:
                caption = f"{caption} {self.config.ayrshare_caption_suffix}"
            media_url = self.upload_media(path)
            post_id = self.post_clip(caption, media_url)
            results.append({"title": clip["title"], "post_id": post_id})
        return results
