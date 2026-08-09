"""Slash commands for florra — the ops desk over the CRM."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.airtable import Airtable
from core.context import AgentContext
from core.llm import STANDARD

BUSY = "the desk is busy. try again in a minute."

OUTREACH_PROMPT = """Draft an outreach message for Florra to the person below.
Professional, warm, specific — reference something real from their record
(platform, niche, following, recent hit). Name the ask plainly. No superlatives,
no fake scarcity. Sign as Florra. Keep it to a short paragraph or two.

{intent}

Person record:
{person}"""


class FlorraCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, ctx: AgentContext, system_prompt: str):
        self.bot = bot
        self.ctx = ctx
        self.system_prompt = system_prompt
        opts = (ctx.config.options or {}).get("airtable", {})
        self.base = opts.get("base_id", "")
        self.tables = opts.get("tables", {})

    def _allowed(self, interaction: discord.Interaction) -> bool:
        return self.ctx.limiter.allow(interaction.user.id, interaction.channel_id or 0)

    def _table(self, key: str) -> str:
        return self.tables.get(key, key)

    @app_commands.command(name="ping", description="agent status: name + model routing")
    async def ping(self, interaction: discord.Interaction):
        c = self.ctx.config
        models = "\n".join(f"{t}: {m}" for t, m in c.models.items())
        at = "connected" if isinstance(self.ctx.airtable, Airtable) else "no AIRTABLE_API_KEY"
        await interaction.response.send_message(
            f"```\nagent {c.name} · online\nairtable: {at}\n{models}\n```", ephemeral=True
        )

    @app_commands.command(name="roster", description="search the CRM People table")
    @app_commands.describe(query="name, niche, brand, or leave blank for top-priority")
    async def roster(self, interaction: discord.Interaction, query: str = ""):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        fields = ["Full Name", "Person Type", "Relationship Tier", "Priority",
                  "Instagram", "TikTok", "Influence Score", "Scout Status"]
        formula = None
        if query.strip():
            q = query.replace('"', '\\"')
            formula = (
                f'OR(FIND(LOWER("{q}"),LOWER({{Full Name}}&"")),'
                f'FIND(LOWER("{q}"),LOWER({{Brand Affiliation}}&"")),'
                f'FIND(LOWER("{q}"),LOWER({{Notes}}&"")))'
            )
        rows = await self.ctx.airtable.list_records(
            self.base, self._table("people"), formula=formula, max_records=12, fields=fields,
            sort=[{"field": "Priority", "direction": "asc"}],
        )
        if not rows:
            await interaction.followup.send("no one in the CRM matches that.")
            return
        v = Airtable.val
        lines = []
        for r in rows:
            lines.append(
                " · ".join(p for p in (
                    v(r, "Full Name") or "—",
                    v(r, "Person Type"),
                    v(r, "Relationship Tier"),
                    (("IG " + v(r, "Instagram")) if v(r, "Instagram") else ""),
                    (("infl " + v(r, "Influence Score")) if v(r, "Influence Score") else ""),
                ) if p)
            )
        await interaction.followup.send("```\n" + "\n".join(lines)[:1900] + "\n```")

    @app_commands.command(name="prospects", description="the pitch pipeline by stage")
    async def prospects(self, interaction: discord.Interaction):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        rows = await self.ctx.airtable.list_records(
            self.base, self._table("prospects"), max_records=200,
            fields=["Brand Name", "Target Status", "Priority", "Estimated Budget", "Industry"],
        )
        if not rows:
            await interaction.followup.send("no prospects on file.")
            return
        v = Airtable.val
        by_stage = Counter(v(r, "Target Status") or "unset" for r in rows)
        lines = [f"{len(rows)} prospects in the pipeline.", ""]
        lines += [f"{stage}: {n}" for stage, n in by_stage.most_common()]
        # show the highest-priority handful
        top = sorted(rows, key=lambda r: v(r, "Priority"))[:8]
        lines.append("")
        lines.append("top of the list:")
        for r in top:
            lines.append(" · ".join(p for p in (
                v(r, "Brand Name") or "—", v(r, "Target Status"),
                v(r, "Estimated Budget"), v(r, "Industry")) if p))
        await interaction.followup.send("```\n" + "\n".join(lines)[:1900] + "\n```")

    @app_commands.command(name="outreach", description="draft outreach for a person (and optionally log it)")
    @app_commands.describe(
        person="name to search the CRM for",
        intent="the ask, e.g. 'seed the new drop, gifting + one reel'",
        log="also log this as a planned outreach record",
    )
    async def outreach(
        self, interaction: discord.Interaction, person: str, intent: str = "", log: bool = False
    ):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        q = person.replace('"', '\\"')
        rows = await self.ctx.airtable.list_records(
            self.base, self._table("people"),
            formula=f'FIND(LOWER("{q}"),LOWER({{Full Name}}&""))', max_records=1,
        )
        if not rows:
            await interaction.followup.send(f"no one named “{person}” in the CRM.")
            return
        rec = rows[0]
        v = Airtable.val
        person_block = "\n".join(
            f"{f}: {v(rec, f)}" for f in (
                "Full Name", "Person Type", "Brand Affiliation", "Instagram", "TikTok",
                "YouTube", "Influence Score", "Relationship Tier", "Recent Viral Hit", "Notes")
            if v(rec, f)
        )
        draft = await self.ctx.llm.complete(
            STANDARD, self.system_prompt,
            OUTREACH_PROMPT.format(
                intent=(f"The ask: {intent}" if intent else "The ask: an initial partnership."),
                person=person_block),
            max_tokens=600,
        )
        reply = f"**draft — {v(rec, 'Full Name')}**\n{draft.strip()[:1600]}"
        if log:
            try:
                await self.ctx.airtable.create_record(
                    self.base, self._table("outreach"),
                    {
                        "Subject": f"Florra × {v(rec, 'Full Name')}"[:100],
                        "Status": "Drafted",
                        "Notes": (intent or "initial partnership") + "\n\n" + draft.strip()[:900],
                        "People": [rec["id"]],
                        "Date": datetime.now(timezone.utc).date().isoformat(),
                    },
                )
                reply += "\n\n*logged to Outreach (status Drafted).*"
            except Exception as exc:
                reply += f"\n\n*could not log it: {str(exc)[:120]}*"
        await interaction.followup.send(reply[:1990])

    @app_commands.command(name="adreport", description="ad performance summary (last N days)")
    @app_commands.describe(days="lookback window, default 7")
    async def adreport(self, interaction: discord.Interaction, days: int = 7):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        rows = await self.ctx.airtable.list_records(
            self.base, self._table("daily_ad_performance"), max_records=400,
            fields=["Date", "Spend", "Impressions", "Clicks", "Views", "Conversions",
                    "CTR", "CPV", "CPC", "Campaign"],
        )

        def num(r, f):
            raw = r.get("fields", {}).get(f)
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0

        recent = [r for r in rows if Airtable.val(r, "Date")[:10] >= since]
        if not recent:
            await interaction.followup.send(f"no ad performance recorded in the last {days} days.")
            return
        spend = sum(num(r, "Spend") for r in recent)
        impr = sum(num(r, "Impressions") for r in recent)
        clicks = sum(num(r, "Clicks") for r in recent)
        views = sum(num(r, "Views") for r in recent)
        conv = sum(num(r, "Conversions") for r in recent)
        ctr = (clicks / impr * 100) if impr else 0
        cpc = (spend / clicks) if clicks else 0
        cpv = (spend / views) if views else 0
        lines = [
            f"AD REPORT — last {days} days ({len(recent)} day-rows)",
            f"spend: ${spend:,.2f}  ·  impressions: {impr:,.0f}  ·  clicks: {clicks:,.0f}",
            f"views: {views:,.0f}  ·  conversions: {conv:,.0f}",
            f"CTR: {ctr:.2f}%  ·  CPC: ${cpc:,.2f}  ·  CPV: ${cpv:,.3f}",
        ]
        if conv == 0 and spend > 0:
            lines.append("flag: spend with zero recorded conversions in-window.")
        await interaction.followup.send("```\n" + "\n".join(lines) + "\n```")

    @app_commands.command(name="clients", description="active retainer clients + spend under management")
    async def clients(self, interaction: discord.Interaction):
        if not self._allowed(interaction):
            await interaction.response.send_message(BUSY, ephemeral=True)
            return
        await interaction.response.defer()
        rows = await self.ctx.airtable.list_records(
            self.base, self._table("clients"), max_records=100,
            fields=["Client Name", "Status", "Retainer Amount",
                    "Monthly Ad Spend Under Management", "Services Running"],
        )
        if not rows:
            await interaction.followup.send("no clients on file.")
            return
        v = Airtable.val

        def num(r, f):
            try:
                return float(r.get("fields", {}).get(f) or 0)
            except (TypeError, ValueError):
                return 0.0

        retainer = sum(num(r, "Retainer Amount") for r in rows)
        aum = sum(num(r, "Monthly Ad Spend Under Management") for r in rows)
        lines = [f"{len(rows)} clients · retainers ${retainer:,.0f}/mo · ad spend managed ${aum:,.0f}/mo", ""]
        for r in rows[:12]:
            lines.append(" · ".join(p for p in (
                v(r, "Client Name") or "—", v(r, "Status"),
                (("$" + v(r, "Retainer Amount") + "/mo") if v(r, "Retainer Amount") else ""),
                v(r, "Services Running")) if p))
        await interaction.followup.send("```\n" + "\n".join(lines)[:1900] + "\n```")
