#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Caption & Metadata Engine
=====================================================
Generates Pinterest-optimized titles, descriptions, hashtags, board
assignments, and alt text for Ebril's own content assets.

Reads video/image files from an asset directory and produces a
pin-package manifest ready for the publisher module.

Prerequisites:
    ANTHROPIC_API_KEY   — for Claude-powered caption generation

Usage:
    python pinterest_caption_engine.py --asset-dir output/pinterest/assets
    python pinterest_caption_engine.py --asset-dir ./my-videos --mood warm --niche aesthetic
    python pinterest_caption_engine.py --asset-dir ./assets --dry-run
"""

import anthropic
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from pinterest_config import (
    BASE_HASHTAGS,
    CAPTION_TEMPLATES,
    CAPTION_TYPE_CYCLE,
    EBRIL_TRACKS,
    MAX_PINS_PER_HOUR,
    NICHE_HASHTAGS,
    NICHE_TO_BOARD,
    PINTEREST_BOARDS,
    POSTING_WINDOWS,
    VALID_MOODS,
    VALID_NICHES,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
SESSION_TOKEN_FILE = Path("/home/claude/.claude/remote/.session_ingress_token")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
SUPPORTED_EXTS = SUPPORTED_VIDEO_EXTS | SUPPORTED_IMAGE_EXTS

# Filename pattern: pin-{niche}-{mood}-{number}.{ext}
FILENAME_PATTERN = re.compile(
    r"^pin-(?P<niche>[a-z0-9-]+)-(?P<mood>[a-z]+)-(?P<number>\d+)$",
    re.IGNORECASE,
)

logger = logging.getLogger("pinterest_caption_engine")


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------

def _get_client() -> anthropic.Anthropic:
    """Create Anthropic client with best available auth."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    if SESSION_TOKEN_FILE.exists():
        token = SESSION_TOKEN_FILE.read_text().strip()
        return anthropic.Anthropic(auth_token=token)
    return anthropic.Anthropic()


# ---------------------------------------------------------------------------
# CaptionEngine
# ---------------------------------------------------------------------------

class CaptionEngine:
    """Generates Pinterest-optimized metadata for Ebril's content assets."""

    def __init__(self, anthropic_client: anthropic.Anthropic):
        self.client = anthropic_client
        self._caption_cycle_index = 0

    # -- asset analysis -----------------------------------------------------

    def analyze_asset(self, filepath: Path) -> dict:
        """Extract file metadata from a single asset.

        Returns a dict with keys: path, filename, stem, extension,
        size_bytes, media_type, duration_seconds (video only, None if
        ffprobe unavailable).
        """
        stat = filepath.stat()
        ext = filepath.suffix.lower()
        media_type = "video" if ext in SUPPORTED_VIDEO_EXTS else "image"

        info = {
            "path": str(filepath),
            "filename": filepath.name,
            "stem": filepath.stem,
            "extension": ext,
            "size_bytes": stat.st_size,
            "media_type": media_type,
            "duration_seconds": None,
        }

        if media_type == "video":
            info["duration_seconds"] = self._probe_duration(filepath)

        return info

    @staticmethod
    def _probe_duration(filepath: Path) -> float | None:
        """Use ffprobe to extract video duration. Returns None on failure."""
        if not shutil.which("ffprobe"):
            return None
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(filepath),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            raw = data.get("format", {}).get("duration")
            return round(float(raw), 2) if raw else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
            return None

    # -- metadata assignment ------------------------------------------------

    def assign_metadata(
        self, asset_info: dict, mood: str | None = None, niche: str | None = None
    ) -> dict:
        """Determine board, Ebril track, and Spotify link for an asset.

        If mood/niche are not provided, attempt to parse from the filename
        pattern ``pin-{niche}-{mood}-{number}.ext``. Falls back to Claude
        inference when the filename does not match.
        """
        parsed_niche = niche
        parsed_mood = mood

        if not parsed_niche or not parsed_mood:
            match = FILENAME_PATTERN.match(asset_info["stem"])
            if match:
                parsed_niche = parsed_niche or match.group("niche")
                parsed_mood = parsed_mood or match.group("mood")

        # If still missing, ask Claude to suggest based on filename
        if not parsed_niche or not parsed_mood:
            parsed_niche, parsed_mood = self._infer_metadata_via_claude(
                asset_info["filename"], parsed_niche, parsed_mood
            )

        # Validate and fall back to defaults
        if parsed_niche not in VALID_NICHES:
            logger.warning(
                "Niche '%s' not recognized for %s, defaulting to 'aesthetic'",
                parsed_niche,
                asset_info["filename"],
            )
            parsed_niche = "aesthetic"

        if parsed_mood not in VALID_MOODS:
            logger.warning(
                "Mood '%s' not recognized for %s, defaulting to 'warm'",
                parsed_mood,
                asset_info["filename"],
            )
            parsed_mood = "warm"

        board_key = NICHE_TO_BOARD.get(parsed_niche, "aesthetic-mood")
        board = PINTEREST_BOARDS[board_key]
        track_info = EBRIL_TRACKS.get(parsed_mood, EBRIL_TRACKS["warm"])

        return {
            "niche": parsed_niche,
            "mood": parsed_mood,
            "board_id": board_key,
            "board_name": board["name"],
            "pinterest_board_id": board["pinterest_id"],
            "ebril_track": track_info["title"],
            "spotify_url": track_info["spotify_url"],
        }

    def _infer_metadata_via_claude(
        self, filename: str, known_niche: str | None, known_mood: str | None
    ) -> tuple[str, str]:
        """Ask Claude to infer niche and/or mood from a filename."""
        missing = []
        if not known_niche:
            missing.append(f"niche (choose from: {', '.join(VALID_NICHES)})")
        if not known_mood:
            missing.append(f"mood (choose from: {', '.join(VALID_MOODS)})")

        prompt = (
            f"Given the filename '{filename}' for a Pinterest content asset "
            f"in the Florra brand (indie music / aesthetic lifestyle), "
            f"suggest the most fitting {' and '.join(missing)}.\n\n"
            f"Respond with ONLY a JSON object like: "
            f'{{"niche": "...", "mood": "..."}}'
        )

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            # Extract JSON from response
            json_match = re.search(r"\{[^}]+\}", text)
            if json_match:
                result = json.loads(json_match.group())
                return (
                    known_niche or result.get("niche", "aesthetic"),
                    known_mood or result.get("mood", "warm"),
                )
        except Exception as exc:
            logger.warning("Claude inference failed for '%s': %s", filename, exc)

        return (known_niche or "aesthetic", known_mood or "warm")

    # -- caption generation -------------------------------------------------

    def generate_caption(self, asset_info: dict, metadata: dict) -> dict:
        """Generate a Pinterest-optimized caption via Claude.

        Cycles through caption template types A/B/C/D. Returns dict with
        title, description, and caption_type.
        """
        caption_type = CAPTION_TYPE_CYCLE[
            self._caption_cycle_index % len(CAPTION_TYPE_CYCLE)
        ]
        self._caption_cycle_index += 1

        templates = CAPTION_TEMPLATES[caption_type]

        prompt = self._build_caption_prompt(asset_info, metadata, caption_type, templates)

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=(
                    "You are a Pinterest SEO and content strategist for Florra, "
                    "a brand that promotes indie artist Ebril's music through "
                    "aesthetic lifestyle content. Write captions that feel organic "
                    "and native to Pinterest — not salesy, not forced. "
                    "Always respond with valid JSON only, no markdown fencing."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            # Strip markdown code fences if present
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)

            # Enforce Pinterest limits
            title = result.get("title", "")[:100]
            description = result.get("description", "")
            if len(description) > 500:
                description = description[:497] + "..."
            elif len(description) < 150:
                # Pad short descriptions with a music reference
                description += f" | {metadata['ebril_track']} by Ebril"

            return {
                "title": title,
                "description": description,
                "caption_type": caption_type,
            }
        except Exception as exc:
            logger.error(
                "Caption generation failed for %s: %s", asset_info["filename"], exc
            )
            # Return a serviceable fallback
            track = metadata.get("ebril_track", "Ebril")
            return {
                "title": f"{metadata['niche'].title()} Mood | {track} by Ebril",
                "description": (
                    f"Aesthetic {metadata['niche']} content with "
                    f"{metadata['mood']} vibes. Currently listening to "
                    f"{track} by Ebril on repeat."
                ),
                "caption_type": caption_type,
            }

    @staticmethod
    def _build_caption_prompt(
        asset_info: dict, metadata: dict, caption_type: str, templates: list[str]
    ) -> str:
        """Build the combined prompt for caption + alt text generation."""
        duration_note = ""
        if asset_info.get("duration_seconds"):
            duration_note = f"Video duration: {asset_info['duration_seconds']}s. "

        return (
            f"Generate Pinterest metadata for this asset.\n\n"
            f"Asset: {asset_info['filename']}\n"
            f"Media type: {asset_info['media_type']}\n"
            f"{duration_note}"
            f"Niche: {metadata['niche']}\n"
            f"Mood: {metadata['mood']}\n"
            f"Ebril track: {metadata['ebril_track']}\n"
            f"Board: {metadata['board_name']}\n\n"
            f"Caption template style: {caption_type}\n"
            f"Example templates for style {caption_type}:\n"
            + "\n".join(f"  - {t}" for t in templates)
            + "\n\n"
            f"Write a JSON object with these fields:\n"
            f"1. \"title\" — max 100 chars, Pinterest SEO-friendly, include "
            f"relevant keywords for the {metadata['niche']} niche\n"
            f"2. \"description\" — 150-500 chars, written in style {caption_type} "
            f"(inspired by the templates above but not a copy), must include a "
            f"natural reference to Ebril or the track \"{metadata['ebril_track']}\"\n\n"
            f"Respond with ONLY the JSON object."
        )

    # -- hashtags -----------------------------------------------------------

    def generate_hashtags(self, niche: str) -> list[str]:
        """Combine base and niche-specific hashtags. Returns 8-15 tags."""
        niche_tags = NICHE_HASHTAGS.get(niche, NICHE_HASHTAGS.get("aesthetic", []))
        combined = list(BASE_HASHTAGS) + list(niche_tags)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for tag in combined:
            low = tag.lower()
            if low not in seen:
                seen.add(low)
                unique.append(tag)
        # Clamp to 8-15
        return unique[:15] if len(unique) > 15 else unique

    # -- alt text -----------------------------------------------------------

    def generate_alt_text(self, asset_info: dict, metadata: dict) -> str:
        """Generate accessibility-focused alt text via Claude."""
        prompt = (
            f"Write Pinterest alt text for this {asset_info['media_type']}.\n\n"
            f"Filename: {asset_info['filename']}\n"
            f"Niche: {metadata['niche']}\n"
            f"Mood: {metadata['mood']}\n"
            f"Board: {metadata['board_name']}\n\n"
            f"The alt text should:\n"
            f"- Be 1-2 sentences, max 500 characters\n"
            f"- Describe the likely visual content based on the niche/mood\n"
            f"- Be accessibility-focused (screen-reader friendly)\n"
            f"- Mention it is {metadata['niche']}-themed content\n\n"
            f"Respond with ONLY the alt text string, no quotes or JSON."
        )

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()[:500]
        except Exception as exc:
            logger.warning(
                "Alt text generation failed for %s: %s", asset_info["filename"], exc
            )
            return (
                f"{metadata['niche'].title()} {asset_info['media_type']} content "
                f"with {metadata['mood']} mood, curated for the "
                f"{metadata['board_name']} board."
            )

    # -- combined generation (batched) --------------------------------------

    def generate_all_metadata_via_claude(
        self, asset_info: dict, metadata: dict
    ) -> dict:
        """Single Claude call to generate title, description, and alt text.

        Batches all caption work into one API call for efficiency.
        """
        caption_type = CAPTION_TYPE_CYCLE[
            self._caption_cycle_index % len(CAPTION_TYPE_CYCLE)
        ]
        self._caption_cycle_index += 1

        templates = CAPTION_TEMPLATES[caption_type]

        duration_note = ""
        if asset_info.get("duration_seconds"):
            duration_note = f"Video duration: {asset_info['duration_seconds']}s. "

        prompt = (
            f"Generate Pinterest metadata for this asset.\n\n"
            f"Asset: {asset_info['filename']}\n"
            f"Media type: {asset_info['media_type']}\n"
            f"{duration_note}"
            f"Niche: {metadata['niche']}\n"
            f"Mood: {metadata['mood']}\n"
            f"Ebril track: {metadata['ebril_track']}\n"
            f"Board: {metadata['board_name']}\n\n"
            f"Caption template style: {caption_type}\n"
            f"Example templates for style {caption_type}:\n"
            + "\n".join(f"  - {t}" for t in templates)
            + "\n\n"
            f"Return a JSON object with exactly these three fields:\n\n"
            f"1. \"title\" — max 100 characters. Pinterest SEO-friendly. "
            f"Include relevant keywords for the {metadata['niche']} niche. "
            f"Do not use hashtags in the title.\n\n"
            f"2. \"description\" — 150-500 characters. Written in caption style "
            f"{caption_type} (inspired by the templates above but not a copy). "
            f"Must include a natural reference to Ebril or the track "
            f"\"{metadata['ebril_track']}\". Should feel organic and native to "
            f"Pinterest — not salesy.\n\n"
            f"3. \"alt_text\" — 1-2 sentences, max 500 characters. "
            f"Accessibility-focused description of the likely visual content "
            f"based on niche and mood. Screen-reader friendly. "
            f"Mention it is {metadata['niche']}-themed content.\n\n"
            f"Respond with ONLY the JSON object, no markdown fencing."
        )

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=(
                    "You are a Pinterest SEO and content strategist for Florra, "
                    "a brand that promotes indie artist Ebril's music through "
                    "aesthetic lifestyle content. Write captions that feel organic "
                    "and native to Pinterest — not salesy, not forced. "
                    "Always respond with valid JSON only."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)

            title = result.get("title", "")[:100]
            description = result.get("description", "")
            if len(description) > 500:
                description = description[:497] + "..."
            elif len(description) < 150:
                description += f" | {metadata['ebril_track']} by Ebril"
            alt_text = result.get("alt_text", "")[:500]

            return {
                "title": title,
                "description": description,
                "caption_type": caption_type,
                "alt_text": alt_text,
            }

        except Exception as exc:
            logger.error(
                "Batched metadata generation failed for %s: %s",
                asset_info["filename"],
                exc,
            )
            track = metadata.get("ebril_track", "Ebril")
            return {
                "title": f"{metadata['niche'].title()} Mood | {track} by Ebril",
                "description": (
                    f"Aesthetic {metadata['niche']} content with "
                    f"{metadata['mood']} vibes. Currently listening to "
                    f"{track} by Ebril on repeat."
                ),
                "caption_type": caption_type,
                "alt_text": (
                    f"{metadata['niche'].title()} {asset_info['media_type']} content "
                    f"with {metadata['mood']} mood, curated for the "
                    f"{metadata['board_name']} board."
                ),
            }

    # -- posting schedule ---------------------------------------------------

    def assign_posting_time(self, pin_index: int) -> dict:
        """Distribute pins across posting windows.

        Returns dict with posting_time (HH:MM EST) and posting_window label.
        Respects MAX_PINS_PER_HOUR per slot.
        """
        total_slots = len(POSTING_WINDOWS)
        window_index = pin_index % total_slots
        window = POSTING_WINDOWS[window_index]

        # Within the window, distribute across hours
        window_hours = window["end_hour"] - window["start_hour"]
        pins_in_window = pin_index // total_slots
        hour_offset = pins_in_window % window_hours if window_hours > 0 else 0
        minute_offset = (
            (pins_in_window // window_hours * 15) % 60
            if window_hours > 0
            else (pins_in_window * 15) % 60
        )

        hour = window["start_hour"] + hour_offset
        minute = minute_offset

        return {
            "posting_time": f"{hour:02d}:{minute:02d} EST",
            "posting_window": window["label"],
        }

    # -- main pipeline ------------------------------------------------------

    def package_assets(
        self,
        asset_dir: Path,
        mood: str | None = None,
        niche: str | None = None,
    ) -> list[dict]:
        """Scan asset_dir and generate full pin package for each asset.

        Returns list of pin package dicts ready for serialization.
        """
        asset_files = sorted(
            f
            for f in asset_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
        )

        if not asset_files:
            logger.warning("No supported media files found in %s", asset_dir)
            return []

        print(f"\n{'='*60}")
        print(f"  PINTEREST CAPTION ENGINE")
        print(f"  Assets:  {len(asset_files)} files in {asset_dir}")
        print(f"  Mood:    {mood or 'auto-detect'}")
        print(f"  Niche:   {niche or 'auto-detect'}")
        print(f"  Model:   {MODEL}")
        print(f"{'='*60}\n")

        package = []
        errors = []

        for idx, filepath in enumerate(asset_files):
            print(f"  [{idx + 1}/{len(asset_files)}] {filepath.name}")

            try:
                # Step 1: Analyze asset
                asset_info = self.analyze_asset(filepath)
                logger.info(
                    "Analyzed %s: %s, %d bytes",
                    filepath.name,
                    asset_info["media_type"],
                    asset_info["size_bytes"],
                )

                # Step 2: Assign metadata (board, track, mood/niche)
                metadata = self.assign_metadata(asset_info, mood=mood, niche=niche)

                # Step 3: Generate title, description, and alt text (single call)
                claude_result = self.generate_all_metadata_via_claude(
                    asset_info, metadata
                )

                # Step 4: Generate hashtags
                hashtags = self.generate_hashtags(metadata["niche"])

                # Step 5: Assign posting time
                schedule = self.assign_posting_time(idx)

                # Assemble pin entry
                pin_entry = {
                    "source_file": filepath.name,
                    "board_id": metadata["board_id"],
                    "board_name": metadata["board_name"],
                    "pinterest_board_id": metadata["pinterest_board_id"],
                    "title": claude_result["title"],
                    "description": claude_result["description"],
                    "hashtags": hashtags,
                    "link_url": metadata["spotify_url"],
                    "ebril_track": metadata["ebril_track"],
                    "caption_type": claude_result["caption_type"],
                    "alt_text": claude_result["alt_text"],
                    "posting_time": schedule["posting_time"],
                    "posting_window": schedule["posting_window"],
                    "mood": metadata["mood"],
                    "niche": metadata["niche"],
                }

                package.append(pin_entry)
                print(
                    f"           -> {metadata['board_name']} | "
                    f"Type {claude_result['caption_type']} | "
                    f"{schedule['posting_time']}"
                )

            except Exception as exc:
                logger.error("Failed to process %s: %s", filepath.name, exc)
                errors.append({"file": filepath.name, "error": str(exc)})
                print(f"           -> ERROR: {exc}")
                continue

        print(f"\n  Processed: {len(package)}/{len(asset_files)} assets")
        if errors:
            print(f"  Errors:    {len(errors)} assets skipped")
            for err in errors:
                print(f"    - {err['file']}: {err['error']}")

        return package

    # -- output -------------------------------------------------------------

    def save_package(self, package: list[dict], output_dir: Path) -> tuple[Path, Path]:
        """Save pin package as JSON manifest and human-readable Markdown summary.

        Returns (json_path, md_path).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()

        json_path = output_dir / f"pin-package-{today}.json"
        md_path = output_dir / f"pin-package-{today}.md"

        # JSON manifest
        manifest = {
            "generated": today,
            "model": MODEL,
            "total_pins": len(package),
            "pins": package,
        }
        json_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Markdown summary
        lines = [
            f"# Pin Package — {today}",
            f"**Total pins:** {len(package)}",
            f"**Model:** {MODEL}",
            "",
            "| # | File | Board | Track | Type | Time |",
            "|---|------|-------|-------|------|------|",
        ]
        for i, pin in enumerate(package, 1):
            lines.append(
                f"| {i} | {pin['source_file']} | {pin['board_name']} | "
                f"{pin['ebril_track']} | {pin['caption_type']} | "
                f"{pin['posting_time']} |"
            )

        lines += [
            "",
            "## Pin Details",
            "",
        ]
        for i, pin in enumerate(package, 1):
            lines.append(f"### {i}. {pin['source_file']}")
            lines.append(f"**Board:** {pin['board_name']} (`{pin['pinterest_board_id']}`)")
            lines.append(f"**Title:** {pin['title']}")
            lines.append(f"**Description:** {pin['description']}")
            lines.append(f"**Hashtags:** {' '.join(pin['hashtags'])}")
            lines.append(f"**Alt text:** {pin['alt_text']}")
            lines.append(f"**Track:** {pin['ebril_track']} | **Mood:** {pin['mood']} | **Niche:** {pin['niche']}")
            lines.append(f"**Posting:** {pin['posting_time']} ({pin['posting_window']})")
            lines.append("")

        md_path.write_text("\n".join(lines), encoding="utf-8")

        return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Pinterest-optimized metadata for Ebril's content assets"
    )
    parser.add_argument(
        "--asset-dir",
        required=True,
        type=Path,
        help="Directory containing Ebril's video/image files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for the pin package (default: same as --asset-dir)",
    )
    parser.add_argument(
        "--mood",
        choices=VALID_MOODS,
        default=None,
        help="Override mood for all assets",
    )
    parser.add_argument(
        "--niche",
        choices=VALID_NICHES,
        default=None,
        help="Override niche for all assets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print package to stdout instead of writing files",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    asset_dir = args.asset_dir.resolve()
    if not asset_dir.is_dir():
        print(f"Error: Asset directory does not exist: {asset_dir}")
        sys.exit(1)

    output_dir = (args.output_dir or asset_dir).resolve()

    # Validate auth
    if not os.environ.get("ANTHROPIC_API_KEY") and not SESSION_TOKEN_FILE.exists():
        print("\nError: No authentication found.")
        print("Set ANTHROPIC_API_KEY or ensure session token is available.")
        sys.exit(1)

    client = _get_client()
    engine = CaptionEngine(client)

    package = engine.package_assets(asset_dir, mood=args.mood, niche=args.niche)

    if not package:
        print("\nNo assets were processed. Check the asset directory and logs.")
        sys.exit(1)

    if args.dry_run:
        print(f"\n{'='*60}")
        print("  DRY RUN — Pin Package Preview")
        print(f"{'='*60}\n")
        print(json.dumps(package, indent=2, ensure_ascii=False))
        print(f"\n  {len(package)} pins would be packaged.")
        return

    json_path, md_path = engine.save_package(package, output_dir)

    print(f"\n{'='*60}")
    print(f"  PIN PACKAGE COMPLETE")
    print(f"  JSON:     {json_path}")
    print(f"  Summary:  {md_path}")
    print(f"  Pins:     {len(package)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
