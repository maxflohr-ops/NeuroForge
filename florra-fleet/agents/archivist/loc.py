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
    image_urls: list[str] = field(default_factory=list)  # jpeg derivatives, various sizes

    def best_image(self, max_width: int | None = None) -> str:
        """Largest jpeg derivative, optionally capped by width (for vision calls)."""
        best_url, best_width = "", -1
        for url in self.image_urls:
            width_match = re.search(r"[#&]w=(\d+)", url)
            width = int(width_match.group(1)) if width_match else 0
            if max_width is not None and width > max_width:
                continue
            if width > best_width:
                best_url, best_width = url, width
        return best_url


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

    data = None
    last_error: Exception | None = None
    for attempt in range(2):  # loc.gov can be slow; one retry
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{canonical}?fo=json", timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            break
        except Exception as exc:
            last_error = exc
    if data is None:
        raise RuntimeError(
            f"loc.gov did not answer ({type(last_error).__name__})"
        ) from last_error

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

    image_urls = list(item.get("image_url") or [])
    if not image_urls:
        for resource in data.get("resources", []) or []:
            if resource.get("image"):
                image_urls.append(resource["image"])
    if not image_urls:
        # P&P derivative naming: <id>_150px.jpg thumb implies <id>r.jpg (~640px)
        # and <id>v.jpg (~1024px) siblings
        thumb = str(item.get("thumb_gallery") or "")
        if thumb.endswith("_150px.jpg"):
            base = thumb[: -len("_150px.jpg")]
            image_urls = [f"{base}r.jpg#w=640", f"{base}v.jpg#w=1024"]
    result.image_urls = [u for u in image_urls if isinstance(u, str)]
    return result


async def download_image(url: str, max_bytes: int = 19_000_000) -> tuple[bytes, str] | None:
    """Fetch a jpeg derivative. Returns (bytes, content_type) or None."""
    if not url:
        return None
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
            if response.status >= 400:
                return None
            data = await response.read()
    if not data or len(data) > max_bytes:
        return None
    content_type = "image/gif" if data[:3] == b"GIF" else "image/jpeg"
    return data, content_type
