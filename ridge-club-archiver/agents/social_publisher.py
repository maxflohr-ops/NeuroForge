#!/usr/bin/env python3
"""
Social Publisher Agent
Posts finished Opus clips to Instagram + Snapchat (or any Ayrshare-linked
platforms) through the Ayrshare API — the same account/key the Ayrshare
Claude plugin uses (AYRSHARE_API_KEY).

Supports fan-out across the clipping community: set AYRSHARE_PROFILE_KEYS to
a comma list of member Profile Keys (see `run.py profiles`) and every clip is
posted through each member's linked accounts, intersected with the configured
platform list per member.

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


PRIMARY = "primary"  # sentinel Profile Key meaning the house accounts


class SocialPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        headers = {"Authorization": f"Bearer {config.ayrshare_api_key}"}
        if "twitter" in config.ayrshare_platforms:
            # X posting is bring-your-own-keys: Ayrshare doesn't store them,
            # they ride along as headers on every request targeting X.
            headers["X-Twitter-OAuth1-Api-Key"] = config.x_twitter_api_key
            headers["X-Twitter-OAuth1-Api-Secret"] = config.x_twitter_api_secret
        self.session.headers.update(headers)
        self._linked_cache = {}  # profile_key -> set of linked platform names

    def _url(self, path: str) -> str:
        return f"{self.config.ayrshare_api_base.rstrip('/')}/{path.lstrip('/')}"

    def _profile_headers(self, profile_key: str) -> dict:
        """Per-request Profile-Key header; the primary profile sends none."""
        if profile_key and profile_key != PRIMARY:
            return {"Profile-Key": profile_key}
        return {}

    def targets(self) -> list:
        """Profile Keys to fan out to, in order. Falls back to the single
        AYRSHARE_PROFILE_KEY, then to the primary (house) profile."""
        if self.config.ayrshare_profile_keys:
            return self.config.ayrshare_profile_keys
        if self.config.ayrshare_profile_key:
            return [self.config.ayrshare_profile_key]
        return [PRIMARY]

    def linked_platforms(self, profile_key: str) -> set:
        """Which of the configured platforms this profile actually has linked
        (a member who only connected IG shouldn't error on Snapchat)."""
        if profile_key not in self._linked_cache:
            resp = self.session.get(self._url("/user"), timeout=60,
                                    headers=self._profile_headers(profile_key))
            if resp.status_code != 200:
                raise AyrshareError(
                    f"user lookup failed for profile ({resp.status_code}): "
                    f"{resp.text[:300]}")
            self._linked_cache[profile_key] = set(
                resp.json().get("activeSocialAccounts") or [])
        return self._linked_cache[profile_key]

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
    def post_clip(self, caption: str, media_url: str, platforms: list,
                  profile_key: str = PRIMARY) -> str:
        """Publish one clip through one profile; returns the Ayrshare post id."""
        payload = {
            "post": caption,
            "platforms": platforms,
            "mediaUrls": [media_url],
            "isVideo": True,
        }
        resp = self.session.post(self._url("/post"), json=payload, timeout=120,
                                 headers=self._profile_headers(profile_key))
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200 or data.get("status") == "error":
            raise AyrshareError(f"post failed ({resp.status_code}): {resp.text[:500]}")
        return str(data.get("id", ""))

    def publish_clips(self, video: dict, clips: list) -> list:
        """
        Fan out: post up to `ayrshare_max_clips_per_video` clips (0 = all)
        through every target profile (house and/or community members).
        Each clip is uploaded to Ayrshare media storage once and the same
        access URL is reused across profiles.

        Returns [{'title', 'post_id', 'profile', 'platforms'}, ...]. A single
        member's failure is logged and skipped; the video only fails if every
        attempted post failed.
        """
        limit = self.config.ayrshare_max_clips_per_video
        selected = clips if limit <= 0 else clips[:limit]
        results, attempts, failures = [], 0, 0
        for clip in selected:
            path = Path(clip.get("path") or "")
            if not clip.get("path") or not path.exists():
                print(f"⚠️  clip file missing, skipping post: {clip.get('title')}", flush=True)
                continue
            caption = clip["title"]
            if self.config.ayrshare_caption_suffix:
                caption = f"{caption} {self.config.ayrshare_caption_suffix}"
            media_url = self.upload_media(path)
            for profile_key in self.targets():
                label = "house" if profile_key == PRIMARY else profile_key[:8] + "…"
                try:
                    platforms = [p for p in self.config.ayrshare_platforms
                                 if p in self.linked_platforms(profile_key)]
                    if not platforms:
                        print(f"⚠️  profile {label} has none of "
                              f"{self.config.ayrshare_platforms} linked, skipping",
                              flush=True)
                        continue
                    attempts += 1
                    post_id = self.post_clip(caption, media_url, platforms, profile_key)
                    results.append({"title": clip["title"], "post_id": post_id,
                                    "profile": label, "platforms": platforms})
                except AyrshareError as exc:
                    failures += 1
                    print(f"⚠️  post via profile {label} failed: {exc}", flush=True)
        if attempts and not results:
            raise AyrshareError(f"all {failures} post attempts failed")
        return results
