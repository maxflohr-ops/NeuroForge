"""Agent 002 — velo, the Florra ops agent.

A Discord command surface over the Florra CRM & Operations Hub (Airtable).
core/ knows nothing about it; the runner boots it by name.
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def build_system_prompt() -> str:
    return (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


async def setup(bot, ctx) -> None:
    from agents.velo.commands import VeloCommands

    await bot.add_cog(VeloCommands(bot, ctx, build_system_prompt()))
