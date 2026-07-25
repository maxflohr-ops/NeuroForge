#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Catalog Pins (BANDERSNATCH)
======================================================
Builds a publisher-ready pin package straight from the county's own
material — no downloads, no API keys, no Claude calls:

  1. the holdings — every product in the live Shopify catalog
     (public products.json), one pin per product photo, linking to
     the product page
  2. the county — the FSA plates mounted on bandersnatch.world/history.html,
     linking to the timeline

Captions are deterministic clerk voice, built from the product's own
description. Canon holds: no "shop now", no urgency, never explain.

Usage:
    python pinterest_catalog_pins.py                          # full package
    python pinterest_catalog_pins.py --holdings-board <ID> --county-board <ID>
    python pinterest_catalog_pins.py --dry-run                # print, don't save

The output pin-package-{DATE}.json feeds pinterest_publisher.py directly.
Pinterest board IDs are required for publishing — pass them here or set
PINTEREST_BOARD_ID_HOLDINGS / PINTEREST_BOARD_ID_COUNTY once the
Bandersnatch Pinterest account and boards exist.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

from pinterest_config import BASE_HASHTAGS, NICHE_HASHTAGS, SITE, STORE

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "output" / "pinterest"

USER_AGENT = "bandersnatch-office-bot/2.0 (+https://bandersnatch.world)"

# The FSA plates mounted on the history page. Mirrors history.html — when a
# new plate is mounted there, add it here (or automate against the Notion
# Historical Section Holdings sweep).
FSA_PLATES = [
    {
        "image_url": "https://tile.loc.gov/storage-services/service/pnp/fsa/8c52000/8c52400/8c52414v.jpg",
        "title": "Bandersnatch County, 1935 — the crossroads store",
        "description": (
            "crossroads store, 1935. walker evans, for the farm security "
            "administration. what was taken: the porch, the signage, the "
            "man who would not give his name. the county has been "
            "photographed since 1935. the plates are in the file. "
            "bandersnatch.world/history.html"
        ),
        "alt_text": "Black and white 1935 photograph of a rural crossroads general store with a covered porch, from the Farm Security Administration archive.",
    },
    {
        "image_url": "https://tile.loc.gov/storage-services/service/pnp/fsa/8a39000/8a39600/8a39681v.jpg",
        "title": "Bandersnatch County, 1938 — farmhouse at the county line",
        "description": (
            "farmhouse at the county line, 1938. marion post wolcott, for "
            "the farm security administration. what was taken: the house, "
            "the fence, the weather. nothing else would sit still. "
            "the full timeline of the county, 1935–1945: "
            "bandersnatch.world/history.html"
        ),
        "alt_text": "Black and white 1938 photograph of a wooden farmhouse behind a fence under a heavy sky, from the Farm Security Administration archive.",
    },
    {
        "image_url": "https://tile.loc.gov/storage-services/service/pnp/fsa/8b19000/8b19700/8b19773v.jpg",
        "title": "Bandersnatch County, 1939 — church interior, empty",
        "description": (
            "church interior, empty, 1939. arthur rothstein, for the farm "
            "security administration. what was taken: the pews, the light, "
            "the quiet. the congregation is not in the file. "
            "bandersnatch.world/history.html"
        ),
        "alt_text": "Black and white 1939 photograph of an empty rural church interior with wooden pews lit by a side window, from the Farm Security Administration archive.",
    },
]


def strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&#39;", "'").replace("&rsquo;", "'")
        .replace("&quot;", '"').replace("&ldquo;", '"').replace("&rdquo;", '"')
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def first_sentence(text: str) -> str:
    m = re.split(r"(?<=\.)\s+", text or "", maxsplit=1)[0]
    return (m[:157] + "…") if len(m) > 160 else m


def fetch_catalog() -> list[dict]:
    """Pull the live holdings from the store's public products.json,
    backing off on Shopify rate limits (429/430)."""
    url = f"{STORE}/products.json?limit=250"
    resp = None
    for attempt in range(1, 4):
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.ok:
            break
        if resp.status_code in (429, 430):
            wait = attempt * 20
            print(f"  catalog: HTTP {resp.status_code}, backing off {wait}s")
            time.sleep(wait)
            continue
        break
    if resp is None or not resp.ok:
        raise RuntimeError(f"catalog fetch failed: HTTP {resp.status_code if resp else '?'}")
    products = resp.json().get("products", [])
    return [
        {
            "title": p["title"],
            "handle": p["handle"],
            "url": f"{STORE}/products/{p['handle']}",
            "description": strip_html(p.get("body_html", "")),
            "price": (p.get("variants") or [{}])[0].get("price"),
            "sizes": [v.get("title") for v in p.get("variants", [])],
            "images": [i["src"] for i in p.get("images", [])],
        }
        for p in products
    ]


def build_holding_pins(catalog: list[dict], board_id: str, all_images: bool) -> list[dict]:
    hashtags = (BASE_HASHTAGS + NICHE_HASHTAGS["gothic-fashion"])[:12]
    pins = []
    for product in catalog:
        epigraph = first_sentence(product["description"])
        description = (
            f"{epigraph} {product['title'].lower()}. screen printed in an "
            f"edition of 24, numbered by hand, sealed in wax. when the "
            f"edition is gone it is gone — the office does not restock. "
            f"the full file: bandersnatch.world"
        )[:500]
        images = product["images"] if all_images else product["images"][:1]
        for img_idx, image_url in enumerate(images, start=1):
            suffix = f" — plate {img_idx}" if all_images and len(images) > 1 else ""
            pins.append(
                {
                    "source_file": None,
                    "board_id": board_id,
                    "board_name": "the file",
                    "title": f"{product['title']} — southern gothic screen print, edition of 24{suffix}"[:100],
                    "description": description,
                    "hashtags": hashtags,
                    "link": product["url"],
                    "destination": "the store",
                    "alt_text": (
                        f"Screen printed garment from BANDERSNATCH, "
                        f"{product['title']}, limited edition of 24, product photograph."
                    )[:500],
                    "image_url": image_url,
                    "niche": "gothic-fashion",
                    "mood": "store",
                }
            )
    return pins


def build_county_pins(board_id: str) -> list[dict]:
    hashtags = (BASE_HASHTAGS + NICHE_HASHTAGS["vintage-photography"])[:12]
    return [
        {
            "source_file": None,
            "board_id": board_id,
            "board_name": "the county, 1935–1945",
            "title": plate["title"][:100],
            "description": plate["description"][:500],
            "hashtags": hashtags,
            "link": f"{SITE}/history.html",
            "destination": "the county, 1935–1945",
            "alt_text": plate["alt_text"][:500],
            "image_url": plate["image_url"],
            "niche": "vintage-photography",
            "mood": "county",
        }
        for plate in FSA_PLATES
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Build a Pinterest pin package from the live Bandersnatch catalog and FSA plates"
    )
    parser.add_argument(
        "--holdings-board",
        default=os.environ.get("PINTEREST_BOARD_ID_HOLDINGS", ""),
        help="Pinterest board ID for product pins (env: PINTEREST_BOARD_ID_HOLDINGS)",
    )
    parser.add_argument(
        "--county-board",
        default=os.environ.get("PINTEREST_BOARD_ID_COUNTY", ""),
        help="Pinterest board ID for FSA plate pins (env: PINTEREST_BOARD_ID_COUNTY)",
    )
    parser.add_argument(
        "--all-images",
        action="store_true",
        help="One pin per product photo instead of one per product",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the pin package (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the package instead of saving"
    )
    args = parser.parse_args()

    print("  pulling the live catalog...")
    catalog = fetch_catalog()
    print(f"  {len(catalog)} holdings in the file")

    pins = build_holding_pins(catalog, args.holdings_board, args.all_images)
    pins += build_county_pins(args.county_board)

    package = {
        "generated": date.today().isoformat(),
        "source": "pinterest_catalog_pins",
        "total_pins": len(pins),
        "pins": pins,
    }

    if not args.holdings_board or not args.county_board:
        print(
            "  NOTE: board IDs are empty — the publisher will reject these pins.\n"
            "  Create boards on the Bandersnatch Pinterest account, then set\n"
            "  PINTEREST_BOARD_ID_HOLDINGS and PINTEREST_BOARD_ID_COUNTY."
        )

    if args.dry_run:
        print(json.dumps(package, indent=2, ensure_ascii=False))
        print(f"\n  {len(pins)} pin(s) would be packaged.")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"pin-package-{date.today().isoformat()}.json"
    out_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  package saved: {out_path}")
    print(f"  next: python pinterest_publisher.py --package {out_path}")


if __name__ == "__main__":
    main()
