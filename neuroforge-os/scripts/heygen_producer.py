#!/usr/bin/env python3
"""
NeuroForge OS — HeyGen Video Producer
=======================================
Reads parsed script JSONs and submits each to the HeyGen API to generate
a talking-head video using the faculty avatar. Polls for completion and
downloads MP4 files.

Prerequisites:
    export HEYGEN_API_KEY="your_key_here"
    export HEYGEN_AVATAR_ID_DR_NOVA_VALE="avatar_id_from_heygen"
    export HEYGEN_VOICE_ID_DR_NOVA_VALE="voice_id_from_heygen"

Usage:
    # Parse scripts first:
    python parse_scripts.py \
        --file output/stop_overthinking/04_shorts_scripts_*.md \
        --topic "Stop Overthinking"

    # Then generate videos:
    python heygen_producer.py \
        --topic "Stop Overthinking" \
        --faculty "Dr. Nova Vale" \
        [--scripts 1-5]       # optional: only generate scripts 1–5
        [--dry-run]           # print payloads without calling API

Setup Guide — Dr. Nova Vale Avatar:
    1. Sign up at heygen.com
    2. Go to Avatars → Create Avatar → Instant Avatar
       - Upload a photorealistic portrait image of "Dr. Nova Vale"
         (professional woman, 30s, warm, soft lighting, neutral background)
       - Or use HeyGen's stock avatar library and pick the closest match
    3. Clone the voice:
       - Go to Voice → Voice Clone → upload 1–2 min audio sample
       - Voice character: calm, measured, slightly clinical
    4. Note the avatar_id and voice_id from the HeyGen dashboard
    5. Set them as environment variables (see above)

Output:
    output/stop_overthinking/videos/
        script_01.mp4
        script_02.mp4
        ...
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

HEYGEN_API_BASE = "https://api.heygen.com"

# Avatar/voice IDs per faculty — set via env vars after creating in HeyGen
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


FACULTY_HEYGEN_CONFIG = {
    "Dr. Nova Vale": {
        "avatar_id":  _env("HEYGEN_AVATAR_ID_DR_NOVA_VALE"),
        "voice_id":   _env("HEYGEN_VOICE_ID_DR_NOVA_VALE"),
        "background": {"type": "color", "value": "#F5F0EB"},  # warm off-white
        "dimension":  {"width": 720, "height": 1280},
    },
    "Kai Ren": {
        "avatar_id":  _env("HEYGEN_AVATAR_ID_KAI_REN"),
        "voice_id":   _env("HEYGEN_VOICE_ID_KAI_REN"),
        "background": {"type": "color", "value": "#0D0D0D"},  # near-black
        "dimension":  {"width": 720, "height": 1280},
    },
    "Marcus Voss": {
        "avatar_id":  _env("HEYGEN_AVATAR_ID_MARCUS_VOSS"),
        "voice_id":   _env("HEYGEN_VOICE_ID_MARCUS_VOSS"),
        "background": {"type": "color", "value": "#1A1A1A"},
        "dimension":  {"width": 720, "height": 1280},
    },
    "Luna Hart": {
        "avatar_id":  _env("HEYGEN_AVATAR_ID_LUNA_HART"),
        "voice_id":   _env("HEYGEN_VOICE_ID_LUNA_HART"),
        "background": {"type": "color", "value": "#FDF6F0"},  # warm cream
        "dimension":  {"width": 720, "height": 1280},
    },
    "Dr. Orion Hale": {
        "avatar_id":  _env("HEYGEN_AVATAR_ID_DR_ORION_HALE"),
        "voice_id":   _env("HEYGEN_VOICE_ID_DR_ORION_HALE"),
        "background": {"type": "color", "value": "#F0F4F8"},  # clean blue-grey
        "dimension":  {"width": 720, "height": 1280},
    },
}


def _headers() -> dict:
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        print("Error: HEYGEN_API_KEY environment variable not set.")
        sys.exit(1)
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def submit_video(script: dict, faculty: str, dry_run: bool = False) -> str:
    """Submit a video generation job. Returns video_id."""
    config = FACULTY_HEYGEN_CONFIG.get(faculty)
    if not config:
        print(f"Error: No HeyGen config for faculty '{faculty}'")
        sys.exit(1)

    if not config["avatar_id"] or not config["voice_id"]:
        env_key = re.sub(r"[^A-Z0-9]", "_", faculty.upper()).strip("_")
        print(f"Error: avatar_id or voice_id not set for {faculty}.")
        print(f"  Set HEYGEN_AVATAR_ID_{env_key} and")
        print(f"      HEYGEN_VOICE_ID_{env_key}")
        sys.exit(1)

    # Build the spoken text — hook bold at the start, then body
    spoken_text = f"{script['hook']}\n\n{script['body']}"

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": config["avatar_id"],
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": spoken_text,
                    "voice_id": config["voice_id"],
                    "speed": 0.95,  # slightly slower = more composed delivery
                },
                "background": config["background"],
            }
        ],
        "dimension": config["dimension"],
        "caption": False,  # captions added in post via CapCut
        "title": f"{faculty} — Script {script['number']:02d}",
    }

    if dry_run:
        print(f"  [DRY RUN] Script {script['number']:02d} payload:")
        print(f"    Title:  {payload['title']}")
        print(f"    Length: ~{len(spoken_text)} chars")
        print(f"    Hook:   {script['hook'][:60]}...")
        return f"dry_run_{script['number']:02d}"

    resp = requests.post(
        f"{HEYGEN_API_BASE}/v2/video/generate",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    video_id = data["data"]["video_id"]
    print(f"  → Submitted script {script['number']:02d}: video_id={video_id}")
    return video_id


def poll_until_complete(video_id: str, timeout_s: int = 600) -> str:
    """Poll video status until complete. Returns download URL."""
    print(f"  ⏳ Waiting for video {video_id}...", end="", flush=True)
    deadline = time.time() + timeout_s
    interval = 10

    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.get(
            f"{HEYGEN_API_BASE}/v1/video_status.get",
            headers=_headers(),
            params={"video_id": video_id},
            timeout=15,
        )
        resp.raise_for_status()
        status_data = resp.json()["data"]
        status = status_data.get("status")

        if status == "completed":
            print(" ✓")
            return status_data["video_url"]
        elif status == "failed":
            print(f" ✗ FAILED: {status_data.get('error', 'unknown error')}")
            return None
        else:
            print(".", end="", flush=True)
            interval = min(interval * 1.2, 30)  # back off up to 30s

    print(f" ✗ TIMEOUT after {timeout_s}s")
    return None


def download_video(url: str, output_path: Path) -> bool:
    """Download video MP4 to output_path."""
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    print(f"  ✓ Saved: {output_path.name} ({output_path.stat().st_size // 1024} KB)")
    return True


def parse_range(s: str) -> list[int]:
    """Parse '1-5' or '1,3,5' or '1-3,7' into a list of ints."""
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
    parser = argparse.ArgumentParser(description="Generate HeyGen videos from parsed scripts")
    parser.add_argument("--topic", required=True, help='Topic e.g. "Stop Overthinking"')
    parser.add_argument("--faculty", required=True, help='Faculty e.g. "Dr. Nova Vale"')
    parser.add_argument("--scripts", default="",
                        help="Script numbers to process, e.g. '1-5' or '1,3,7' (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print payloads without calling HeyGen API")
    args = parser.parse_args()

    safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", args.topic.lower())
    scripts_dir = OUTPUT_DIR / safe_topic / "scripts_parsed"
    videos_dir = OUTPUT_DIR / safe_topic / "videos"

    if not scripts_dir.exists():
        print(f"Error: No parsed scripts found at {scripts_dir}")
        print(f"Run parse_scripts.py first.")
        sys.exit(1)

    script_files = sorted(scripts_dir.glob("script_*.json"))
    if not script_files:
        print(f"Error: No script_*.json files in {scripts_dir}")
        sys.exit(1)

    # Filter by --scripts range if provided
    if args.scripts:
        wanted = set(parse_range(args.scripts))
        script_files = [f for f in script_files
                        if int(re.search(r"(\d+)", f.stem).group(1)) in wanted]

    print(f"\n{'='*60}")
    print(f"  HEYGEN PRODUCER")
    print(f"  Topic:    {args.topic}")
    print(f"  Faculty:  {args.faculty}")
    print(f"  Scripts:  {len(script_files)}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}")

    jobs = []  # (script_num, video_id)

    # Submit all jobs first
    print("\n[ Submitting jobs ]")
    for sf in script_files:
        script = json.loads(sf.read_text(encoding="utf-8"))
        video_id = submit_video(script, args.faculty, dry_run=args.dry_run)
        jobs.append((script, video_id))

    if args.dry_run:
        print(f"\n✅ Dry run complete — {len(jobs)} jobs would be submitted.")
        return

    # Poll and download
    print(f"\n[ Polling & downloading ]")
    success, failed = 0, 0
    for script, video_id in jobs:
        n = script["number"]
        url = poll_until_complete(video_id)
        if url:
            out = videos_dir / f"script_{n:02d}.mp4"
            download_video(url, out)
            success += 1
        else:
            print(f"  ✗ Script {n:02d} failed — skipping download.")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  PRODUCTION COMPLETE")
    print(f"  Videos:   {success} generated, {failed} failed")
    print(f"  Output:   {videos_dir}")
    print(f"{'='*60}\n")

    # Write a posting schedule for the generated videos
    _write_posting_schedule(args.topic, args.faculty, script_files, videos_dir)


def _write_posting_schedule(topic: str, faculty: str, script_files: list, videos_dir: Path):
    """Write a simple posting schedule markdown for the generated videos."""
    from datetime import date, timedelta

    safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
    out = OUTPUT_DIR / safe_topic / "posting_schedule.md"

    # Map days to script types per MARKETING_OPS.md
    day_map = {
        0: "Hook-led script (Mon)",
        1: "Quote graphic (Tue)",  # not video
        2: "Mechanism-led script (Wed)",
        3: "Carousel post (Thu)",  # not video
        4: "Counterintuitive-led script (Fri)",
        5: "Tool-led script (Sat)",
        6: "Best performer repost (Sun)",
    }
    video_days = [0, 2, 4, 5]  # Mon, Wed, Fri, Sat

    video_nums = [int(re.search(r"(\d+)", f.stem).group(1)) for f in script_files
                  if f.suffix == ".json"]

    lines = [
        f"# Posting Schedule — {topic}",
        f"**Faculty:** {faculty}",
        f"**Generated:** {date.today().isoformat()}",
        "",
        "| Date | Day | Script | Platform | Caption |",
        "|------|-----|--------|----------|---------|",
    ]

    start = date.today()
    video_queue = list(video_nums)
    current_date = start
    posted = 0

    while video_queue:
        dow = current_date.weekday()
        if dow in video_days and video_queue:
            n = video_queue.pop(0)
            lines.append(
                f"| {current_date.isoformat()} | {current_date.strftime('%A')} "
                f"| script_{n:02d}.mp4 | TikTok + Reels + Shorts | _(add caption from script JSON)_ |"
            )
            posted += 1
        current_date += timedelta(days=1)

    lines += [
        "",
        f"**Total videos scheduled:** {posted}",
        f"**Videos folder:** `{videos_dir}`",
        "",
        "## Caption Template",
        "Use the `caption_hook` field from each `scripts_parsed/script_NN.json` as your caption.",
        "Append: `\n\n👇 Full breakdown — link in bio`",
        "",
        "## Text Overlay",
        "Use the `text_overlay` field from each script JSON.",
        "Add in CapCut or HeyGen's built-in caption tool.",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  📅 Posting schedule saved: {out.name}")


if __name__ == "__main__":
    main()
