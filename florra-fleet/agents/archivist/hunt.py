"""/hunt — scout the LOC photo archive from Discord.

Searches loc.gov, pre-screens candidates against the Taking Test on the
cheap tier, and returns the best picks with thumbnails. Nothing is filed —
hunting and filing are separate acts.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

from core.context import AgentContext
from core.llm import CLASSIFY

from agents.archivist import filing, loc

SEARCH_URL = "https://www.loc.gov/photos/?q={query}&fo=json&c={count}"

PRESCREEN_SYSTEM = """You are the scouting clerk of a photo archive. You are \
given numbered photo captions from the 1930s-40s FSA/OWI archive. For each, \
judge the Taking Test from the caption alone:
- "pass": something was TAKEN — economic extraction (foreclosure, abandonment \
from collapsed trade, eroded cash-cropped land, dead mine/mill towns, closed \
storefronts).
- "fail weather": the damage is weather alone (hurricane, flood, fire, winter).
- "pending": neither, or cannot tell.
Output ONLY JSON: {"verdicts": [{"index": <n>, "verdict": "...", "reason": \
"<one short lower-case clause>"}]} — one entry per candidate."""


@dataclass
class HuntPick:
    title: str
    date: str
    item_url: str
    thumbnail: str
    verdict: str
    reason: str
    already_filed: bool = False


async def search_loc(query: str, count: int = 12) -> list[dict]:
    url = SEARCH_URL.format(query=quote(query), count=count)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            data = await response.json()
    results = []
    for entry in data.get("results", []):
        item_url = str(entry.get("id", ""))
        if "/item/" not in item_url:
            continue
        # bias toward the FSA/OWI collections when the result declares them
        partof = " ".join(str(p) for p in entry.get("partof", [])).lower()
        results.append(
            {
                "title": str(entry.get("title", ""))[:150],
                "date": str(entry.get("date", "") or ""),
                "item_url": item_url.replace("http://", "https://"),
                "thumbnail": (entry.get("image_url") or [""])[0],
                "fsa": "farm security administration" in partof or "fsa" in partof,
            }
        )
    fsa_results = [r for r in results if r["fsa"]]
    return fsa_results or results


async def hunt(ctx: AgentContext, query: str, max_picks: int = 5) -> list[HuntPick]:
    candidates = await search_loc(query)
    if not candidates:
        return []

    listing = "\n".join(
        f"{i}. {c['title']} ({c['date']})" for i, c in enumerate(candidates)
    )
    parsed = await ctx.llm.complete_json(
        CLASSIFY, PRESCREEN_SYSTEM, f"Candidates:\n{listing}", max_tokens=800
    )
    verdicts = {}
    for entry in (parsed or {}).get("verdicts", []):
        try:
            verdicts[int(entry.get("index"))] = (
                str(entry.get("verdict", "pending")),
                str(entry.get("reason", ""))[:150],
            )
        except (TypeError, ValueError):
            continue

    picks: list[HuntPick] = []
    order = {"pass": 0, "pending": 1, "fail weather": 2}
    ranked = sorted(
        range(len(candidates)),
        key=lambda i: order.get(verdicts.get(i, ("pending", ""))[0], 1),
    )
    for i in ranked[: max_picks * 2]:
        c = candidates[i]
        verdict, reason = verdicts.get(i, ("pending", ""))
        canonical = loc.extract_loc_urls(c["item_url"])
        source_url = canonical[0] if canonical else c["item_url"]
        already = bool(await filing.check_duplicate(ctx, source_url))
        picks.append(
            HuntPick(
                title=c["title"],
                date=c["date"],
                item_url=source_url,
                thumbnail=c["thumbnail"],
                verdict=verdict,
                reason=reason,
                already_filed=already,
            )
        )
        if len(picks) >= max_picks:
            break
    return picks
