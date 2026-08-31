#!/usr/bin/env python3
"""
Florra OS — Dashboard
=====================
The "observe" layer. Reads neuroforge_db.json (pipeline run log), the clip
engine manifest, and any local Notion todos, then prints a readable report:
what's been generated, QA trends, clip pipeline state, and the launch desk.

Usage:
    python florra_dashboard.py            # full report
    python florra_dashboard.py --topics   # topic summary only
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DB_FILE = SCRIPT_DIR / "neuroforge-os" / "neuroforge_db.json"
CLIP_MANIFEST = SCRIPT_DIR / "clip-engine" / "manifest.json"
TODO_FILE = SCRIPT_DIR / "florra_todos.json"


def load_db() -> list:
    if not DB_FILE.exists():
        return []
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def load_manifest() -> list:
    if not CLIP_MANIFEST.exists():
        return []
    try:
        return json.loads(CLIP_MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def load_todos() -> list:
    if not TODO_FILE.exists():
        return []
    try:
        return json.loads(TODO_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def print_topics(db: list) -> None:
    topics = defaultdict(lambda: {"scores": [], "runs": 0})
    for r in db:
        t = topics[r.get("topic", "unknown")]
        t["runs"] += 1
        if r.get("qa_score") is not None:
            t["scores"].append(r["qa_score"])

    print(f"\n  {'Topic':<28} {'Runs':>5} {'Avg QA':>7}  Status")
    print("  " + "-" * 56)
    for topic, d in sorted(topics.items()):
        avg = sum(d["scores"]) / len(d["scores"]) if d["scores"] else 0
        status = "🔥 strong" if avg >= 42 else "⚠️  review" if avg >= 38 else "❌ low"
        print(f"  {topic:<28} {d['runs']:>5} {avg:>6.1f}/50  {status}")


def print_desk(db: list, manifest: list, todos: list) -> None:
    print("\n  ── LAUNCH DESK ──")
    pending = [t for t in todos if not t.get("done")]
    done = [t for t in todos if t.get("done")]
    if todos:
        for t in pending:
            print(f"  • {t['title']}")
        if done:
            print(f"  ✓ done: {', '.join(t['title'] for t in done)}")
    else:
        print("  (no to-do file yet — run notion_todo.py once)")

    clips_pending = sum(1 for c in manifest if not c.get("scheduled"))
    print(f"\n  Clips in engine:  {len(manifest)} total, {clips_pending} awaiting schedule")
    print(f"  Pipeline runs:    {len(db)}")


def main():
    parser = argparse.ArgumentParser(description="Florra OS dashboard")
    parser.add_argument("--topics", action="store_true", help="Topic summary only")
    args = parser.parse_args()

    db = load_db()
    manifest = load_manifest()
    todos = load_todos()

    print("═" * 60)
    print("  FLORRA OS — DASHBOARD  (the operating layer)")
    print("═" * 60)

    print_topics(db)
    if not args.topics:
        print_desk(db, manifest, todos)

    print("\n" + "═" * 60)


if __name__ == "__main__":
    main()
