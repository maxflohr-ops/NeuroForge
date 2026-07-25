"""Reports read out of THE FILE: the weekly ledger and shooting-script coverage."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from core.context import AgentContext
from core.llm import STANDARD

COVERAGE_PROMPT = """Shooting Script No. 1 (chapter 002) lists 12 numbered \
subjects — they are in the bible in your instructions. Below are the current \
holdings of THE FILE. Map holdings to subjects and report coverage.

Reply as a terse checklist, one line per subject, in this exact shape:
 1. [x] chimneys standing alone — covered by BS-E-4 <short title>
 2. [ ] a doorstep with no door — not in the file
(use [x] only when a holding plausibly serves the subject; cite its negative \
no. when you can. after the 12 lines, one closing line: how many of twelve are \
covered, and whether coverage can close — it closes at three garments and one \
notice, not eight.)

Holdings:
{holdings}"""


async def rows_filed_since(ctx: AgentContext, days: int = 7) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return await ctx.notion.query(
        filter={"timestamp": "created_time", "created_time": {"on_or_after": since}},
        sorts=[{"timestamp": "created_time", "direction": "ascending"}],
        page_size=50,
    )


async def build_ledger(ctx: AgentContext) -> str:
    """The weekly ledger: what the office filed this week."""
    rows = await rows_filed_since(ctx, days=7)
    read = ctx.notion.plain_text
    if not rows:
        return (
            "```\nTHE LEDGER — weekly filing report\n"
            "nothing crossed the desk this week. the file is never closed.\n```"
        )

    by_status = Counter(read(p, "Status") or "?" for p in rows)
    by_class = Counter(read(p, "Class") or "?" for p in rows)
    lines = [
        "THE LEDGER — weekly filing report",
        f"{len(rows)} item(s) crossed the desk.",
        "status: " + " · ".join(f"{k} {v}" for k, v in by_status.most_common()),
        "class:  " + " · ".join(f"{k} {v}" for k, v in by_class.most_common()),
        "",
    ]
    for page in rows[:15]:
        lines.append(
            " · ".join(
                part
                for part in (
                    read(page, "Negative No.") or "—",
                    (read(page, "Title") or "untitled")[:55],
                    read(page, "Status"),
                    read(page, "Taking Test"),
                )
                if part
            )
        )
    if len(rows) > 15:
        lines.append(f"… and {len(rows) - 15} more in the file.")
    lines.append("")
    lines.append("the office keeps everything. services next sunday, 10 a.m.")
    return "```\n" + "\n".join(lines)[:1900] + "\n```"


async def build_coverage(ctx: AgentContext, system_full: str) -> str:
    """Check holdings against the 12 subjects of Shooting Script No. 1."""
    rows = await ctx.notion.query(
        sorts=[{"timestamp": "created_time", "direction": "ascending"}], page_size=60
    )
    read = ctx.notion.plain_text
    holdings = []
    for page in rows:
        status = read(page, "Status")
        if status == "refused":
            continue
        holdings.append(
            " | ".join(
                part
                for part in (
                    read(page, "Negative No.") or "—",
                    (read(page, "Title") or "untitled")[:80],
                    read(page, "Class"),
                    (read(page, "What Was Taken") or "")[:80],
                )
                if part
            )
        )
    if not holdings:
        return "the file is empty. coverage has not begun."
    report = await ctx.llm.complete(
        STANDARD,
        system_full,
        COVERAGE_PROMPT.format(holdings="\n".join(holdings)),
        max_tokens=1000,
    )
    return report[:1900] or "coverage could not be assessed."
