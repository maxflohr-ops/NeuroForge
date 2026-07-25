"""The filing pipeline — shared by /file, /test file:true, and passive intake.

fetch -> dedupe -> taking test + classification (classify tier) ->
"What Was Taken" (standard tier, house voice) -> write to THE FILE ->
caption card.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

from core.context import AgentContext
from core.llm import CANON, CLASSIFY, STANDARD
from core.log import log_event
from core.notion import (
    prop_files_upload,
    prop_rich_text,
    prop_select,
    prop_title,
    prop_url,
)

from agents.archivist import loc

MAX_VISION_BYTES = 4_500_000  # api image limit is 5MB; stay under it

VALID_CLASSES = {
    ".3100 dwellings unoccupied",
    ".9026 organized gatherings",
    ".9100 churches",
    ".9200 cemeteries",
    ".4000 land eroded",
    ".5000 commerce closed",
    ".7000 roads and rail",
    ".8000 water and harbor",
    ".0000 unclassified",
}
VALID_REGIONS = {"E southern", "E coastal annex"}
VALID_TEST = {"pass", "fail weather", "pending"}

# Classification runs on the cheap tier with a compact doctrine — the full
# bible is not needed to run the Taking Test.
CLASSIFY_SYSTEM = """You are the classification clerk of a photo archive. \
Output ONLY a JSON object, nothing else.

The Taking Test: material passes only if something was TAKEN — economic \
extraction (foreclosure, auction, emptied tenant houses, boarded storefronts, \
land eroded from cash-cropping, towns dead when the mine or the price died, \
the Dust Bowl as farming-for-profit). Weather alone — hurricane, flood, fire, \
hard winter — FAILS as "fail weather". Material that is neither extraction nor \
weather (portraits, war production, plenty, unrelated subjects) is "pending", \
as is anything you cannot tell. "fail weather" is ONLY for weather. Never guess.

Class numbers (pick exactly one string):
".3100 dwellings unoccupied", ".9026 organized gatherings", ".9100 churches", \
".9200 cemeteries", ".4000 land eroded", ".5000 commerce closed", \
".7000 roads and rail", ".8000 water and harbor", ".0000 unclassified"
Uncertain -> ".0000 unclassified".

Region: "E southern" (default; the county, inland, Appalachia, the South) or \
"E coastal annex" (harbors, coast, California, salt water).

If a photograph is attached, judge from the photograph itself first, the
metadata second. Also report whether people are visible:
"people": "none" (no people), "present" (people small/incidental/faces not
legible), or "prominent" (a person or face is a clear subject).

JSON shape:
{"taking_test": "pass" | "fail weather" | "pending",
 "reason": "<one short lower-case sentence>",
 "class": "<one class string>",
 "region": "<one region string>",
 "people": "none" | "present" | "prominent"}"""

LORE_MEMO_PROMPT = """Write a short internal memo (2-4 sentences, house voice, \
lower-case-leaning) on how this material might sit in the bandersnatch lore: \
which chapter it could serve, what the beast took here, what stayed, and any \
design angle (print, clipping, caption card). Ground every claim in the bible \
or in what the photograph/metadata actually shows — do not invent canon.

Then two closing lines, exactly:
suggested chapter: <exactly one of: 001 the cardinal stayed / \
002 nothing attached to them / 003 the harbor answers / unassigned>
memo only. not canon until a human files it.

Material:
{description}"""

VALID_CHAPTERS = {
    "001 the cardinal stayed",
    "002 nothing attached to them",
    "003 the harbor answers",
    "unassigned",
}


@dataclass
class FilingResult:
    ok: bool
    duplicate: bool = False
    caption_card: str = ""
    page_url: str = ""
    message: str = ""


def _caption_card(
    title: str,
    date: str,
    photographer: str,
    class_: str,
    region: str,
    test: str,
    taken: str,
    loc_lot: str,
    status: str,
    filed_by: str,
    page_url: str,
) -> str:
    lines = [
        " · ".join(part for part in (title, date, photographer) if part),
        f"CLASS {class_} · REGION {region} · TAKING TEST {test}",
        f"WHAT WAS TAKEN: {taken or '————'}",
        f"LOT {loc_lot or '—'} · STATUS {status} · filed by {filed_by}",
    ]
    card = "```\n" + "\n".join(lines) + "\n```"
    if page_url:
        card += f"\n{page_url}"
    return card


async def run_taking_test(
    ctx: AgentContext,
    description: str,
    images: list[tuple[str, str]] | None = None,
) -> dict:
    """Taking test + class + region (+ people flag) in one classify-tier call,
    judged from the photograph itself when one is available. Uncertainty
    resolves to pending / .0000 — never a guess."""
    parsed = await ctx.llm.complete_json(
        CLASSIFY,
        CLASSIFY_SYSTEM,
        f"Material to classify:\n{description}",
        max_tokens=300,
        images=images,
    )
    parsed = parsed or {}
    test = parsed.get("taking_test", "pending")
    class_ = parsed.get("class", ".0000 unclassified")
    region = parsed.get("region", "E southern")
    people = parsed.get("people", "")
    return {
        "taking_test": test if test in VALID_TEST else "pending",
        "reason": str(parsed.get("reason", ""))[:300],
        "class": class_ if class_ in VALID_CLASSES else ".0000 unclassified",
        "region": region if region in VALID_REGIONS else "E southern",
        "people": people if people in {"none", "present", "prominent"} else "",
    }


async def _draft_what_was_taken(
    ctx: AgentContext,
    system_full: str,
    description: str,
    images: list[tuple[str, str]] | None = None,
) -> str:
    prompt = (
        "Write the WHAT WAS TAKEN line for this caption card. One sentence, "
        "house voice: lower-case, concrete, names the economic extraction — "
        "never weather, never a monster in place of the real cause. "
        "Output the sentence only.\n\nMaterial:\n" + description
    )
    return (
        await ctx.llm.complete(STANDARD, system_full, prompt, max_tokens=200, images=images)
    )[:1900]


async def check_duplicate(ctx: AgentContext, source_url: str) -> str | None:
    """Existing row URL if this Source URL is already filed — checks SQLite
    first, then a live Notion query. Never file the same URL twice."""
    cached = ctx.memory.dedupe_get(f"url:{source_url}")
    if cached:
        return cached
    existing = await ctx.notion.find_by_url("Source URL", source_url)
    if existing:
        page_url = existing.get("url", "")
        ctx.memory.dedupe_set(f"url:{source_url}", page_url)
        return page_url
    return None


async def file_source(
    ctx: AgentContext,
    system_full: str,
    raw: str,
    filed_by: str = "the bot",
) -> FilingResult:
    """Full intake for a loc.gov URL or free text."""
    urls = loc.extract_loc_urls(raw)
    source_url = urls[0] if urls else ""

    title, date, photographer, loc_lot, notes = raw.strip()[:200], "", "", "", ""
    description = raw.strip()
    item: loc.LocItem | None = None
    vision_images: list[tuple[str, str]] = []

    if source_url:
        duplicate_url = await check_duplicate(ctx, source_url)
        if duplicate_url:
            return FilingResult(
                ok=True,
                duplicate=True,
                page_url=duplicate_url,
                message=f"already in the file. nothing is filed twice.\n{duplicate_url}",
            )
        try:
            item = await loc.fetch_item(source_url)
        except Exception as exc:  # network or parse failure — report, don't invent
            reason = str(exc) or type(exc).__name__
            log_event(ctx.log, "loc_fetch_failed", url=source_url, error=reason)
            return FilingResult(
                ok=False, message=f"could not pull the record from loc.gov ({reason})."
            )
        title = item.title or title
        date = item.date
        photographer = item.photographer
        loc_lot = item.loc_lot
        notes = " · ".join(item.notes)
        description = (
            f"title: {item.title}\ndate: {item.date}\nphotographer: {item.photographer}\n"
            f"lot/negative: {item.loc_lot}\nnotes: {notes}\nsource: {source_url}"
        )
        # let the models see the photograph itself, not just the caption
        try:
            downloaded = await loc.download_image(
                item.best_image(max_width=1200), max_bytes=MAX_VISION_BYTES
            )
            if downloaded:
                data, content_type = downloaded
                vision_images = [(content_type, base64.standard_b64encode(data).decode())]
        except Exception as exc:
            log_event(ctx.log, "vision_image_failed", url=source_url, error=str(exc))

    verdict = await run_taking_test(ctx, description, images=vision_images)
    test = verdict["taking_test"]
    if verdict["people"] == "prominent":
        flag = "people prominent in frame — print the places, not the people."
        notes = f"{notes} · {flag}" if notes else flag

    if test == "pass":
        taken = await _draft_what_was_taken(ctx, system_full, description, images=vision_images)
        status = "filed"
    elif test == "fail weather":
        # refused, never deleted — the office keeps everything
        taken = "nothing was taken. weather did this."
        status = "refused"
    else:
        taken = ""
        status = "filed"

    properties = {
        "Title": prop_title(title),
        "Class": prop_select(verdict["class"]),
        "Region": prop_select(verdict["region"]),
        "What Was Taken": prop_rich_text(taken),
        "Status": prop_select(status),
        "Taking Test": prop_select(test),
        "Chapter": prop_select("unassigned"),
        "Photographer": prop_rich_text(photographer),
        "Source Date": prop_rich_text(date),
        "LOC LOT": prop_rich_text(loc_lot),
        "Filed By": prop_select(filed_by),
        "Notes": prop_rich_text(notes),
    }
    if source_url:
        properties["Source URL"] = prop_url(source_url)

    page = await ctx.notion.create_row(properties)
    page_url = page.get("url", "")
    if source_url:
        ctx.memory.dedupe_set(f"url:{source_url}", page_url)
    log_event(ctx.log, "row_filed", title=title, status=status, test=test, page=page_url)

    # enrichment is best-effort: the row is already filed, so never fail on it
    memo = ""
    try:
        memo = await _enrich_page(
            ctx, system_full, page.get("id", ""), item, description, vision_images
        )
    except Exception as exc:
        log_event(ctx.log, "enrich_failed", page=page_url, error=str(exc))

    card = _caption_card(
        title, date, photographer, verdict["class"], verdict["region"],
        test, taken, loc_lot, status, filed_by, page_url,
    )
    if memo:
        card += f"\n> {memo}"
    return FilingResult(ok=True, caption_card=card, page_url=page_url)


async def _enrich_page(
    ctx: AgentContext,
    system_full: str,
    page_id: str,
    item: loc.LocItem | None,
    description: str,
    vision_images: list[tuple[str, str]],
) -> str:
    """Attach the plate (Plate property + page cover + body image) and append a
    lore memo written in the estate's voice. Returns the memo text."""
    if not page_id:
        return ""

    if item and item.image_urls:
        best_url = item.best_image()
        downloaded = await loc.download_image(best_url)
        if downloaded:
            data, content_type = downloaded
            upload_id = await ctx.notion.upload_file(
                f"{item.item_id}.jpg", data, content_type
            )
            if upload_id:
                await ctx.notion.update_page(
                    page_id,
                    properties={"Plate": prop_files_upload(f"{item.item_id}.jpg", upload_id)},
                    cover={"type": "external", "external": {"url": best_url.split("#")[0]}},
                )

    # canon-tier models think before writing; max_tokens covers thinking + text,
    # so give real headroom or the memo comes back empty
    memo = await ctx.llm.complete(
        CANON,
        system_full,
        LORE_MEMO_PROMPT.format(description=description),
        max_tokens=2000,
        images=vision_images or None,
    )
    memo = memo[:900]

    # the memo's suggested chapter goes in its own property; Chapter itself
    # stays unassigned until a human confirms
    chapter_match = re.search(r"suggested chapter:\s*(.+)", memo)
    if chapter_match:
        suggestion = chapter_match.group(1).strip().rstrip(".")
        if suggestion in VALID_CHAPTERS:
            await ctx.notion.update_page(
                page_id, properties={"Suggested Chapter": prop_select(suggestion)}
            )

    if memo:
        blocks: list[dict] = []
        if item and item.image_urls:
            blocks.append(
                {
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": item.best_image().split("#")[0]},
                    },
                }
            )
        blocks.append(
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"lore memo — {memo}"[:1990]}}]
                },
            }
        )
        await ctx.notion.append_blocks(page_id, blocks)
    return memo


async def file_tip(ctx: AgentContext, tip: str, reporter: str) -> FilingResult:
    """Tip line: a strange place reported by a fan, kept as an untitled
    harbor-contract candidate. Never opened until the submission-license
    paragraph exists — gating lives in config, not here."""
    properties = {
        "Title": prop_title(tip.strip()[:200]),
        "Class": prop_select(".0000 unclassified"),
        "Region": prop_select("E coastal annex"),
        "Status": prop_select("untitled"),
        "Taking Test": prop_select("pending"),
        "Chapter": prop_select("unassigned"),
        "Suggested Chapter": prop_select("003 the harbor answers"),
        "Filed By": prop_select("the bot"),
        "Notes": prop_rich_text(
            f"tip line submission by {reporter} · harbor contract candidate"
        ),
    }
    page = await ctx.notion.create_row(properties)
    page_url = page.get("url", "")
    log_event(ctx.log, "tip_filed", reporter=reporter, tip=tip[:80], page=page_url)
    return FilingResult(
        ok=True,
        page_url=page_url,
        message="the office has your report. if the place is real, a contract may follow.",
    )


async def file_untitled(ctx: AgentContext, idea: str, filed_by: str = "the bot") -> FilingResult:
    """Quick capture — zero friction, everything kept. No LLM involved."""
    properties = {
        "Title": prop_title(idea.strip()[:200]),
        "Class": prop_select(".0000 unclassified"),
        "Region": prop_select("E southern"),
        "Status": prop_select("untitled"),
        "Taking Test": prop_select("pending"),
        "Chapter": prop_select("unassigned"),
        "Filed By": prop_select(filed_by),
        "Notes": prop_rich_text(idea.strip()[:2000] if len(idea.strip()) > 200 else ""),
    }
    page = await ctx.notion.create_row(properties)
    page_url = page.get("url", "")
    log_event(ctx.log, "row_filed", title=idea[:80], status="untitled", page=page_url)
    return FilingResult(ok=True, page_url=page_url, message=f"kept. status untitled.\n{page_url}")
