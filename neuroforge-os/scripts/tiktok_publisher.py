#!/usr/bin/env python3
"""
NeuroForge OS — TikTok Publisher
==================================
Posts generated videos to TikTok using the Content Posting API (FILE_UPLOAD).
Reads from output/{topic}/videos/ and matching scripts_parsed/script_NN.json
for captions and hashtags.

Prerequisites:
    Complete OAuth flow once to get tokens, then set in .env:
        TIKTOK_CLIENT_KEY
        TIKTOK_CLIENT_SECRET
        TIKTOK_ACCESS_TOKEN
        TIKTOK_REFRESH_TOKEN
        TIKTOK_OPEN_ID

    See README — TikTok Setup for the one-time OAuth flow instructions.

Usage:
    # Post videos for a topic (respects 15/day cap)
    python tiktok_publisher.py \\
        --topic "Stop Overthinking" \\
        --faculty "Dr. Nova Vale" \\
        [--scripts 1-5]       # optional: only post scripts 1–5
        [--privacy SELF_ONLY] # default: PUBLIC_TO_EVERYONE (use SELF_ONLY for testing)
        [--dry-run]           # print payloads without calling TikTok API

Output:
    output/{topic}/tiktok_publish_log.json  — publish_ids + status per video
"""

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

TIKTOK_API_BASE = "https://open.tiktokapis.com"

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB — well within the 5–64 MB per-chunk limit
DAILY_POST_CAP = 15             # TikTok hard cap per creator account per 24h
RATE_LIMIT_DELAY = 12           # seconds between init calls (6 req/min per token)


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_tokens() -> dict:
    """Load TikTok tokens from environment variables."""
    required = ["TIKTOK_ACCESS_TOKEN", "TIKTOK_OPEN_ID"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print("Error: Missing TikTok environment variables:")
        for k in missing:
            print(f"  {k}")
        print("\nRun the one-time OAuth flow to get tokens.")
        print("See .env.example for details.")
        sys.exit(1)
    return {
        "access_token":  os.environ["TIKTOK_ACCESS_TOKEN"],
        "refresh_token": os.environ.get("TIKTOK_REFRESH_TOKEN", ""),
        "open_id":       os.environ["TIKTOK_OPEN_ID"],
        "client_key":    os.environ.get("TIKTOK_CLIENT_KEY", ""),
        "client_secret": os.environ.get("TIKTOK_CLIENT_SECRET", ""),
    }


def _refresh_access_token(tokens: dict) -> dict:
    """Exchange refresh_token for a new access_token. Updates tokens in-place."""
    if not tokens["client_key"] or not tokens["client_secret"] or not tokens["refresh_token"]:
        print("Warning: Cannot refresh token — TIKTOK_CLIENT_KEY/SECRET/REFRESH_TOKEN not set.")
        return tokens

    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key":     tokens["client_key"],
            "client_secret":  tokens["client_secret"],
            "grant_type":     "refresh_token",
            "refresh_token":  tokens["refresh_token"],
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Warning: Token refresh failed ({resp.status_code}): {resp.text}")
        return tokens

    data = resp.json()
    tokens["access_token"]  = data["access_token"]
    tokens["refresh_token"] = data.get("refresh_token", tokens["refresh_token"])
    print("  ✓ Access token refreshed.")
    return tokens


def _auth_headers(tokens: dict) -> dict:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type":  "application/json; charset=UTF-8",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TikTok Content Posting API
# ─────────────────────────────────────────────────────────────────────────────

def init_video_upload(tokens: dict, video_path: Path, caption: str,
                      privacy: str, dry_run: bool) -> tuple[str, str]:
    """
    Call POST /v2/post/publish/video/init/ to register the upload.
    Returns (publish_id, upload_url).
    """
    video_size = video_path.stat().st_size
    total_chunk_count = math.ceil(video_size / CHUNK_SIZE)

    payload = {
        "post_info": {
            "title":         caption,          # caption + hashtags
            "privacy_level": privacy,          # PUBLIC_TO_EVERYONE | SELF_ONLY | FOLLOWER_OF_CREATOR
            "disable_duet":  False,
            "disable_stitch": False,
            "disable_comment": False,
        },
        "source_info": {
            "source":             "FILE_UPLOAD",
            "video_size":         video_size,
            "chunk_size":         CHUNK_SIZE,
            "total_chunk_count":  total_chunk_count,
        },
    }

    if dry_run:
        print(f"    [DRY RUN] POST /v2/post/publish/video/init/")
        print(f"    Caption: {caption[:80]}{'...' if len(caption) > 80 else ''}")
        print(f"    Size:    {video_size // 1024 // 1024} MB  |  Chunks: {total_chunk_count}")
        print(f"    Privacy: {privacy}")
        return f"dry_publish_{video_path.stem}", "https://dry-run-upload-url"

    resp = requests.post(
        f"{TIKTOK_API_BASE}/v2/post/publish/video/init/",
        headers=_auth_headers(tokens),
        json=payload,
        timeout=30,
    )

    if resp.status_code == 401:
        print("  Access token expired — refreshing...")
        tokens = _refresh_access_token(tokens)
        resp = requests.post(
            f"{TIKTOK_API_BASE}/v2/post/publish/video/init/",
            headers=_auth_headers(tokens),
            json=payload,
            timeout=30,
        )

    if not resp.ok:
        raise RuntimeError(f"init failed ({resp.status_code}): {resp.text}")

    data = resp.json().get("data", {})
    return data["publish_id"], data["upload_url"]


def upload_chunks(upload_url: str, video_path: Path, dry_run: bool) -> bool:
    """PUT video chunks to the TikTok upload URL."""
    if dry_run:
        print(f"    [DRY RUN] Would upload {video_path.name} in chunks")
        return True

    video_size = video_path.stat().st_size
    total_chunks = math.ceil(video_size / CHUNK_SIZE)

    with open(video_path, "rb") as f:
        for chunk_index in range(total_chunks):
            chunk_data = f.read(CHUNK_SIZE)
            start = chunk_index * CHUNK_SIZE
            end = start + len(chunk_data) - 1

            resp = requests.put(
                upload_url,
                headers={
                    "Content-Type":  "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Length": str(len(chunk_data)),
                },
                data=chunk_data,
                timeout=120,
            )

            if not resp.ok:
                print(f"  ✗ Chunk {chunk_index + 1}/{total_chunks} failed: {resp.status_code}")
                return False

            print(f"    chunk {chunk_index + 1}/{total_chunks} ✓", end="\r", flush=True)

    print()  # newline after chunk progress
    return True


def poll_publish_status(tokens: dict, publish_id: str,
                        timeout_s: int = 300, dry_run: bool = False) -> str:
    """
    Poll POST /v2/post/publish/status/fetch/ until published or failed.
    Returns final status string.
    """
    if dry_run:
        return "dry_run_success"

    print(f"    Waiting for publish_id={publish_id}...", end="", flush=True)
    deadline = time.time() + timeout_s
    interval = 10

    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.post(
            f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/",
            headers=_auth_headers(tokens),
            json={"publish_id": publish_id},
            timeout=15,
        )
        if not resp.ok:
            print(f" ✗ status check failed: {resp.status_code}")
            return "error"

        data = resp.json().get("data", {})
        status = data.get("status", "PROCESSING")

        if status in ("PUBLISH_COMPLETE", "PUBLISHED_BY_SSP", "DOWNLOADED_BY_SSP"):
            print(" ✓")
            return status
        elif status in ("FAILED", "PUBLISH_FAILED"):
            fail_reason = data.get("fail_reason", "unknown")
            print(f" ✗ FAILED: {fail_reason}")
            return f"failed: {fail_reason}"
        else:
            print(".", end="", flush=True)
            interval = min(interval * 1.2, 30)

    print(f" ✗ TIMEOUT after {timeout_s}s")
    return "timeout"


# ─────────────────────────────────────────────────────────────────────────────
# Caption builder
# ─────────────────────────────────────────────────────────────────────────────

def build_caption(script: dict) -> str:
    """
    Use tiktok_caption if Claude generated it; otherwise assemble from parts.
    TikTok caption max = 2,200 chars.
    """
    if script.get("tiktok_caption"):
        return script["tiktok_caption"]

    parts = []
    if script.get("caption_hook"):
        parts.append(script["caption_hook"])
    if script.get("hashtags"):
        parts.append(script["hashtags"])

    caption = "\n\n".join(parts) if parts else script.get("hook", "")
    return caption[:2200]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_range(s: str) -> list[int]:
    nums = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            nums.update(range(int(a), int(b) + 1))
        else:
            nums.add(int(part))
    return sorted(nums)


def main():
    parser = argparse.ArgumentParser(description="Post NeuroForge videos to TikTok")
    parser.add_argument("--topic",   required=True, help='Topic e.g. "Stop Overthinking"')
    parser.add_argument("--scripts", default="",
                        help="Script numbers to post, e.g. '1-5' or '1,3,7' (default: all)")
    parser.add_argument("--privacy", default="PUBLIC_TO_EVERYONE",
                        choices=["PUBLIC_TO_EVERYONE", "SELF_ONLY", "FOLLOWER_OF_CREATOR"],
                        help="TikTok post visibility (use SELF_ONLY for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print payloads without calling TikTok API")
    args = parser.parse_args()

    tokens = _load_tokens()

    safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", args.topic.lower())
    videos_dir  = OUTPUT_DIR / safe_topic / "videos"
    scripts_dir = OUTPUT_DIR / safe_topic / "scripts_parsed"
    log_path    = OUTPUT_DIR / safe_topic / "tiktok_publish_log.json"

    if not videos_dir.exists():
        print(f"Error: No videos folder at {videos_dir}")
        print("Run heygen_producer.py first.")
        sys.exit(1)

    video_files = sorted(videos_dir.glob("script_*.mp4"))
    if not video_files:
        print(f"Error: No script_*.mp4 files in {videos_dir}")
        sys.exit(1)

    # Filter by --scripts range
    if args.scripts:
        wanted = set(parse_range(args.scripts))
        video_files = [f for f in video_files
                       if int(re.search(r"(\d+)", f.stem).group(1)) in wanted]

    if len(video_files) > DAILY_POST_CAP:
        print(f"Warning: {len(video_files)} videos requested but TikTok cap is {DAILY_POST_CAP}/day.")
        print(f"  Only the first {DAILY_POST_CAP} will be posted. Re-run tomorrow for the rest.")
        video_files = video_files[:DAILY_POST_CAP]

    print(f"\n{'='*60}")
    print(f"  TIKTOK PUBLISHER")
    print(f"  Topic:    {args.topic}")
    print(f"  Videos:   {len(video_files)}")
    print(f"  Privacy:  {args.privacy}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    # Load existing log
    publish_log = []
    if log_path.exists():
        publish_log = json.loads(log_path.read_text(encoding="utf-8"))
    already_posted = {entry["video"] for entry in publish_log if "published" in entry.get("status", "")}

    results = []

    for video_path in video_files:
        num = int(re.search(r"(\d+)", video_path.stem).group(1))

        if video_path.name in already_posted:
            print(f"  Skip {video_path.name} — already posted.")
            continue

        # Load script JSON for caption
        script_file = scripts_dir / f"script_{num:02d}.json"
        script = json.loads(script_file.read_text(encoding="utf-8")) if script_file.exists() else {}
        caption = build_caption(script)

        print(f"  [{num:02d}] {video_path.name}")
        print(f"    Caption: {caption[:80]}{'...' if len(caption) > 80 else ''}")

        try:
            publish_id, upload_url = init_video_upload(
                tokens, video_path, caption, args.privacy, args.dry_run
            )

            upload_ok = upload_chunks(upload_url, video_path, args.dry_run)
            if not upload_ok:
                results.append({"video": video_path.name, "status": "upload_failed", "publish_id": publish_id})
                continue

            status = poll_publish_status(tokens, publish_id, dry_run=args.dry_run)
            results.append({"video": video_path.name, "status": status, "publish_id": publish_id})

        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({"video": video_path.name, "status": f"error: {e}", "publish_id": None})

        # Respect rate limit: 6 init calls per minute
        if not args.dry_run and video_path != video_files[-1]:
            time.sleep(RATE_LIMIT_DELAY)

    # Save log
    publish_log.extend(results)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(publish_log, indent=2, ensure_ascii=False), encoding="utf-8")

    success = sum(1 for r in results if "failed" not in r["status"] and "error" not in r["status"])
    failed  = len(results) - success

    print(f"\n{'='*60}")
    print(f"  PUBLISH COMPLETE")
    print(f"  Posted:   {success}  |  Failed: {failed}")
    print(f"  Log:      {log_path.name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
