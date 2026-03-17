#!/usr/bin/env python3
"""
NeuroForge OS — HeyGen Avatar Setup
=====================================
Queries the HeyGen API to find the best-matching stock avatar and voice
for each faculty member, then writes HEYGEN_AVATAR_ID_* and HEYGEN_VOICE_ID_*
to a .env file ready for use by heygen_producer.py.

Usage:
    export HEYGEN_API_KEY="your_key_here"
    python heygen_setup.py [--faculty "Dr. Nova Vale"] [--save]

    --faculty   Only configure one faculty (default: all)
    --save      Write IDs to .heygen.env (default: print only)
    --list      Just list all available avatars/voices and exit

Setup steps:
    1. Sign up at heygen.com → Settings → API → copy your API key
    2. Run: export HEYGEN_API_KEY="..."
    3. Run: python heygen_setup.py --save
    4. Review .heygen.env and source it: source .heygen.env
    5. Run heygen_producer.py --dry-run to confirm
"""

import argparse
import json
import os
import sys
import re
from pathlib import Path

import requests

HEYGEN_API_BASE = "https://api.heygen.com"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ENV_FILE = PROJECT_DIR / ".heygen.env"

# What we're looking for per faculty
FACULTY_SEARCH_PROFILES = {
    "Dr. Nova Vale": {
        "avatar_keywords": ["woman", "professional", "calm", "warm", "30"],
        "voice_keywords":  ["calm", "female", "professional", "soft"],
        "gender": "female",
        "description": "Professional woman, 30s, warm, soft lighting",
    },
    "Kai Ren": {
        "avatar_keywords": ["man", "young", "sharp", "confident", "asian"],
        "voice_keywords":  ["male", "confident", "fast", "direct"],
        "gender": "male",
        "description": "Sharp-looking man, late 20s, clean, minimal",
    },
    "Marcus Voss": {
        "avatar_keywords": ["man", "strong", "commanding", "mature"],
        "voice_keywords":  ["male", "deep", "deliberate", "strong"],
        "gender": "male",
        "description": "Strong man, 35–40, commanding presence",
    },
    "Luna Hart": {
        "avatar_keywords": ["woman", "warm", "natural", "approachable"],
        "voice_keywords":  ["female", "warm", "conversational", "soft"],
        "gender": "female",
        "description": "Approachable woman, late 20s, warm, natural",
    },
    "Dr. Orion Hale": {
        "avatar_keywords": ["man", "scholarly", "professional", "mature"],
        "voice_keywords":  ["male", "precise", "professional", "clear"],
        "gender": "male",
        "description": "Professional man, 40s, scholarly, lab coat — custom photo avatar",
        # Upload the approved photo to HeyGen → Avatars → Photo Avatar, then set:
        # custom_avatar_id: the ID returned by HeyGen after upload
        "custom_avatar_id": None,  # TODO: set after uploading photo to HeyGen
    },
}


def _headers() -> dict:
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        print("Error: HEYGEN_API_KEY is not set.")
        print("  Get your key from: heygen.com → Settings → API")
        print("  Then: export HEYGEN_API_KEY='...'")
        sys.exit(1)
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def fetch_avatars() -> list[dict]:
    """Fetch all available stock avatars from HeyGen."""
    resp = requests.get(f"{HEYGEN_API_BASE}/v2/avatars", headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    avatars = data.get("data", {}).get("avatars", [])
    print(f"  Fetched {len(avatars)} avatars from HeyGen")
    return avatars


def fetch_voices() -> list[dict]:
    """Fetch all available voices from HeyGen."""
    resp = requests.get(f"{HEYGEN_API_BASE}/v2/voices", headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    voices = data.get("data", {}).get("voices", [])
    print(f"  Fetched {len(voices)} voices from HeyGen")
    return voices


def score_avatar(avatar: dict, profile: dict) -> int:
    """Score an avatar against a faculty profile. Higher = better match."""
    score = 0
    name = (avatar.get("avatar_name", "") + " " + avatar.get("preview_video_url", "")).lower()
    gender = avatar.get("gender", "").lower()

    if profile["gender"] and gender == profile["gender"]:
        score += 10

    for keyword in profile["avatar_keywords"]:
        if keyword.lower() in name:
            score += 3

    return score


def score_voice(voice: dict, profile: dict) -> int:
    """Score a voice against a faculty profile. Higher = better match."""
    score = 0
    name = (voice.get("name", "") + " " + voice.get("language", "") + " " +
            voice.get("preview_audio", "")).lower()
    gender = voice.get("gender", "").lower()
    language = voice.get("language", "").lower()

    # Must be English
    if "en" in language or "english" in language:
        score += 5

    if profile["gender"] and gender == profile["gender"]:
        score += 10

    for keyword in profile["voice_keywords"]:
        if keyword.lower() in name:
            score += 2

    return score


def find_best_matches(faculty: str, avatars: list[dict], voices: list[dict]) -> dict:
    """Return the top avatar and voice match for a faculty member."""
    profile = FACULTY_SEARCH_PROFILES[faculty]

    # Use custom photo avatar if configured, skip stock avatar search
    custom_id = profile.get("custom_avatar_id")
    if custom_id:
        custom_avatar = {"avatar_id": custom_id, "avatar_name": f"[custom photo] {faculty}"}
        top_avatars = [(99, custom_avatar)]
        best_avatar = custom_avatar
    else:
        scored_avatars = sorted(
            [(score_avatar(a, profile), a) for a in avatars],
            key=lambda x: x[0],
            reverse=True,
        )
        top_avatars = [(s, a) for s, a in scored_avatars[:5] if s > 0]
        best_avatar = scored_avatars[0][1] if scored_avatars else None

    scored_voices = sorted(
        [(score_voice(v, profile), v) for v in voices],
        key=lambda x: x[0],
        reverse=True,
    )
    top_voices = [(s, v) for s, v in scored_voices[:5] if s > 0]

    return {
        "faculty": faculty,
        "description": profile["description"],
        "top_avatars": top_avatars,
        "top_voices": top_voices,
        "best_avatar": best_avatar,
        "best_voice": scored_voices[0][1] if scored_voices else None,
    }


def print_matches(result: dict):
    """Print faculty match results clearly."""
    print(f"\n{'─'*60}")
    print(f"  {result['faculty']}")
    print(f"  Profile: {result['description']}")
    print(f"{'─'*60}")

    print("  TOP AVATAR MATCHES:")
    if result["top_avatars"]:
        for score, av in result["top_avatars"]:
            print(f"    [{score:2d}] {av.get('avatar_id', '?'):<30} {av.get('avatar_name', 'unnamed')}")
    else:
        print("    (no matches — will use first available)")

    print("  TOP VOICE MATCHES:")
    if result["top_voices"]:
        for score, v in result["top_voices"]:
            print(f"    [{score:2d}] {v.get('voice_id', '?'):<30} {v.get('name', 'unnamed')} ({v.get('language', '')})")
    else:
        print("    (no matches — will use first available)")

    best_av = result["best_avatar"]
    best_vo = result["best_voice"]
    if best_av:
        print(f"\n  → Selected avatar: {best_av['avatar_id']} ({best_av.get('avatar_name', '')})")
    if best_vo:
        print(f"  → Selected voice:  {best_vo['voice_id']} ({best_vo.get('name', '')})")


def build_env_key(faculty: str, kind: str) -> str:
    """Build env var name like HEYGEN_AVATAR_ID_DR_NOVA_VALE."""
    safe = re.sub(r"[^A-Z0-9]", "_", faculty.upper()).strip("_")
    return f"HEYGEN_{kind}_ID_{safe}"


def write_env_file(results: list[dict]):
    """Write selected avatar/voice IDs to .heygen.env."""
    lines = [
        "# NeuroForge — HeyGen Avatar & Voice IDs",
        "# Generated by heygen_setup.py",
        "# Source with: source .heygen.env",
        "",
    ]
    for r in results:
        av = r["best_avatar"]
        vo = r["best_voice"]
        av_key = build_env_key(r["faculty"], "AVATAR")
        vo_key = build_env_key(r["faculty"], "VOICE")
        av_id = av["avatar_id"] if av else "REPLACE_ME"
        vo_id = vo["voice_id"] if vo else "REPLACE_ME"
        lines.append(f"# {r['faculty']}")
        lines.append(f"export {av_key}={av_id!r}")
        lines.append(f"export {vo_key}={vo_id!r}")
        lines.append("")

    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ Config saved to: {ENV_FILE}")
    print(f"   Source it with:  source {ENV_FILE.relative_to(PROJECT_DIR)}")
    print(f"   Then run:        python scripts/heygen_producer.py --topic 'Stop Overthinking' --faculty 'Dr. Nova Vale' --dry-run")


def main():
    parser = argparse.ArgumentParser(description="Find best HeyGen avatars/voices for NeuroForge faculty")
    parser.add_argument("--faculty", default="", help="Configure one faculty only (default: all)")
    parser.add_argument("--save", action="store_true", help="Write IDs to .heygen.env")
    parser.add_argument("--list", action="store_true", help="List all available avatars and voices")
    args = parser.parse_args()

    print("\n[ Fetching HeyGen library ]")
    avatars = fetch_avatars()
    voices = fetch_voices()

    if args.list:
        print("\nALL AVATARS:")
        for av in avatars:
            print(f"  {av.get('avatar_id', '?'):<35} {av.get('avatar_name', '')} [{av.get('gender', '')}]")
        print("\nALL VOICES:")
        for v in voices:
            print(f"  {v.get('voice_id', '?'):<35} {v.get('name', '')} [{v.get('language', '')} / {v.get('gender', '')}]")
        return

    faculty_list = [args.faculty] if args.faculty else list(FACULTY_SEARCH_PROFILES.keys())

    print(f"\n[ Matching {len(faculty_list)} faculty member(s) ]")
    results = []
    for faculty in faculty_list:
        if faculty not in FACULTY_SEARCH_PROFILES:
            print(f"Unknown faculty: {faculty}")
            continue
        result = find_best_matches(faculty, avatars, voices)
        print_matches(result)
        results.append(result)

    if args.save and results:
        write_env_file(results)
    elif results:
        print("\nRun with --save to write IDs to .heygen.env")


if __name__ == "__main__":
    main()
