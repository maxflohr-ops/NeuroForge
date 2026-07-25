#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Cross-Platform Reposter
===================================================
Downloads Ebril's OWN TikTok videos and prepares them for Pinterest posting.
This handles same-creator cross-platform distribution only — it will only
process URLs from Ebril's verified TikTok account.

The downloaded assets feed into the caption engine and publisher modules.

Prerequisites:
    EBRIL_TIKTOK_USERNAME   — Ebril's TikTok handle (for ownership verification)
    COBALT_API_URL          — Cobalt API endpoint (default: https://api.cobalt.tools/)

Usage:
    # From a URLs file (one TikTok URL per line)
    python pinterest_cross_reposter.py --urls-file ebril_tiktoks.txt --output-dir output/pinterest/assets

    # Single URL
    python pinterest_cross_reposter.py --url "https://www.tiktok.com/@ebril/video/123" --output-dir output/pinterest/assets

    # Dry run — just validate URLs without downloading
    python pinterest_cross_reposter.py --urls-file ebril_tiktoks.txt --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

# ---------------------------------------------------------------------------
# Imports from the Pinterest pipeline config
# ---------------------------------------------------------------------------
sys.path.insert(0, str(SCRIPT_DIR))
from pinterest_config import VALID_NICHES, VALID_MOODS  # noqa: E402

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_COBALT_URL = "https://api.cobalt.tools/"
DEFAULT_OUTPUT_SUBDIR = "output/pinterest/assets"
TIKTOK_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?tiktok\.com/@(?P<username>[A-Za-z0-9_.]+)/video/(?P<video_id>\d+)"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pinterest_cross_reposter")


# ===========================================================================
# CrossPlatformReposter
# ===========================================================================
class CrossPlatformReposter:
    """Downloads Ebril's own TikTok videos via Cobalt and prepares them for
    the Pinterest caption-engine / publisher pipeline.

    Ownership verification is enforced: every URL must belong to
    ``self.ebril_username``.  URLs from other creators are rejected.
    """

    def __init__(
        self,
        ebril_username: str | None = None,
        cobalt_url: str | None = None,
        output_dir: str | Path | None = None,
    ):
        self.ebril_username = (
            ebril_username
            or os.environ.get("EBRIL_TIKTOK_USERNAME")
            or "ebril"
        )
        self.cobalt_url = (
            cobalt_url
            or os.environ.get("COBALT_API_URL")
            or DEFAULT_COBALT_URL
        )
        # Ensure the cobalt URL ends with a slash for consistent joining
        if not self.cobalt_url.endswith("/"):
            self.cobalt_url += "/"
        self.output_dir = Path(output_dir) if output_dir else PROJECT_DIR / DEFAULT_OUTPUT_SUBDIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("CrossPlatformReposter initialized")
        logger.info("  Ebril username : @%s", self.ebril_username)
        logger.info("  Cobalt API     : %s", self.cobalt_url)
        logger.info("  Output dir     : %s", self.output_dir)

    # ------------------------------------------------------------------
    # URL validation
    # ------------------------------------------------------------------
    def validate_url(self, url: str) -> tuple[bool, str]:
        """Check that *url* is a valid TikTok video URL belonging to Ebril.

        Returns ``(is_valid, reason)`` where *reason* explains any rejection.
        """
        url = url.strip()
        if not url:
            return False, "Empty URL"

        match = TIKTOK_URL_PATTERN.match(url)
        if not match:
            return False, (
                f"Not a valid TikTok video URL. "
                f"Expected format: https://www.tiktok.com/@{self.ebril_username}/video/<id>"
            )

        username = match.group("username")
        if username.lower() != self.ebril_username.lower():
            return False, (
                f"Skipping {url}: belongs to @{username}, not @{self.ebril_username}. "
                f"This tool only processes Ebril's own content."
            )

        return True, "Valid"

    # ------------------------------------------------------------------
    # Cobalt download
    # ------------------------------------------------------------------
    def download_via_cobalt(self, url: str, output_path: Path) -> dict:
        """Download a TikTok video through the Cobalt API.

        Posts a download request, handles the response type (``redirect``,
        ``tunnel``, ``stream``, etc.), and writes the video to *output_path*.

        On a 403 response the method waits 60 s and retries once.

        Returns a dict with ``status``, ``file_path``, ``file_size``, and
        ``error`` (if any).
        """
        payload = {
            "url": url,
            "videoQuality": "1080",
            "filenameStyle": "basic",
            "tiktokFullAudio": True,
            "tiktokH265": False,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        api_endpoint = self.cobalt_url.rstrip("/")

        result: dict = {
            "status": "pending",
            "file_path": str(output_path),
            "file_size": 0,
            "error": None,
        }

        for attempt in range(2):  # at most one retry
            try:
                logger.info("  Cobalt request (attempt %d): %s", attempt + 1, url)
                resp = requests.post(
                    api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if resp.status_code == 403 and attempt == 0:
                    logger.warning("  Received 403 — waiting 60 s before retry...")
                    time.sleep(60)
                    continue

                resp.raise_for_status()
                data = resp.json()

            except requests.RequestException as exc:
                result["status"] = "error"
                result["error"] = str(exc)
                logger.error("  Cobalt API error: %s", exc)
                return result

            # Handle Cobalt response types
            response_status = data.get("status")
            download_url: str | None = None

            if response_status == "redirect":
                download_url = data.get("url")
            elif response_status in ("tunnel", "stream"):
                download_url = data.get("url")
            elif response_status == "error":
                result["status"] = "error"
                result["error"] = data.get("text", "Unknown Cobalt error")
                logger.error("  Cobalt returned error: %s", result["error"])
                return result
            else:
                # Fallback: try to find a URL in the response
                download_url = data.get("url")
                if not download_url:
                    result["status"] = "error"
                    result["error"] = f"Unexpected Cobalt response status: {response_status}"
                    logger.error("  %s", result["error"])
                    return result

            if not download_url:
                result["status"] = "error"
                result["error"] = "No download URL in Cobalt response"
                logger.error("  %s", result["error"])
                return result

            # Download the actual video file
            try:
                logger.info("  Downloading video to %s ...", output_path.name)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                dl_resp = requests.get(download_url, timeout=120, stream=True)
                dl_resp.raise_for_status()
                with open(output_path, "wb") as fh:
                    for chunk in dl_resp.iter_content(chunk_size=65536):
                        fh.write(chunk)
                file_size = output_path.stat().st_size
                result["status"] = "downloaded"
                result["file_size"] = file_size
                logger.info(
                    "  Saved: %s (%d KB)", output_path.name, file_size // 1024
                )
                return result
            except requests.RequestException as exc:
                result["status"] = "error"
                result["error"] = f"Download failed: {exc}"
                logger.error("  %s", result["error"])
                return result

        # Exhausted retries
        if result["status"] == "pending":
            result["status"] = "error"
            result["error"] = "Exhausted retries after 403"
        return result

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------
    def extract_metadata_from_url(self, url: str) -> dict:
        """Parse *url* and return basic metadata.

        The returned dict includes ``video_id``, ``username``, and the
        original ``source_url``.
        """
        match = TIKTOK_URL_PATTERN.match(url.strip())
        if not match:
            return {"video_id": None, "username": None, "source_url": url}
        return {
            "video_id": match.group("video_id"),
            "username": match.group("username"),
            "source_url": url.strip(),
        }

    # ------------------------------------------------------------------
    # Batch download
    # ------------------------------------------------------------------
    def download_batch(self, urls: list[str]) -> list[dict]:
        """Process a list of TikTok URLs.

        1. Validates each URL (skips non-Ebril URLs with a warning).
        2. Downloads valid URLs via Cobalt.
        3. Names output files ``ebril-repost-{N}.mp4`` (sequential).

        Returns a download manifest — a list of dicts, each with:
        ``source_url``, ``local_file``, ``status``, ``file_size``, ``error``,
        ``video_id``.
        """
        manifest: list[dict] = []
        download_seq = 1

        for url in urls:
            url = url.strip()
            if not url:
                continue

            is_valid, reason = self.validate_url(url)
            metadata = self.extract_metadata_from_url(url)

            entry: dict = {
                "source_url": url,
                "local_file": None,
                "status": "pending",
                "file_size": 0,
                "error": None,
                "video_id": metadata.get("video_id"),
            }

            if not is_valid:
                entry["status"] = "skipped"
                entry["error"] = reason
                logger.warning("  SKIP: %s", reason)
                manifest.append(entry)
                continue

            # Build output filename
            output_path = self.output_dir / f"ebril-repost-{download_seq}.mp4"
            dl_result = self.download_via_cobalt(url, output_path)

            entry["status"] = dl_result["status"]
            entry["file_size"] = dl_result["file_size"]
            entry["error"] = dl_result.get("error")

            if dl_result["status"] == "downloaded":
                entry["local_file"] = str(output_path)
                download_seq += 1

            manifest.append(entry)

        return manifest

    # ------------------------------------------------------------------
    # Manifest persistence
    # ------------------------------------------------------------------
    def save_manifest(self, manifest: list[dict], output_dir: str | Path | None = None) -> tuple[Path, Path]:
        """Save the download manifest as both JSON and Markdown.

        Files are named ``download-manifest-{DATE}.json`` and
        ``download-manifest-{DATE}.md``.

        Returns ``(json_path, md_path)``.
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        date_stamp = datetime.now().strftime("%Y-%m-%d")

        # --- JSON ---
        json_path = target_dir / f"download-manifest-{date_stamp}.json"
        json_path.write_text(
            json.dumps(manifest, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Manifest (JSON): %s", json_path)

        # --- Markdown ---
        total = len(manifest)
        downloaded = sum(1 for e in manifest if e["status"] == "downloaded")
        skipped = sum(1 for e in manifest if e["status"] == "skipped")
        failed = total - downloaded - skipped

        lines: list[str] = [
            f"# Download Manifest — {date_stamp}",
            "",
            "## Summary",
            "",
            f"| Metric       | Count |",
            f"|--------------|-------|",
            f"| Total        | {total} |",
            f"| Downloaded   | {downloaded} |",
            f"| Skipped      | {skipped} |",
            f"| Failed       | {failed} |",
            "",
            "## Per-Video Details",
            "",
            "| # | Source URL | Local File | Status | Size (KB) | Error |",
            "|---|-----------|------------|--------|-----------|-------|",
        ]

        for idx, entry in enumerate(manifest, start=1):
            local_file = Path(entry["local_file"]).name if entry["local_file"] else "—"
            size_kb = entry["file_size"] // 1024 if entry["file_size"] else "—"
            error = entry.get("error") or "—"
            source = entry["source_url"]
            status = entry["status"]
            lines.append(
                f"| {idx} | `{source}` | `{local_file}` | {status} | {size_kb} | {error} |"
            )

        # --- Next steps ---
        downloaded_files = [
            e["local_file"] for e in manifest if e["status"] == "downloaded" and e["local_file"]
        ]
        assets_dir = str(target_dir)

        lines += [
            "",
            "## Next Steps",
            "",
            "Run the caption engine on the downloaded assets:",
            "",
            "```bash",
            f"python pinterest_caption_engine.py \\",
            f"    --assets-dir {assets_dir} \\",
            f"    --manifest {json_path.name}",
            "```",
            "",
            "Then publish to Pinterest:",
            "",
            "```bash",
            f"python pinterest_publisher.py \\",
            f"    --captions-file {assets_dir}/captions-{date_stamp}.json \\",
            f"    --assets-dir {assets_dir}",
            "```",
        ]

        if downloaded_files:
            lines += [
                "",
                f"**{downloaded} asset(s) ready for captioning.**",
            ]

        md_path = target_dir / f"download-manifest-{date_stamp}.md"
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Manifest (Markdown): %s", md_path)

        return json_path, md_path

    # ------------------------------------------------------------------
    # Pipeline command helper
    # ------------------------------------------------------------------
    def generate_pipeline_command(self, manifest: list[dict]) -> None:
        """Print the next command to run in the pipeline (the caption engine).

        This lets the user chain the pipeline steps by copy-pasting the output.
        """
        downloaded = [
            e for e in manifest if e["status"] == "downloaded" and e["local_file"]
        ]
        if not downloaded:
            logger.warning("No downloaded assets — nothing to pass to the caption engine.")
            return

        date_stamp = datetime.now().strftime("%Y-%m-%d")
        assets_dir = str(self.output_dir)

        print(f"\n{'='*60}")
        print("  NEXT STEP — Run the caption engine:")
        print(f"{'='*60}")
        print()
        print(f"  python pinterest_caption_engine.py \\")
        print(f"      --assets-dir {assets_dir} \\")
        print(f"      --manifest download-manifest-{date_stamp}.json")
        print()
        print(f"  Then publish:")
        print()
        print(f"  python pinterest_publisher.py \\")
        print(f"      --captions-file {assets_dir}/captions-{date_stamp}.json \\")
        print(f"      --assets-dir {assets_dir}")
        print()
        print(f"  Assets ready: {len(downloaded)}")
        print(f"{'='*60}\n")


# ===========================================================================
# CLI entrypoint
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(
        description=(
            "NeuroForge OS — Pinterest Cross-Platform Reposter. "
            "Downloads Ebril's own TikTok videos and prepares them for Pinterest posting."
        ),
    )
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument(
        "--url",
        type=str,
        help="Single TikTok URL to download",
    )
    url_group.add_argument(
        "--urls-file",
        type=str,
        help="Path to text file with one TikTok URL per line (lines starting with # are comments)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_SUBDIR,
        help=f"Directory to save downloaded assets (default: {DEFAULT_OUTPUT_SUBDIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate URLs and print what would be downloaded without actually downloading",
    )
    parser.add_argument(
        "--mood",
        type=str,
        choices=VALID_MOODS,
        default=None,
        help="Tag all downloads with this mood",
    )
    parser.add_argument(
        "--niche",
        type=str,
        choices=VALID_NICHES,
        default=None,
        help="Tag all downloads with this niche",
    )

    args = parser.parse_args()

    # Resolve output dir relative to project root
    if not os.path.isabs(args.output_dir):
        output_dir = PROJECT_DIR / args.output_dir
    else:
        output_dir = Path(args.output_dir)

    # Build URL list
    urls: list[str] = []
    if args.url:
        urls = [args.url]
    elif args.urls_file:
        urls_path = Path(args.urls_file)
        if not urls_path.exists():
            logger.error("URLs file not found: %s", urls_path)
            sys.exit(1)
        with open(urls_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    if not urls:
        logger.error("No URLs provided. Use --url or --urls-file.")
        sys.exit(1)

    # Initialize reposter
    reposter = CrossPlatformReposter(output_dir=output_dir)

    # Header
    print(f"\n{'='*60}")
    print("  PINTEREST CROSS-PLATFORM REPOSTER")
    print(f"  Owner account : @{reposter.ebril_username}")
    print(f"  URLs to process: {len(urls)}")
    print(f"  Output dir    : {output_dir}")
    print(f"  Mode          : {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.mood:
        print(f"  Mood tag      : {args.mood}")
    if args.niche:
        print(f"  Niche tag     : {args.niche}")
    print(f"{'='*60}\n")

    # --- Dry run: validate only ---
    if args.dry_run:
        valid_count = 0
        skip_count = 0
        for idx, url in enumerate(urls, start=1):
            is_valid, reason = reposter.validate_url(url)
            metadata = reposter.extract_metadata_from_url(url)
            status_label = "OK" if is_valid else "SKIP"
            icon = "[OK]  " if is_valid else "[SKIP]"
            video_id = metadata.get("video_id", "?")
            print(f"  {icon} {idx:>3}. {url}")
            if not is_valid:
                print(f"         Reason: {reason}")
                skip_count += 1
            else:
                print(f"         Video ID: {video_id}")
                valid_count += 1

        print(f"\n{'='*60}")
        print(f"  DRY RUN COMPLETE")
        print(f"  Valid   : {valid_count}")
        print(f"  Skipped : {skip_count}")
        print(f"  Total   : {len(urls)}")
        print(f"{'='*60}\n")
        return

    # --- Live run: download ---
    manifest = reposter.download_batch(urls)

    # Attach mood / niche tags if provided
    if args.mood or args.niche:
        for entry in manifest:
            if args.mood:
                entry["mood"] = args.mood
            if args.niche:
                entry["niche"] = args.niche

    # Save manifest
    json_path, md_path = reposter.save_manifest(manifest, output_dir)

    # Summary
    downloaded = sum(1 for e in manifest if e["status"] == "downloaded")
    skipped = sum(1 for e in manifest if e["status"] == "skipped")
    failed = len(manifest) - downloaded - skipped

    print(f"\n{'='*60}")
    print("  DOWNLOAD COMPLETE")
    print(f"  Downloaded : {downloaded}")
    print(f"  Skipped    : {skipped}")
    print(f"  Failed     : {failed}")
    print(f"  Manifest   : {json_path.name}")
    print(f"  Report     : {md_path.name}")
    print(f"{'='*60}")

    # Print next pipeline command
    reposter.generate_pipeline_command(manifest)


if __name__ == "__main__":
    main()
