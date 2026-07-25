"""Slash command handlers for the Archivist."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.context import AgentContext
from core.llm import CANON, STANDARD
from core.log import log_event

from agents.archivist import filing, hunt, reports

BUSY = "the office is busy. try again in a minute."

STATUSES = {"filed", "untitled", "printed", "refused"}
CHAPTERS = {
    "001": "001 the cardinal stayed",
    "002": "002 nothing attached to them",
    "003": "003 the harbor answers",
    "unassigned": "unassigned",
}

LORECHECK_PROMPT = """A proposed lore idea follows. Check it against the bible \
in your instructions — and nothing else.

Reply in exactly this format:
line 1: one of CONSISTENT / CONTRADICTS / NOT IN THE FILE
line 2+: if CONTRADICTS — quote the exact clashing canon line from the bible, \
then one terse sentence on the clash. If NOT IN THE FILE — one terse sentence \
naming what canon it would touch (it is novel; it is not canon until a human \
files it). If CONSISTENT — one terse sentence saying what it lines up with.

Never invent canon. Never auto-canonize.

Proposed idea:
{idea}"""

DRAFT_PROMPTS = {
    "copy": """Write product copy for a garment lot built from this holding of \
THE FILE. House voice: lower-case-leaning, plain, southern-gothic backend tone. \
Two short paragraphs at most — the human sentence first, the lore under it. \
No hashtags, no exclamation marks, nothing that winks. Ground it in the \
holding and the bible only.

Holding:
{row}""",
    "obituary": """Write a drop announcement for this holding in the estate's \
obituary-clipping style (the estate announces, oxblood wax): a notice in a \
dying county newspaper. Short — a headline line, 2-4 sentences of notice, and \
close with "in lieu of flowers, attend." Ground it in the holding and the \
bible only. Never show or explain the animal.

Holding:
{row}""",
    "caption": """Write the finished caption card text for this holding — \
place · date · photographer · description · negative no., with the single \
appended line WHAT WAS TAKEN: completed in house voice. Terse, archival, \
lower-case-leaning. Output the card only.

Holding:
{row}""",
}


class ArchivistCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, ctx: AgentContext, system_prompt: str):
        self.bot = bot
        self.ctx = ctx
        self.system_prompt = system_prompt

    def _allowed(self, interaction: discord.Interaction) -> bool:
        return self.ctx.limiter.allow(
            interaction.user.id, interaction.channel_id or 0
        )

    @app_commands.command(name="ping", description="agent status: name + model routing")
    async def ping(self, interaction: discord.Interaction):
        config = self.ctx.config
        models = "\n".join(f"{tier}: {model}" for tier, model in config.models.items())
        await interaction.response.send_message(
            f"```\nagent {config.name} · online\n{models}\n```", ephemeral=True
        )

    @app_commands.command(name="file", description="full intake: loc.gov url or text -> THE FILE")
    @app_commands.describe(source="a loc.gov item url, or a description of the material")
    async def file(self, interaction: discord.Interaction, source: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        result = await filing.file_source(
            self.ctx, self.system_prompt, source, filed_by="the bot"
        )
        if result.duplicate:
            await interaction.followup.send(result.message)
        elif result.ok:
            await interaction.followup.send(result.caption_card)
        else:
            await interaction.followup.send(result.message or "filing failed.")

    @app_commands.command(name="test", description="taking test only — pass / fail weather / pending")
    @app_commands.describe(
        material="description or loc.gov url", file="also write the row to THE FILE"
    )
    async def test(self, interaction: discord.Interaction, material: str, file: bool = False):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        if file:
            result = await filing.file_source(
                self.ctx, self.system_prompt, material, filed_by="the bot"
            )
            await interaction.followup.send(
                result.caption_card or result.message or "filing failed."
            )
            return
        verdict = await filing.run_taking_test(self.ctx, material)
        reason = verdict["reason"] or "no reason recorded."
        await interaction.followup.send(
            f"```\nTAKING TEST {verdict['taking_test']}\n{reason}\n```"
        )

    @app_commands.command(name="lorecheck", description="check a lore idea against the bible")
    @app_commands.describe(idea="the proposed lore")
    async def lorecheck(self, interaction: discord.Interaction, idea: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        verdict = await self.ctx.llm.complete(
            STANDARD,
            self.system_prompt,
            LORECHECK_PROMPT.format(idea=idea),
            max_tokens=500,
        )
        log_event(self.ctx.log, "lorecheck", idea=idea[:120])
        await interaction.followup.send(verdict[:1990] or "not in the file.")

    @app_commands.command(name="untitled", description="quick capture — kept, status untitled")
    @app_commands.describe(idea="anything worth keeping")
    async def untitled(self, interaction: discord.Interaction, idea: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        result = await filing.file_untitled(self.ctx, idea, filed_by="the bot")
        await interaction.followup.send(result.message)

    @app_commands.command(name="hunt", description="scout loc.gov for archive candidates")
    @app_commands.describe(query="what to hunt for, e.g. 'abandoned church alabama'")
    async def hunt(self, interaction: discord.Interaction, query: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        picks = await hunt.hunt(self.ctx, query)
        if not picks:
            await interaction.followup.send("the archive gave nothing back for that.")
            return
        embeds = []
        for pick in picks[:5]:
            marker = "already in the file" if pick.already_filed else pick.reason
            embed = discord.Embed(
                title=pick.title[:250],
                url=pick.item_url,
                description=f"TAKING TEST {pick.verdict} — {marker}"[:300],
            )
            if pick.date:
                embed.set_footer(text=pick.date)
            if pick.thumbnail:
                embed.set_thumbnail(url=pick.thumbnail)
            embeds.append(embed)
        await interaction.followup.send(
            "the hunt returned. file a pick with /file <link>.", embeds=embeds
        )

    @app_commands.command(name="draft", description="write copy for a filed holding, in the estate's voice")
    @app_commands.describe(negative="the negative no. (the BS-E number)", kind="what to draft")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="product copy", value="copy"),
            app_commands.Choice(name="obituary drop announcement", value="obituary"),
            app_commands.Choice(name="caption card", value="caption"),
        ]
    )
    async def draft(self, interaction: discord.Interaction, negative: int, kind: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        rows = await self.ctx.notion.query(
            filter={"property": "Negative No.", "unique_id": {"equals": negative}},
            page_size=1,
        )
        if not rows:
            await interaction.followup.send(f"no holding BS-E-{negative} in the file.")
            return
        page = rows[0]
        read = self.ctx.notion.plain_text
        row = "\n".join(
            f"{name}: {read(page, name)}"
            for name in (
                "Negative No.", "Title", "Source Date", "Photographer", "Class",
                "Region", "Status", "Taking Test", "Chapter", "What Was Taken",
                "LOC LOT", "Notes",
            )
            if read(page, name)
        )
        text = await self.ctx.llm.complete(
            CANON,
            self.system_prompt,
            DRAFT_PROMPTS[kind].format(row=row),
            max_tokens=2000,
        )
        log_event(self.ctx.log, "draft", negative=negative, kind=kind)
        await interaction.followup.send(text[:1990] or "the desk produced nothing. try again.")

    @app_commands.command(name="coverage", description="check holdings against shooting script no. 1")
    async def coverage(self, interaction: discord.Interaction):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        report = await reports.build_coverage(self.ctx, self.system_prompt)
        await interaction.followup.send(report)

    @app_commands.command(name="ledger", description="what the office filed this week")
    async def ledger(self, interaction: discord.Interaction):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await reports.build_ledger(self.ctx))

    @app_commands.command(name="status", description="read THE FILE by title, chapter, or status")
    @app_commands.describe(query="a status (filed/untitled/printed/refused), chapter (001/002/003/unassigned), or title text")
    async def status(self, interaction: discord.Interaction, query: str):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()

        q = query.strip()
        if q.lower() in STATUSES:
            filter_ = {"property": "Status", "select": {"equals": q.lower()}}
        elif q.lower() in CHAPTERS:
            filter_ = {"property": "Chapter", "select": {"equals": CHAPTERS[q.lower()]}}
        else:
            filter_ = {"property": "Title", "title": {"contains": q}}

        rows = await self.ctx.notion.query(filter=filter_, page_size=10)
        if not rows:
            await interaction.followup.send("nothing in the file for that.")
            return

        read = self.ctx.notion.plain_text
        lines = []
        for page in rows:
            lines.append(
                " · ".join(
                    part
                    for part in (
                        read(page, "Negative No.") or "—",
                        (read(page, "Title") or "untitled")[:60],
                        read(page, "Class"),
                        read(page, "Status"),
                        read(page, "Chapter"),
                    )
                    if part
                )
            )
        await interaction.followup.send("```\n" + "\n".join(lines)[:1900] + "\n```")
