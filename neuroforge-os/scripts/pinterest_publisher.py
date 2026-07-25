#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Publisher
=====================================
Posts Ebril's content to Pinterest using the v5 API.
Reads pin packages from the caption engine and handles video upload,
media processing, pin creation, rate limiting, and publish logging.

Prerequisites:
    PINTEREST_ACCESS_TOKEN  — OAuth2 token with pins:read, pins:write, boards:read

Usage:
    python pinterest_publisher.py --package output/pinterest/pin-package-2026-07-25.json
    python pinterest_publisher.py --package ./package.json --dry-run
    python pinterest_publisher.py --package ./package.json --rate-limit 30
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pinterest_config import (
    PINTEREST_API_BASE,
    PINTEREST_MEDIA_POLL_SEC,
    PINTEREST_MEDIA_TIMEOUT_SEC,
    PINTEREST_RATE_BACKOFF_SEC,
    PINTEREST_RATE_LIMIT_PER_MIN,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class PinterestPublisher:
    """Publishes pin packages to Pinterest via the v5 API."""

    def __init__(self, access_token: str, dry_run: bool = False):
        self.access_token = access_token
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

        # Rate limiter state
        self._call_timestamps: list[float] = []
        self._rate_limit_per_min = PINTEREST_RATE_LIMIT_PER_MIN

    @property
    def rate_limit_per_min(self) -> int:
        return self._rate_limit_per_min

    @rate_limit_per_min.setter
    def rate_limit_per_min(self, value: int):
        self._rate_limit_per_min = max(1, value)

    # ------------------------------------------------------------------ #
    #  Rate limiting
    # ------------------------------------------------------------------ #

    def _rate_limit(self):
        """Track API calls per minute and sleep if approaching the limit."""
        now = time.time()
        window_start = now - 60.0

        # Prune timestamps older than the 60-second window
        self._call_timestamps = [
            ts for ts in self._call_timestamps if ts > window_start
        ]

        if len(self._call_timestamps) >= self._rate_limit_per_min:
            oldest_in_window = self._call_timestamps[0]
            sleep_for = 60.0 - (now - oldest_in_window) + 0.5
            if sleep_for > 0:
                print(f"  [rate-limit] Sleeping {sleep_for:.1f}s to stay under {self._rate_limit_per_min} calls/min")
                time.sleep(sleep_for)

        self._call_timestamps.append(time.time())

    # ------------------------------------------------------------------ #
    #  API request wrapper
    # ------------------------------------------------------------------ #

    def _api_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        Wrapper around requests that applies rate limiting, handles retries
        (1 retry on failure), and logs requests. Returns response JSON or raises.
        """
        url = f"{PINTEREST_API_BASE}{endpoint}"
        retries = 1

        for attempt in range(retries + 1):
            self._rate_limit()

            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"  [{ts}] {method.upper()} {endpoint}", end="", flush=True)

            try:
                resp = self.session.request(method, url, timeout=60, **kwargs)
            except requests.RequestException as exc:
                print(f" ... request error: {exc}")
                if attempt < retries:
                    print(f"  Retrying ({attempt + 1}/{retries})...")
                    time.sleep(2)
                    continue
                raise

            if resp.status_code == 429:
                print(f" ... 429 rate-limited, backing off {PINTEREST_RATE_BACKOFF_SEC}s")
                time.sleep(PINTEREST_RATE_BACKOFF_SEC)
                if attempt < retries:
                    continue
                resp.raise_for_status()

            if resp.status_code >= 400:
                print(f" ... {resp.status_code} error")
                if attempt < retries:
                    print(f"  Retrying ({attempt + 1}/{retries})...")
                    time.sleep(2)
                    continue
                resp.raise_for_status()

            print(f" ... {resp.status_code} OK")
            return resp.json()

        # Should not reach here, but just in case
        raise RuntimeError(f"API request failed after {retries + 1} attempts: {method} {endpoint}")

    # ------------------------------------------------------------------ #
    #  Media upload (videos)
    # ------------------------------------------------------------------ #

    def upload_media(self, filepath: Path) -> str | None:
        """
        Upload media to Pinterest.

        For video files: POST to /media to create an upload slot, then PUT the
        video file to the returned upload URL. Returns media_id.

        For image files: skip media upload (images use image_url or image_base64
        source type directly in pin creation). Returns None.
        """
        suffix = filepath.suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            # Images don't use the media upload flow
            return None

        if suffix not in VIDEO_EXTENSIONS:
            print(f"  [warn] Unrecognized file extension '{suffix}', treating as video")

        print(f"  Registering media upload for {filepath.name}...")

        # Step 1: Create upload slot
        register_data = self._api_request("POST", "/media", json={
            "media_type": "video",
        })

        media_id = register_data.get("media_id")
        upload_url = register_data.get("upload_url")

        if not media_id or not upload_url:
            raise RuntimeError(
                f"Media registration failed — missing media_id or upload_url: {register_data}"
            )

        # Step 2: PUT the video file to the upload URL
        print(f"  Uploading {filepath.name} ({filepath.stat().st_size // 1024} KB)...")
        with open(filepath, "rb") as f:
            put_resp = requests.put(
                upload_url,
                data=f,
                headers={"Content-Type": "application/octet-stream"},
                timeout=300,
            )
            put_resp.raise_for_status()

        print(f"  Upload complete. media_id={media_id}")
        return media_id

    # ------------------------------------------------------------------ #
    #  Media processing poll
    # ------------------------------------------------------------------ #

    def poll_media_status(self, media_id: str) -> bool:
        """
        Poll GET /media/{media_id} every PINTEREST_MEDIA_POLL_SEC until status
        is 'succeeded' or timeout after PINTEREST_MEDIA_TIMEOUT_SEC.
        Returns True on success, False on failure/timeout.
        """
        print(f"  Waiting for media {media_id} to process", end="", flush=True)
        deadline = time.time() + PINTEREST_MEDIA_TIMEOUT_SEC
        poll_count = 0

        while time.time() < deadline:
            time.sleep(PINTEREST_MEDIA_POLL_SEC)
            poll_count += 1

            try:
                data = self._api_request("GET", f"/media/{media_id}")
            except Exception as exc:
                print(f"\n  [error] Poll failed: {exc}")
                return False

            status = data.get("status", "").lower()

            if status == "succeeded":
                print(f" succeeded ({poll_count * PINTEREST_MEDIA_POLL_SEC}s)")
                return True
            elif status in ("failed", "error"):
                failure_reason = data.get("failure_reason", "unknown")
                print(f" FAILED: {failure_reason}")
                return False
            else:
                print(".", end="", flush=True)

        print(f" TIMEOUT after {PINTEREST_MEDIA_TIMEOUT_SEC}s")
        return False

    # ------------------------------------------------------------------ #
    #  Pin creation
    # ------------------------------------------------------------------ #

    def create_pin(self, pin_data: dict, media_id: str | None = None) -> tuple[str | None, str | None]:
        """
        POST to /pins with title, description, board_id, media_source, link, alt_text.
        Returns (pin_id, pin_url) or (None, None) on failure.
        """
        payload: dict = {
            "board_id": pin_data.get("board_id", ""),
            "title": pin_data.get("title", ""),
            "description": pin_data.get("description", ""),
        }

        if pin_data.get("link"):
            payload["link"] = pin_data["link"]

        if pin_data.get("alt_text"):
            payload["alt_text"] = pin_data["alt_text"]

        # Determine media source type
        if media_id:
            # Video pin — reference the uploaded media
            payload["media_source"] = {
                "source_type": "video_id",
                "media_id": media_id,
            }
        elif pin_data.get("image_url"):
            # Image pin via URL
            payload["media_source"] = {
                "source_type": "image_url",
                "url": pin_data["image_url"],
            }
        elif pin_data.get("image_base64"):
            # Image pin via base64
            payload["media_source"] = {
                "source_type": "image_base64",
                "data": pin_data["image_base64"],
                "content_type": pin_data.get("content_type", "image/jpeg"),
            }
        elif pin_data.get("source_file"):
            # Local image file — encode as base64
            source_path = Path(pin_data["source_file"])
            if source_path.exists() and source_path.suffix.lower() in IMAGE_EXTENSIONS:
                content_type_map = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                }
                content_type = content_type_map.get(source_path.suffix.lower(), "image/jpeg")
                encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
                payload["media_source"] = {
                    "source_type": "image_base64",
                    "data": encoded,
                    "content_type": content_type,
                }

        data = self._api_request("POST", "/pins", json=payload)
        pin_id = data.get("id")
        # Pinterest v5 returns the pin URL directly or we can construct it
        pin_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None

        return pin_id, pin_url

    # ------------------------------------------------------------------ #
    #  Pin verification
    # ------------------------------------------------------------------ #

    def verify_pin(self, pin_id: str) -> bool:
        """GET /pins/{pin_id} to confirm it exists after creation."""
        try:
            data = self._api_request("GET", f"/pins/{pin_id}")
            return data.get("id") == pin_id
        except Exception as exc:
            print(f"  [warn] Pin verification failed for {pin_id}: {exc}")
            return False

    # ------------------------------------------------------------------ #
    #  Package publisher (main workflow)
    # ------------------------------------------------------------------ #

    def publish_package(self, package_path: Path, asset_dir: Path | None = None,
                        scheduled: bool = False) -> list[dict]:
        """
        Main method. Loads the pin-package JSON, iterates through pins:
          1. Determine asset path (from source_file field, looking in asset_dir)
          2. Upload media if video
          3. Wait for processing
          4. Create pin
          5. Verify pin
          6. Log result (success/failure)

        If --scheduled flag is set, respects posting times from the package.
        Returns a list of publish log entries.
        """
        package = json.loads(package_path.read_text(encoding="utf-8"))
        pins = package.get("pins", [])

        if not pins:
            print("  No pins found in package.")
            return []

        if asset_dir is None:
            asset_dir = package_path.parent

        results: list[dict] = []
        total = len(pins)

        print(f"\n  Processing {total} pin(s) from {package_path.name}")
        print(f"  Asset directory: {asset_dir}")
        print(f"  Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        if scheduled:
            print(f"  Scheduled posting: enabled")
        print()

        # ---- Dry run: print formatted table ---- #
        if self.dry_run:
            self._print_dry_run_table(pins, asset_dir)
            return []

        # ---- Live run ---- #
        for idx, pin in enumerate(pins, start=1):
            source_file = pin.get("source_file", "")
            board_name = pin.get("board", pin.get("board_id", "unknown"))
            title_preview = (pin.get("title", "") or "")[:50]
            asset_path = self._resolve_asset_path(source_file, asset_dir)

            entry: dict = {
                "source_file": source_file,
                "board": board_name,
                "pinterest_pin_id": None,
                "pinterest_url": None,
                "status": "failed",
                "posted_at": None,
                "error": None,
                "media_id": None,
                "upload_duration_sec": None,
                "processing_duration_sec": None,
            }

            print(f"  [{idx}/{total}] Posting {source_file} to {board_name}...", end=" ", flush=True)

            # Respect scheduled posting time
            if scheduled and pin.get("scheduled_time"):
                self._wait_until_scheduled(pin["scheduled_time"])

            try:
                media_id = None
                suffix = Path(source_file).suffix.lower() if source_file else ""

                # Step 1 & 2: Upload media if video
                if suffix in VIDEO_EXTENSIONS:
                    if not asset_path or not asset_path.exists():
                        raise FileNotFoundError(f"Video asset not found: {source_file} (looked in {asset_dir})")

                    upload_start = time.time()
                    media_id = self.upload_media(asset_path)
                    entry["upload_duration_sec"] = round(time.time() - upload_start, 1)
                    entry["media_id"] = media_id

                    # Step 3: Wait for processing
                    if media_id:
                        process_start = time.time()
                        success = self.poll_media_status(media_id)
                        entry["processing_duration_sec"] = round(time.time() - process_start, 1)
                        if not success:
                            raise RuntimeError(f"Media processing failed for {media_id}")

                elif suffix in IMAGE_EXTENSIONS:
                    # For images, set the source_file path for base64 encoding in create_pin
                    if asset_path and asset_path.exists():
                        pin["source_file"] = str(asset_path)

                # Step 4: Create pin
                pin_id, pin_url = self.create_pin(pin, media_id=media_id)

                if not pin_id:
                    raise RuntimeError("Pin creation returned no pin ID")

                # Step 5: Verify pin
                verified = self.verify_pin(pin_id)
                if not verified:
                    print(f"[warn] Pin {pin_id} created but verification failed")

                # Step 6: Log success
                entry["pinterest_pin_id"] = pin_id
                entry["pinterest_url"] = pin_url
                entry["status"] = "posted"
                entry["posted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"done (pin_id: {pin_id})")

            except FileNotFoundError as exc:
                entry["status"] = "skipped"
                entry["error"] = str(exc)
                print(f"skipped ({exc})")

            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = str(exc)
                print(f"FAILED ({exc})")

            results.append(entry)

        return results

    # ------------------------------------------------------------------ #
    #  Dry-run table
    # ------------------------------------------------------------------ #

    def _print_dry_run_table(self, pins: list[dict], asset_dir: Path):
        """Print a formatted table showing what would be posted."""
        print(f"  {'='*80}")
        print(f"  DRY RUN — the following pins would be posted:")
        print(f"  {'='*80}")
        print(f"  {'#':<4} {'File':<35} {'Board':<20} {'Title':<25} {'Scheduled':<20}")
        print(f"  {'-'*4} {'-'*35} {'-'*20} {'-'*25} {'-'*20}")

        for idx, pin in enumerate(pins, start=1):
            source = pin.get("source_file", "n/a")
            board = pin.get("board", pin.get("board_id", "n/a"))
            title = (pin.get("title", "") or "")[:24]
            sched = pin.get("scheduled_time", "immediate")

            # Truncate long values
            if len(source) > 34:
                source = "..." + source[-31:]
            if len(board) > 19:
                board = board[:16] + "..."

            print(f"  {idx:<4} {source:<35} {board:<20} {title:<25} {sched:<20}")

        print(f"  {'='*80}")
        print(f"  Total: {len(pins)} pin(s) would be posted.")
        print()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _resolve_asset_path(self, source_file: str, asset_dir: Path) -> Path | None:
        """Resolve the asset path from source_file, looking in asset_dir."""
        if not source_file:
            return None

        # If source_file is already absolute and exists, use it
        p = Path(source_file)
        if p.is_absolute() and p.exists():
            return p

        # Look in asset_dir
        candidate = asset_dir / Path(source_file).name
        if candidate.exists():
            return candidate

        # Try the full relative path under asset_dir
        candidate = asset_dir / source_file
        if candidate.exists():
            return candidate

        return None

    def _wait_until_scheduled(self, scheduled_time: str):
        """Wait until the scheduled posting time."""
        try:
            target = datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            print(f"  [warn] Invalid scheduled_time '{scheduled_time}', posting immediately")
            return

        now = datetime.now(timezone.utc)
        if target > now:
            wait_sec = (target - now).total_seconds()
            print(f"\n  [scheduled] Waiting {wait_sec:.0f}s until {scheduled_time}...", end=" ", flush=True)
            time.sleep(wait_sec)
            print("ready.")

    # ------------------------------------------------------------------ #
    #  Publish log
    # ------------------------------------------------------------------ #

    def save_publish_log(self, results: list[dict], output_dir: Path):
        """
        Save publish-log-{DATE}.json and publish-log-{DATE}.md with
        summary stats and per-pin status.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # --- JSON log --- #
        json_path = output_dir / f"publish-log-{date_str}.json"
        json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Log saved: {json_path}")

        # --- Summary stats --- #
        total = len(results)
        posted = sum(1 for r in results if r["status"] == "posted")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        # --- Markdown log --- #
        md_lines = [
            f"# Pinterest Publish Log — {date_str}",
            "",
            "## Summary",
            "",
            f"| Metric    | Count |",
            f"|-----------|-------|",
            f"| Total     | {total}   |",
            f"| Posted    | {posted}   |",
            f"| Failed    | {failed}   |",
            f"| Skipped   | {skipped}   |",
            "",
        ]

        # Timing summary for posted pins
        upload_times = [r["upload_duration_sec"] for r in results if r.get("upload_duration_sec") is not None]
        process_times = [r["processing_duration_sec"] for r in results if r.get("processing_duration_sec") is not None]

        if upload_times:
            avg_upload = sum(upload_times) / len(upload_times)
            md_lines.append(f"**Avg upload time:** {avg_upload:.1f}s  ")
        if process_times:
            avg_process = sum(process_times) / len(process_times)
            md_lines.append(f"**Avg processing time:** {avg_process:.1f}s  ")

        md_lines += [
            "",
            "## Per-Pin Details",
            "",
            "| # | File | Board | Status | Pin ID | Error |",
            "|---|------|-------|--------|--------|-------|",
        ]

        for idx, r in enumerate(results, start=1):
            source = r.get("source_file", "n/a")
            board = r.get("board", "n/a")
            status = r.get("status", "n/a")
            pin_id = r.get("pinterest_pin_id") or "-"
            error = r.get("error") or "-"

            # Truncate long error messages in table
            if len(error) > 50:
                error = error[:47] + "..."

            md_lines.append(f"| {idx} | {source} | {board} | {status} | {pin_id} | {error} |")

        # Detailed entries for failures
        failures = [r for r in results if r["status"] in ("failed", "skipped")]
        if failures:
            md_lines += [
                "",
                "## Errors",
                "",
            ]
            for r in failures:
                md_lines.append(f"- **{r['source_file']}** ({r['status']}): {r.get('error', 'unknown')}")

        md_lines += [
            "",
            f"---",
            f"*Generated by NeuroForge OS Pinterest Publisher at "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}*",
        ]

        md_path = output_dir / f"publish-log-{date_str}.md"
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"  Log saved: {md_path}")

        # Print summary to console
        print(f"\n  {'='*50}")
        print(f"  PUBLISH SUMMARY")
        print(f"  Posted:  {posted}/{total}")
        print(f"  Failed:  {failed}/{total}")
        print(f"  Skipped: {skipped}/{total}")
        print(f"  {'='*50}")


# ====================================================================== #
#  CLI entry point
# ====================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description="NeuroForge OS — Pinterest Publisher: post pin packages to Pinterest v5 API"
    )
    parser.add_argument(
        "--package", required=True,
        help="Path to pin-package JSON file produced by the caption engine",
    )
    parser.add_argument(
        "--asset-dir", default=None,
        help="Directory containing media assets (default: same directory as package file)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for publish logs (default: same directory as package file)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be posted without calling the Pinterest API",
    )
    parser.add_argument(
        "--rate-limit", type=int, default=PINTEREST_RATE_LIMIT_PER_MIN,
        help=f"Max API calls per minute (default: {PINTEREST_RATE_LIMIT_PER_MIN})",
    )
    parser.add_argument(
        "--scheduled", action="store_true",
        help="Respect posting times from the pin package (waits until scheduled time)",
    )
    args = parser.parse_args()

    # Resolve paths
    package_path = Path(args.package).resolve()
    if not package_path.exists():
        print(f"Error: Package file not found: {package_path}")
        sys.exit(1)

    asset_dir = Path(args.asset_dir).resolve() if args.asset_dir else package_path.parent
    output_dir = Path(args.output_dir).resolve() if args.output_dir else package_path.parent

    # Check for access token
    access_token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    if not access_token and not args.dry_run:
        print("Error: PINTEREST_ACCESS_TOKEN environment variable is not set.")
        print()
        print("To get a token:")
        print("  1. Go to https://developers.pinterest.com/apps/")
        print("  2. Create or select your app")
        print("  3. Generate an OAuth2 access token with scopes:")
        print("     pins:read, pins:write, boards:read")
        print("  4. Export it:")
        print('     export PINTEREST_ACCESS_TOKEN="your_token_here"')
        print()
        print("Or run with --dry-run to preview without posting.")
        sys.exit(1)

    # Banner
    print(f"\n{'='*60}")
    print(f"  PINTEREST PUBLISHER")
    print(f"  Package:    {package_path.name}")
    print(f"  Asset dir:  {asset_dir}")
    print(f"  Output dir: {output_dir}")
    print(f"  Rate limit: {args.rate_limit} calls/min")
    print(f"  Mode:       {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Scheduled:  {'yes' if args.scheduled else 'no'}")
    print(f"{'='*60}")

    # Initialize publisher
    publisher = PinterestPublisher(
        access_token=access_token or "dry-run-token",
        dry_run=args.dry_run,
    )
    publisher.rate_limit_per_min = args.rate_limit

    # Publish
    start_time = time.time()
    results = publisher.publish_package(
        package_path=package_path,
        asset_dir=asset_dir,
        scheduled=args.scheduled,
    )
    elapsed = time.time() - start_time

    # Save logs (only for live runs with results)
    if results:
        publisher.save_publish_log(results, output_dir)

    if args.dry_run:
        print(f"\n  Dry run complete.")
    else:
        print(f"\n  Total time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
