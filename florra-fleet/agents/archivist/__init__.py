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


async def setup(bot, ctx) -> None:
    from agents.archivist.commands import ArchivistCommands
    from agents.archivist.intake import PassiveIntake

    system_prompt = build_system_prompt()
    await bot.add_cog(ArchivistCommands(bot, ctx, system_prompt))
    await bot.add_cog(PassiveIntake(bot, ctx, system_prompt))
