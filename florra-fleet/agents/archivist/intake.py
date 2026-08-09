"""Passive channel watchers.

Gating: the bot reacts only to (a) loc.gov links in configured
intake_channels, and (b) direct @mentions. It never speaks otherwise.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from core.context import AgentContext
from core.llm import STANDARD
from core.log import log_event

from agents.archivist import filing, loc, reports

MENTION_PROMPT = """Recent channel context (newest last):
{context}

A staff member addressed the office:
{question}

Answer in one short, plain reply — courteous, even warm, but still the office:
no exclamation marks, no emoji, no salesman energy. Help them get what they
came for; a closing pointer to a useful command is welcome. Answers about
canon come only from the bible in your instructions or from what the message
itself shows. If the bible does not contain the answer, reply exactly:
not in the file. — and, if it seems worth keeping, kindly offer /untitled."""

MAX_URLS_PER_MESSAGE = 3

COMMAND_MENU = (
    "-# the office also answers: /file · /test · /lorecheck · /untitled · "
    "/status · /hunt · /draft · /coverage · /ledger · /ping"
)


class PassiveIntake(commands.Cog):
    def __init__(self, bot: commands.Bot, ctx: AgentContext, prompts):
        self.bot = bot
        self.ctx = ctx
        self.prompts = prompts
        options = ctx.config.options or {}
        self.ledger_cfg = options.get("ledger") or {}
        self.tip_channel = (options.get("tipline") or {}).get("channel_id")
        self.workup_cfg = options.get("auto_workup") or {}
        if self.ledger_cfg.get("channel_id"):
            self.ledger_tick.start()

    def cog_unload(self) -> None:
        self.ledger_tick.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        if self.tip_channel and message.channel.id == self.tip_channel:
            await self._intake_tip(message)
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
            if not mentioned and self.workup_cfg.get("enabled"):
                await self._auto_workup(message)
                return

        if mentioned:
            await self._answer_mention(message)

    async def _intake_urls(self, message: discord.Message, urls: list[str]) -> None:
        if not self.ctx.limiter.allow(message.author.id, message.channel.id):
            return  # silent under throttle; the office does not argue
        for url in urls:
            result = await filing.file_source(
                self.ctx, self.prompts.office, url, filed_by="the bot"
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

    async def _auto_workup(self, message: discord.Message) -> None:
        """The full treatment for a plain post: taking test + lorecheck + the
        command menu. Everything the office can answer, unprompted."""
        text = message.content.strip()
        if len(text) < int(self.workup_cfg.get("min_chars", 15)):
            return
        if not self.ctx.limiter.allow(message.author.id, message.channel.id):
            return  # silent under throttle; the office does not argue

        from agents.archivist.commands import LORECHECK_PROMPT

        verdict = await filing.run_taking_test(self.ctx, text)
        lorecheck = await self.ctx.llm.complete(
            STANDARD,
            self.prompts.office,
            LORECHECK_PROMPT.format(idea=text),
            max_tokens=500,
        )
        reason = verdict["reason"] or "no reason recorded."
        reply = (
            f"```\nTAKING TEST {verdict['taking_test']} — {reason}\n```\n"
            f"{lorecheck.strip() or 'NOT IN THE FILE'}\n"
            f"keep it: /untitled · file a plate: /file <loc.gov link>\n"
            f"{COMMAND_MENU}"
        )
        self.ctx.memory.remember(message.channel.id, "the archivist bot", reply[:500])
        await message.reply(reply[:1990], mention_author=False)
        log_event(self.ctx.log, "auto_workup", channel=message.channel.id)

    async def _intake_tip(self, message: discord.Message) -> None:
        """The tip line: every report is kept as an untitled harbor-contract
        candidate. Active only when config names a channel (legal gate)."""
        if not self.ctx.limiter.allow(message.author.id, message.channel.id):
            return
        if len(message.content.strip()) < 10:
            return  # not a report
        result = await filing.file_tip(
            self.ctx, message.content, reporter=message.author.display_name
        )
        try:
            await message.add_reaction("🕯️")
        except discord.HTTPException:
            pass
        await message.reply(result.message, mention_author=False)

    # -- the weekly ledger ----------------------------------------------

    @tasks.loop(minutes=20)
    async def ledger_tick(self) -> None:
        cfg = self.ledger_cfg
        tz = ZoneInfo(str(cfg.get("timezone", "America/Los_Angeles")))
        now = datetime.now(tz)
        if now.weekday() != int(cfg.get("weekday", 6)) or now.hour != int(cfg.get("hour", 10)):
            return
        iso = now.isocalendar()
        week_key = f"ledger:{iso.year}-W{iso.week}"
        if self.ctx.memory.dedupe_get(week_key):
            return  # already posted this week
        channel = self.bot.get_channel(int(cfg["channel_id"]))
        if channel is None:
            return
        ledger = await reports.build_ledger(self.ctx)
        await channel.send(ledger)
        self.ctx.memory.dedupe_set(week_key, now.isoformat())
        log_event(self.ctx.log, "ledger_posted", week=week_key)

    @ledger_tick.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

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
            self.prompts.office,
            MENTION_PROMPT.format(context=context or "(none)", question=question),
            max_tokens=400,
        )
        answer = answer or "not in the file."
        self.ctx.memory.remember(message.channel.id, "the archivist bot", answer)
        await message.reply(answer[:1990], mention_author=False)
