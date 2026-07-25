"""Fleet runner — boots exactly one agent per process.

    python runner.py archivist

One Discord application (token) per agent, so agents scale and crash
independently. The runner is agent-agnostic: it loads agents/<name>/agent.yaml,
builds the shared services, imports agents.<name>, and calls its setup(bot, ctx).
Adding agent 002 requires zero changes here.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os

import discord
from discord.ext import commands

from core.config import load_agent_config
from core.context import AgentContext
from core.llm import ModelRouter
from core.log import get_logger, log_event
from core.memory import Memory
from core.notion import NotionAdapter
from core.ratelimit import RateLimiter


class FleetBot(commands.Bot):
    def __init__(self, agent_module, ctx: AgentContext):
        intents = discord.Intents.default()
        intents.message_content = True  # passive intake needs message content
        # honor an outbound proxy when the host requires one (discord.py does
        # not read env proxies on its own)
        proxy = os.environ.get("DISCORD_PROXY") or os.environ.get("HTTPS_PROXY") or None
        super().__init__(command_prefix="!fleet-unused!", intents=intents, proxy=proxy)
        self.agent_module = agent_module
        self.ctx = ctx

    async def setup_hook(self) -> None:
        await self.agent_module.setup(self, self.ctx)
        guild = discord.Object(id=self.ctx.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log_event(self.ctx.log, "commands_synced", count=len(synced))

    async def on_ready(self) -> None:
        log_event(
            self.ctx.log,
            "agent_online",
            agent=self.ctx.config.name,
            user=str(self.user),
            guild=self.ctx.config.guild_id,
        )


def build_context(agent_name: str) -> AgentContext:
    config = load_agent_config(agent_name)
    logger = get_logger(config.name, config.log_dir)
    return AgentContext(
        config=config,
        llm=ModelRouter(config.models, logger, config.max_tokens_default),
        notion=NotionAdapter(config.notion_token, config.notion_file_data_source_id),
        memory=Memory(config.db_path, config.name),
        limiter=RateLimiter(
            config.rate_limit.per_user_per_minute,
            config.rate_limit.per_channel_per_minute,
        ),
        log=logger,
    )


async def run(agent_name: str) -> None:
    ctx = build_context(agent_name)
    agent_module = importlib.import_module(f"agents.{agent_name}")
    if not hasattr(agent_module, "setup"):
        raise SystemExit(f"agents/{agent_name}/__init__.py must define async setup(bot, ctx)")
    bot = FleetBot(agent_module, ctx)
    async with bot:
        await bot.start(ctx.config.discord_token)


def main() -> None:
    parser = argparse.ArgumentParser(description="boot one fleet agent")
    parser.add_argument("agent", help="agent name, e.g. archivist")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.agent))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
