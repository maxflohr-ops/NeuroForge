#!/usr/bin/env python3
"""
Florra OS — Notion To-do CLI
============================
The daily desk → Notion. Adds tasks to the Florra to-do database via the
Notion API. If NOTION_TOKEN / NOTION_DB_ID are not set, it falls back to a
local JSON store (florra_todos.json) so the desk works before the integration
token exists — and prints the exact payload it would have sent.

Usage:
    python notion_todo.py add "Revoke old Telegram token in BotFather" --tag security
    python notion_todo.py add "Host Postiz and connect TikTok/IG/YouTube" --tag launch
    python notion_todo.py list
    python notion_todo.py done <id>

Env:
    NOTION_TOKEN   — Notion internal integration token (secret_...)
    NOTION_DB_ID   — the database id (from the Notion page URL)

Seeded items (the current Florra launch desk):
    - Revoke old Telegram bot token in BotFather (security)
    - Host Postiz and connect TikTok / Instagram / YouTube (launch)
    - Add POSTIZ_API_KEY + ANTHROPIC_API_KEY as GitHub Actions secrets (launch)
    - Optionally deploy ADK agents to Cloud Run via agents-cli (infra)
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

TOKEN = os.getenv("NOTION_TOKEN", "")
DB_ID = os.getenv("NOTION_DB_ID", "")
LOCAL_STORE = Path(__file__).resolve().parent / "florra_todos.json"

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

SEED = [
    {"title": "Revoke old Telegram bot token in BotFather", "tag": "security"},
    {"title": "Host Postiz and connect TikTok / Instagram / YouTube", "tag": "launch"},
    {"title": "Add POSTIZ_API_KEY + ANTHROPIC_API_KEY as GitHub Actions secrets", "tag": "launch"},
    {"title": "Deploy ADK agents to Cloud Run via agents-cli (optional)", "tag": "infra"},
]


# ── Local store (fallback) ─────────────────────────────────────────────────

def load_local() -> list:
    if LOCAL_STORE.exists():
        return json.loads(LOCAL_STORE.read_text(encoding="utf-8"))
    # Seed on first run
    records = [
        {"id": str(uuid.uuid4())[:8], "title": s["title"], "tag": s["tag"],
         "done": False, "created": datetime.now(timezone.utc).isoformat()}
        for s in SEED
    ]
    save_local(records)
    return records


def save_local(records: list) -> None:
    LOCAL_STORE.write_text(json.dumps(records, indent=2), encoding="utf-8")


# ── Notion API (real) ──────────────────────────────────────────────────────

def notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_add(title: str, tag: str = "") -> str:
    import requests
    payload = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Tag": {"select": {"name": tag}} if tag else None,
        },
    }
    if not payload["properties"]["Tag"]:
        del payload["properties"]["Tag"]
    resp = requests.post(f"{API}/pages", headers=notion_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


# ── CLI ────────────────────────────────────────────────────────────────────

def cmd_add(args):
    if TOKEN and DB_ID:
        page_id = notion_add(args.title, args.tag)
        print(f"✓ Added to Notion: {args.title!r} ({page_id})")
        return

    records = load_local()
    records.append({
        "id": str(uuid.uuid4())[:8], "title": args.title, "tag": args.tag,
        "done": False, "created": datetime.now(timezone.utc).isoformat(),
    })
    save_local(records)
    print(f"✓ Added to local store (NOTION_TOKEN not set): {args.title!r} [{records[-1]['id']}]")
    if args.tag:
        print(f"  Would send to Notion with Tag={args.tag!r}")


def cmd_list(args):
    records = load_local()
    if not records:
        print("No todos.")
        return
    for r in records:
        mark = "✓" if r.get("done") else "•"
        tag = f" [{r.get('tag', '')}]" if r.get("tag") else ""
        print(f"{mark} {r['id']}  {r['title']}{tag}")


def cmd_done(args):
    records = load_local()
    for r in records:
        if r["id"] == args.id:
            r["done"] = True
            save_local(records)
            print(f"✓ Marked done: {r['title']}")
            return
    print(f"Not found: {args.id}", file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Florra OS Notion to-do CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Add a task")
    a.add_argument("title")
    a.add_argument("--tag", default="")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="List tasks")
    l.set_defaults(func=cmd_list)

    d = sub.add_parser("done", help="Mark task done")
    d.add_argument("id")
    d.set_defaults(func=cmd_done)

    return parser.parse_args()


def main():
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
