"""Passive channel watchers.

Gating: the bot reacts only to (a) loc.gov links in configured
intake_channels, and (b) direct @mentions. It never speaks otherwise.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.context import AgentContext
from core.llm import STANDARD
from core.log import log_event

from agents.archivist import filing, loc

MENTION_PROMPT = """Recent channel context (newest last):
{context}

A staff member addressed the office:
{question}

Answer in one short, plain, backend-toned reply. Answers about canon come only
from the bible in your instructions or from what the message itself shows. If
the bible does not contain the answer, reply exactly: not in the file. — and,
if it seems worth keeping, add: log it with /untitled if it should be kept."""

MAX_URLS_PER_MESSAGE = 3


class PassiveIntake(commands.Cog):
    def __init__(self, bot: commands.Bot, ctx: AgentContext, system_prompt: str):
        self.bot = bot
        self.ctx = ctx
        self.system_prompt = system_prompt

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        in_intake = message.channel.id in self.ctx.config.intake_channels
        mentioned = self.bot.user is not None and self.bot.user.mentioned_in(message)
        if not in_intake and not mentioned:
            return  # gated: the bot never speaks otherwise

        # keep rolling per-channel context for mention answers
        self.ctx.memory.remember(
            message.channel.id, message.author.display_name, message.content
        )

        if in_intake:
            urls = loc.extract_loc_urls(message.content)
            if urls:
                await self._intake_urls(message, urls[:MAX_URLS_PER_MESSAGE])
                return

        if mentioned:
            await self._answer_mention(message)

    async def _intake_urls(self, message: discord.Message, urls: list[str]) -> None:
        if not self.ctx.limiter.allow(message.author.id, message.channel.id):
            return  # silent under throttle; the office does not argue
        for url in urls:
            result = await filing.file_source(
                self.ctx, self.system_prompt, url, filed_by="the bot"
            )
            if result.duplicate:
                await message.reply(result.message, mention_author=False)
            elif result.ok:
                await message.reply(result.caption_card, mention_author=False)
                try:
                    await message.add_reaction("✅")
                except discord.HTTPException:
                    pass
            else:
                await message.reply(result.message or "filing failed.", mention_author=False)
        log_event(self.ctx.log, "passive_intake", channel=message.channel.id, urls=len(urls))

    async def _answer_mention(self, message: discord.Message) -> None:
        if not self.ctx.limiter.allow(message.author.id, message.channel.id):
            return
        question = message.content
        if self.bot.user:
            question = question.replace(self.bot.user.mention, "").strip()
        if not question:
            await message.reply("state your business. the office is open.", mention_author=False)
            return
        context = "\n".join(
            f"{author}: {content}"
            for author, content in self.ctx.memory.recent(message.channel.id)
        )
        answer = await self.ctx.llm.complete(
            STANDARD,
            self.system_prompt,
            MENTION_PROMPT.format(context=context or "(none)", question=question),
            max_tokens=400,
        )
        answer = answer or "not in the file."
        self.ctx.memory.remember(message.channel.id, "the archivist bot", answer)
        await message.reply(answer[:1990], mention_author=False)
