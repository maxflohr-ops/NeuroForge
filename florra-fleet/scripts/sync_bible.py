"""Pull the Notion bible page -> agents/archivist/prompts/BIBLE.md.

Run manually for now (cron later):

    python scripts/sync_bible.py

The bible in Notion is canon; BIBLE.md is a mirror the bot ships with.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from core.notion import fetch_page_markdown

FLEET_ROOT = Path(__file__).resolve().parent.parent
BIBLE_PATH = FLEET_ROOT / "agents" / "archivist" / "prompts" / "BIBLE.md"

HEADER = (
    "<!-- BIBLE.md — synced snapshot of the Notion bible page ('the estate').\n"
    "     Regenerate with: python scripts/sync_bible.py\n"
    "     Do not hand-edit: canon lives in Notion; this file is a mirror. -->\n\n"
    "# bandersnatch · the estate\n\n"
)


def main() -> None:
    load_dotenv(FLEET_ROOT / ".env")
    token = os.environ.get("NOTION_TOKEN", "").strip()
    page_id = os.environ.get("NOTION_BIBLE_PAGE_ID", "").strip()
    if not token or not page_id:
        raise SystemExit("set NOTION_TOKEN and NOTION_BIBLE_PAGE_ID in .env")

    markdown = fetch_page_markdown(token, page_id)
    BIBLE_PATH.write_text(HEADER + markdown, encoding="utf-8")
    tokens_estimate = len(markdown) // 4
    print(f"wrote {BIBLE_PATH} ({len(markdown)} chars, ~{tokens_estimate} tokens)")
    if tokens_estimate > 50_000:
        print(
            "WARNING: bible exceeds ~50k tokens — per the build spec, split "
            "per-command sections before adding anything like RAG."
        )


if __name__ == "__main__":
    main()
