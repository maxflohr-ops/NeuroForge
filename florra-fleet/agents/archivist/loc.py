"""Library of Congress item fetcher.

Given a loc.gov item URL, pulls https://www.loc.gov/item/<id>/?fo=json and
extracts the fields THE FILE cares about. Best-effort: the FSA records vary,
and a missing field is filed as empty, never invented.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import aiohttp

LOC_URL_RE = re.compile(
    r"https?://(?:www\.)?loc\.gov/(?:item|pictures/item)/([^/?#\s>]+)", re.IGNORECASE
)


@dataclass
class LocItem:
    item_id: str
    url: str  # canonical item url — the dedupe key
    title: str = ""
    date: str = ""
    photographer: str = ""
    loc_lot: str = ""  # e.g. "LOT 1723 · LC-USF33-030272-M1"
    notes: list[str] = field(default_factory=list)


def extract_loc_urls(text: str) -> list[str]:
    """Canonical item URLs for every loc.gov item link in the text, deduped."""
    seen: list[str] = []
    for match in LOC_URL_RE.finditer(text or ""):
        canonical = f"https://www.loc.gov/item/{match.group(1).rstrip('/')}/"
        if canonical not in seen:
            seen.append(canonical)
    return seen


def _first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value else ""


async def fetch_item(item_url: str) -> LocItem:
    match = LOC_URL_RE.search(item_url)
    if not match:
        raise ValueError(f"not a loc.gov item url: {item_url}")
    item_id = match.group(1).rstrip("/")
    canonical = f"https://www.loc.gov/item/{item_id}/"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{canonical}?fo=json", timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            response.raise_for_status()
            data = await response.json()

    item = data.get("item", {}) or {}
    result = LocItem(item_id=item_id, url=canonical)
    result.title = _first(item.get("title"))
    result.date = _first(item.get("date") or item.get("dates"))

    contributors = item.get("contributor_names") or item.get("creators") or []
    if contributors and isinstance(contributors[0], dict):
        contributors = [c.get("title", "") for c in contributors]
    result.photographer = ", ".join(str(c) for c in contributors if c)[:200]

    call_number = _first(item.get("call_number") or item.get("reproduction_number"))
    # normalize e.g. "LC-USF33- 030272-M1 [P&P] LOT 1723 (…)" -> "LC-USF33-030272-M1"
    negative = re.split(r"\[|\(", call_number)[0]
    negative = re.sub(r"\bLOT\s*\d+\b", "", negative)
    negative = re.sub(r"-\s+", "-", negative).strip(" ·,;")
    # LOT number often hides in miscellaneous fields; scan the record for it
    lot_match = re.search(r"\bLOT\s*(\d+)\b", json.dumps(item))
    lot = f"LOT {lot_match.group(1)}" if lot_match else ""
    result.loc_lot = " · ".join(part for part in (lot, negative) if part)

    medium = _first(item.get("medium"))
    if medium:
        result.notes.append(medium)
    return result
