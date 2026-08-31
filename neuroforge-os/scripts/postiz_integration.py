#!/usr/bin/env python3
"""
NeuroForge OS — Postiz Posting Integration
==========================================
Schedules generated short-form videos to TikTok, Instagram Reels, and YouTube
Shorts through a Postiz instance (self-hosted or cloud) using its Public API.

This is the "distribution" layer that turns generated content into actual
posts. It reads the parsed script JSONs (scripts_parsed/script_*.json) and the
generated MP4s (videos/script_*.mp4) for a topic, uploads each video, and
schedules posts with the caption/hashtags from the script data.

Usage:
    python postiz_integration.py \
        --topic "Stop Overthinking" \
        --faculty "Dr. Nova Vale" \
        --platforms tiktok,instagram,youtube \
        [--start-date "2026-09-01"] \
        [--interval-days 2] \
        [--dry-run]

Env:
    POSTIZ_API_KEY        required — API key from Postiz → Settings → API keys
    POSTIZ_BASE_URL       default https://api.postiz.com/public/v1
                          (self-hosted: https://your-domain/api/public/v1)
    POSTIZ_INTEGRATION_IDS optional JSON mapping platform -> integration id,
                          e.g. {"tiktok": "cm4...", "youtube": "cm5..."}.
                          If omitted, the script lists integrations and picks
                          the first enabled one per platform.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = Path(os.getenv("NEUROFORGE_OUTPUT_DIR", PROJECT_DIR / "output"))

DEFAULT_BASE_URL = "https://api.postiz.com/public/v1"

# Postiz integration identifier -> platform key used in this script
PLATFORM_KEYS = {
    "tiktok": "tiktok",
    "instagram": "instagram",
    "youtube": "youtube",
}

# Posting cadence per platform (Mon/Wed/Fri video days from MARKETING_OPS.md)
VIDEO_DAYS = [0, 2, 4]  # Monday, Wednesday, Friday


class PostizIntegration:
    def __init__(self, base_url: str, api_key: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.dry_run = dry_run
        self.headers = {"Authorization": api_key}

    # ── API helpers ─────────────────────────────────────────────────────────

    def _get(self, path: str):
        resp = requests.get(f"{self.base_url}{path}", headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict):
        resp = requests.post(
            f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _upload(self, filepath: Path) -> dict:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/upload",
                headers=self.headers,
                files={"file": (filepath.name, f, "video/mp4")},
                timeout=300,
            )
        resp.raise_for_status()
        return resp.json()

    # ── Public methods ──────────────────────────────────────────────────────

    def list_integrations(self) -> list:
        """Return all connected channels."""
        return self._get("/integrations")

    def resolve_integration_ids(self, platforms: list) -> dict:
        """Map platform key -> integration id, using env override or discovery."""
        override = os.getenv("POSTIZ_INTEGRATION_IDS")
        if override:
            try:
                return json.loads(override)
            except json.JSONDecodeError:
                print(f"  ⚠️  POSTIZ_INTEGRATION_IDS is not valid JSON: {override}",
                      file=sys.stderr)

        if self.dry_run:
            # No API calls in dry-run mode — use placeholder IDs.
            return {p: f"dry-{p}-integration" for p in platforms}

        integrations = self.list_integrations()
        result = {}
        for platform in platforms:
            key = PLATFORM_KEYS.get(platform)
            if not key:
                print(f"  ⚠️  Unknown platform: {platform}", file=sys.stderr)
                continue
            matches = [
                i for i in integrations
                if i.get("identifier") == key and not i.get("disabled")
            ]
            if matches:
                result[platform] = matches[0]["id"]
                print(f"  ✓ {platform} -> integration {matches[0]['id']} "
                      f"({matches[0].get('profile', '')})")
            else:
                print(f"  ✗ No enabled {platform} integration found. "
                      f"Connect it in Postiz first.", file=sys.stderr)
        return result

    def schedule_post(self, platform: str, integration_id: str,
                      content: str, media: list, title: str,
                      publish_at: datetime) -> str:
        """Schedule a single post. Returns the created postId."""
        settings = {"__type": PLATFORM_KEYS[platform]}

        if platform == "tiktok":
            settings.update({
                "title": title[:90],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "duet": True,
                "stitch": True,
                "comment": True,
                "autoAddMusic": "no",
                "brand_content_toggle": False,
                "brand_organic_toggle": False,
                "video_made_with_ai": True,  # honest AI labeling
                "content_posting_method": "DIRECT_POST",
            })
        elif platform == "youtube":
            settings.update({
                "title": title[:100],
                "type": "public",
                "selfDeclaredMadeForKids": "no",
                "tags": [{"value": "shorts", "label": "Shorts"}],
            })
        elif platform == "instagram":
            settings.update({
                "post_type": "post",
                "is_trial_reel": False,
                "collaborators": [],
            })

        payload = {
            "type": "schedule",
            "date": publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "shortLink": False,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": integration_id},
                    "value": [{"content": content, "image": media}],
                    "settings": settings,
                }
            ],
        }

        if self.dry_run:
            print(f"  [DRY RUN] Would schedule {platform} post at {publish_at.isoformat()}")
            print(f"            title={title!r} media={media}")
            return "dry-run"

        created = self._post("/posts", payload)
        post_id = created[0].get("postId", "unknown") if isinstance(created, list) else created
        print(f"  ✓ {platform} post scheduled: {post_id}")
        return post_id

    # ── Orchestration ───────────────────────────────────────────────────────

    def schedule_topic_videos(self, topic: str, platforms: list,
                              start_date: datetime,
                              interval_days: int) -> dict:
        """Upload and schedule every video for a topic across platforms."""
        safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
        scripts_dir = OUTPUT_DIR / safe_topic / "scripts_parsed"
        videos_dir = OUTPUT_DIR / safe_topic / "videos"

        if not videos_dir.exists():
            print(f"Error: No videos found at {videos_dir}. Run heygen_producer.py first.",
                  file=sys.stderr)
            sys.exit(1)

        script_files = sorted(scripts_dir.glob("script_*.json")) if scripts_dir.exists() else []
        scripts = {}
        for sf in script_files:
            data = json.loads(sf.read_text(encoding="utf-8"))
            scripts[data.get("number")] = data

        videos = sorted(videos_dir.glob("script_*.mp4"))
        if not videos:
            print(f"Error: No script_*.mp4 files in {videos_dir}", file=sys.stderr)
            sys.exit(1)

        ids = self.resolve_integration_ids(platforms)
        if not ids:
            print("Error: No integrations resolved. Check POSTIZ_API_KEY and "
                  "connected channels.", file=sys.stderr)
            sys.exit(1)

        results = {"scheduled": 0, "failed": 0, "posts": []}
        publish_at = start_date
        used_dates = set()

        for video in videos:
            num = int(re.search(r"(\d+)", video.stem).group(1))
            script = scripts.get(num, {})

            # Upload once, reference in every platform post
            if self.dry_run:
                media = [{"id": f"dry-{video.stem}", "path": f"file://{video.name}"}]
            else:
                try:
                    up = self._upload(video)
                    media = [{"id": up["id"], "path": up["path"]}]
                    print(f"  ↑ Uploaded {video.name}")
                except requests.RequestException as e:
                    print(f"  ✗ Failed to upload {video.name}: {e}", file=sys.stderr)
                    results["failed"] += 1
                    continue

            # Build caption from the script JSON (fall back to the hook)
            caption_hook = script.get("caption_hook", "")
            hook = script.get("hook", "")
            body = script.get("body", "")
            content = caption_hook or hook or (body[:150] if body else "")
            if content:
                content += "\n\n#shorts #selfimprovement"

            title = script.get("topic", topic) or topic

            # Next available publishing date on a video day
            while publish_at.weekday() not in VIDEO_DAYS or publish_at.date() in used_dates:
                publish_at += timedelta(days=1)

            for platform in platforms:
                if platform not in ids:
                    continue
                try:
                    post_id = self.schedule_post(
                        platform, ids[platform], content, media, title, publish_at
                    )
                    results["scheduled"] += 1
                    results["posts"].append({
                        "video": video.name, "platform": platform,
                        "postId": post_id, "date": publish_at.isoformat(),
                    })
                except requests.RequestException as e:
                    print(f"  ✗ Failed to schedule {platform} for {video.name}: {e}",
                          file=sys.stderr)
                    results["failed"] += 1

            used_dates.add(publish_at.date())
            publish_at += timedelta(days=interval_days)

        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule NeuroForge videos to TikTok/IG/YouTube via Postiz"
    )
    parser.add_argument("--topic", required=True, help='Topic e.g. "Stop Overthinking"')
    parser.add_argument("--faculty", default="", help="Faculty name (informational)")
    parser.add_argument("--platforms", default="tiktok,instagram,youtube",
                        help="Comma-separated platforms (default: tiktok,instagram,youtube)")
    parser.add_argument("--start-date", default=None,
                        help="First publish date (YYYY-MM-DD, default: next video day)")
    parser.add_argument("--interval-days", type=int, default=2,
                        help="Days between posts (default: 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print payloads without calling the API")
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("POSTIZ_API_KEY", "")
    if not api_key and not args.dry_run:
        print("Error: POSTIZ_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    base_url = os.getenv("POSTIZ_BASE_URL", DEFAULT_BASE_URL)
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
    # Align to the next video day
    while start.weekday() not in VIDEO_DAYS:
        start += timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"  POSTIZ POSTING — {args.topic}")
    print(f"  Platforms: {', '.join(platforms)}")
    print(f"  Start:     {start.date()} (video days: Mon/Wed/Fri)")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Postiz:    {base_url}")
    print(f"{'='*60}\n")

    integration = PostizIntegration(base_url, api_key, dry_run=args.dry_run)
    results = integration.schedule_topic_videos(args.topic, platforms, start, args.interval_days)

    print(f"\n{'='*60}")
    print(f"  SCHEDULED: {results['scheduled']}  FAILED: {results['failed']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
