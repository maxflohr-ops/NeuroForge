"""The filing pipeline — shared by /file, /test file:true, and passive intake.

fetch -> dedupe -> taking test + classification (classify tier) ->
"What Was Taken" (standard tier, house voice) -> write to THE FILE ->
caption card.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.context import AgentContext
from core.llm import CLASSIFY, STANDARD
from core.log import log_event
from core.notion import prop_rich_text, prop_select, prop_title, prop_url

from agents.archivist import loc

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
hard winter — FAILS as "fail weather". If you cannot tell, the answer is \
"pending". Never guess.

Class numbers (pick exactly one string):
".3100 dwellings unoccupied", ".9026 organized gatherings", ".9100 churches", \
".9200 cemeteries", ".4000 land eroded", ".5000 commerce closed", \
".7000 roads and rail", ".8000 water and harbor", ".0000 unclassified"
Uncertain -> ".0000 unclassified".

Region: "E southern" (default; the county, inland, Appalachia, the South) or \
"E coastal annex" (harbors, coast, California, salt water).

JSON shape:
{"taking_test": "pass" | "fail weather" | "pending",
 "reason": "<one short lower-case sentence>",
 "class": "<one class string>",
 "region": "<one region string>"}"""


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


async def run_taking_test(ctx: AgentContext, description: str) -> dict:
    """Taking test + class + region in one classify-tier call. Uncertainty
    resolves to pending / .0000 — never a guess."""
    parsed = await ctx.llm.complete_json(
        CLASSIFY, CLASSIFY_SYSTEM, f"Material to classify:\n{description}", max_tokens=300
    )
    parsed = parsed or {}
    test = parsed.get("taking_test", "pending")
    class_ = parsed.get("class", ".0000 unclassified")
    region = parsed.get("region", "E southern")
    return {
        "taking_test": test if test in VALID_TEST else "pending",
        "reason": str(parsed.get("reason", ""))[:300],
        "class": class_ if class_ in VALID_CLASSES else ".0000 unclassified",
        "region": region if region in VALID_REGIONS else "E southern",
    }


async def _draft_what_was_taken(ctx: AgentContext, system_full: str, description: str) -> str:
    prompt = (
        "Write the WHAT WAS TAKEN line for this caption card. One sentence, "
        "house voice: lower-case, concrete, names the economic extraction — "
        "never weather, never a monster in place of the real cause. "
        "Output the sentence only.\n\nMaterial:\n" + description
    )
    return (await ctx.llm.complete(STANDARD, system_full, prompt, max_tokens=200))[:1900]


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
            log_event(ctx.log, "loc_fetch_failed", url=source_url, error=str(exc))
            return FilingResult(ok=False, message=f"could not pull the record from loc.gov ({exc}).")
        title = item.title or title
        date = item.date
        photographer = item.photographer
        loc_lot = item.loc_lot
        notes = " · ".join(item.notes)
        description = (
            f"title: {item.title}\ndate: {item.date}\nphotographer: {item.photographer}\n"
            f"lot/negative: {item.loc_lot}\nnotes: {notes}\nsource: {source_url}"
        )

    verdict = await run_taking_test(ctx, description)
    test = verdict["taking_test"]

    if test == "pass":
        taken = await _draft_what_was_taken(ctx, system_full, description)
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

    card = _caption_card(
        title, date, photographer, verdict["class"], verdict["region"],
        test, taken, loc_lot, status, filed_by, page_url,
    )
    return FilingResult(ok=True, caption_card=card, page_url=page_url)


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
