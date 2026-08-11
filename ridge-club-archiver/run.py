#!/usr/bin/env python3
"""
Ridge Club YouTube Archiver — CLI entrypoint

    python run.py backfill              # archive the entire channel history
    python run.py watch                 # poll for new uploads forever
    python run.py watch --once          # single pass (for cron)
    python run.py process --url <url>   # archive one specific video
    python run.py retry                 # re-queue failed videos
    python run.py status                # show pipeline state
"""

import argparse
import re
import sys

from agents.config import Config
from agents.orchestrator import Orchestrator


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if not match:
        sys.exit(f"Could not find a YouTube video id in: {url}")
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description="Ridge Club YouTube → Drive → Opus archiver")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("backfill", help="Archive every video on the channel")
    watch = sub.add_parser("watch", help="Poll for new uploads and process them")
    watch.add_argument("--once", action="store_true", help="Run a single pass (cron mode)")
    process = sub.add_parser("process", help="Archive a single video")
    process.add_argument("--url", required=True, help="YouTube video URL")
    sub.add_parser("retry", help="Re-queue failed videos and process them")
    sub.add_parser("status", help="Show pipeline status")

    args = parser.parse_args()

    config = Config()
    if args.command != "status":
        problems = config.validate()
        if problems:
            print("Configuration problems:")
            for p in problems:
                print(f"  - {p}")
            sys.exit("Fix .env (see .env.example) and re-run.")

    orch = Orchestrator(config)

    if args.command == "backfill":
        orch.backfill()
    elif args.command == "watch":
        if args.once:
            orch.watch_once()
        else:
            orch.watch_forever()
    elif args.command == "process":
        video_id = extract_video_id(args.url)
        url = f"https://www.youtube.com/watch?v={video_id}"
        orch.state.add_video(video_id, video_id, url)
        orch.process_video(orch.state.get(video_id))
    elif args.command == "retry":
        orch.state.retry_failed()
        orch.process_pending()
    elif args.command == "status":
        orch.print_status()


if __name__ == "__main__":
    main()
