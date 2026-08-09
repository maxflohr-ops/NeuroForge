"""Agent 001 — the Archivist.

The runner calls setup(bot, ctx). Everything the archivist does lives in
this package; core/ knows nothing about it.
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def build_system_prompt() -> str:
    """{role + hard rules} + {full BIBLE.md} + {output formats} — assembled
    from system.md with the bible snapshot injected."""
    template = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    bible = (PROMPTS_DIR / "BIBLE.md").read_text(encoding="utf-8")
    return template.replace("{{BIBLE}}", bible)


def build_web_system_prompt() -> str:
    """The front-desk persona for the website chat — warmer voice, same canon,
    same never-invent rules."""
    template = (PROMPTS_DIR / "frontdesk.md").read_text(encoding="utf-8")
    bible = (PROMPTS_DIR / "BIBLE.md").read_text(encoding="utf-8")
    return template.replace("{{BIBLE}}", bible)


def refresh_bible_from_notion(config) -> int:
    """Pull the live bible page and rewrite BIBLE.md. Returns the character
    count written. Raises on failure — callers keep the committed snapshot."""
    from core.notion import fetch_page_markdown

    if not config.notion_bible_page_id:
        raise RuntimeError("NOTION_BIBLE_PAGE_ID not set")
    markdown = fetch_page_markdown(config.notion_token, config.notion_bible_page_id)
    header = (
        "<!-- BIBLE.md — synced snapshot of the Notion bible page ('the estate').\n"
        "     Regenerate with: python scripts/sync_bible.py\n"
        "     Do not hand-edit: canon lives in Notion; this file is a mirror. -->\n\n"
        "# bandersnatch · the estate\n\n"
    )
    (PROMPTS_DIR / "BIBLE.md").write_text(header + markdown, encoding="utf-8")
    return len(markdown)


class SystemPrompts:
    """Mutable holder so /resync can re-read the bible without a restart."""

    def __init__(self):
        self.office = build_system_prompt()
        self.frontdesk = build_web_system_prompt()

    def rebuild(self) -> None:
        self.office = build_system_prompt()
        self.frontdesk = build_web_system_prompt()


def build_prompts(ctx) -> SystemPrompts:
    """Boot-time prompt assembly: try the live bible first so a long-running
    process starts on current canon; fall back to the committed snapshot."""
    try:
        chars = refresh_bible_from_notion(ctx.config)
        from core.log import log_event

        log_event(ctx.log, "bible_synced", chars=chars)
    except Exception as exc:
        from core.log import log_event

        log_event(ctx.log, "bible_sync_skipped", reason=str(exc)[:200])
    return SystemPrompts()


async def setup(bot, ctx) -> None:
    from agents.archivist.commands import ArchivistCommands
    from agents.archivist.intake import PassiveIntake

    prompts = build_prompts(ctx)
    await bot.add_cog(ArchivistCommands(bot, ctx, prompts))
    await bot.add_cog(PassiveIntake(bot, ctx, prompts))
