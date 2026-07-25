"""Notion API adapter (databases/data sources + pages).

Uses the 2025-09-03 API version, which addresses databases through data
sources. All fleet lore data lives in Notion; this adapter is the only
place that talks to it.

Nothing is ever deleted or archived through this adapter — by design it
exposes no delete. The office keeps everything.
"""

from __future__ import annotations

from typing import Any

from notion_client import AsyncClient, Client

NOTION_VERSION = "2025-09-03"


# -- property payload builders ------------------------------------------


def prop_title(text: str) -> dict:
    return {"title": [{"text": {"content": text[:2000]}}]}


def prop_rich_text(text: str) -> dict:
    return {"rich_text": [{"text": {"content": text[:2000]}}]} if text else {"rich_text": []}


def prop_select(name: str) -> dict:
    return {"select": {"name": name}}


def prop_url(url: str) -> dict:
    return {"url": url or None}


class NotionAdapter:
    def __init__(self, token: str, data_source_id: str):
        self.client = AsyncClient(auth=token, notion_version=NOTION_VERSION)
        self.data_source_id = data_source_id

    async def query(
        self,
        filter: dict | None = None,
        sorts: list[dict] | None = None,
        page_size: int = 25,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"page_size": page_size}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        response = await self.client.request(
            path=f"data_sources/{self.data_source_id}/query",
            method="POST",
            body=body,
        )
        return response.get("results", [])

    async def find_by_url(self, property_name: str, url: str) -> dict | None:
        results = await self.query(
            filter={"property": property_name, "url": {"equals": url}}, page_size=1
        )
        return results[0] if results else None

    async def create_row(self, properties: dict[str, Any]) -> dict:
        return await self.client.pages.create(
            parent={"type": "data_source_id", "data_source_id": self.data_source_id},
            properties=properties,
        )

    @staticmethod
    def plain_text(page: dict, property_name: str) -> str:
        """Best-effort plain-text read of a page property."""
        prop = page.get("properties", {}).get(property_name, {})
        kind = prop.get("type")
        if kind == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
        if kind == "rich_text":
            return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
        if kind == "select":
            return (prop.get("select") or {}).get("name", "")
        if kind == "url":
            return prop.get("url") or ""
        if kind == "unique_id":
            uid = prop.get("unique_id") or {}
            prefix = uid.get("prefix") or ""
            number = uid.get("number")
            return f"{prefix}-{number}" if number is not None else ""
        if kind == "created_time":
            return prop.get("created_time") or ""
        return ""


# -- bible page -> markdown (sync; used by scripts/sync_bible.py) --------


def fetch_page_markdown(token: str, page_id: str) -> str:
    client = Client(auth=token, notion_version=NOTION_VERSION)
    lines: list[str] = []
    _walk_blocks(client, page_id, lines, depth=0)
    return "\n".join(lines).strip() + "\n"


def _walk_blocks(client: Client, block_id: str, lines: list[str], depth: int) -> None:
    cursor = None
    while True:
        response = client.blocks.children.list(block_id=block_id, start_cursor=cursor)
        for block in response.get("results", []):
            _render_block(client, block, lines, depth)
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")


def _rt(block_payload: dict) -> str:
    return "".join(t.get("plain_text", "") for t in block_payload.get("rich_text", []))


def _render_block(client: Client, block: dict, lines: list[str], depth: int) -> None:
    kind = block.get("type", "")
    payload = block.get(kind, {}) or {}
    indent = "  " * depth
    if kind == "paragraph":
        text = _rt(payload)
        lines.append(f"{indent}{text}" if text else "")
    elif kind in ("heading_1", "heading_2", "heading_3"):
        hashes = "#" * int(kind[-1])
        lines.append(f"\n{hashes} {_rt(payload)}")
    elif kind in ("bulleted_list_item", "toggle"):
        lines.append(f"{indent}- {_rt(payload)}")
    elif kind == "numbered_list_item":
        lines.append(f"{indent}1. {_rt(payload)}")
    elif kind == "to_do":
        mark = "x" if payload.get("checked") else " "
        lines.append(f"{indent}- [{mark}] {_rt(payload)}")
    elif kind == "quote":
        lines.append(f"{indent}> {_rt(payload)}")
    elif kind == "callout":
        lines.append(f"{indent}> {_rt(payload)}")
    elif kind == "code":
        lines.append(f"{indent}```")
        lines.append(_rt(payload))
        lines.append(f"{indent}```")
    elif kind == "divider":
        lines.append("\n---")
    elif kind == "table_row":
        cells = payload.get("cells", [])
        row = " | ".join("".join(t.get("plain_text", "") for t in cell) for cell in cells)
        lines.append(f"{indent}| {row} |")
    elif kind in ("child_database", "child_page"):
        lines.append(f"{indent}[{kind}: {payload.get('title', '')}]")
        return  # do not descend into child pages/databases
    # images/embeds/etc. are skipped — the bible text is what matters

    if block.get("has_children") and kind not in ("child_page", "child_database"):
        _walk_blocks(client, block["id"], lines, depth + 1)
