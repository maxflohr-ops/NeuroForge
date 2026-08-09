"""Airtable adapter — REST over the official API, honoring the env proxy.

The interface was defined with agent 001 so future agents code against a
stable surface. Agent 002 (velo, the Florra ops agent) is the first user, so
the real implementation lands here. Any agent that needs Airtable takes this
via AgentContext; core never imports agents.

Auth: AIRTABLE_API_KEY (a personal access token). Read + write scopes on the
bases the token is shared with.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

import aiohttp

API_ROOT = "https://api.airtable.com/v0"


class AirtableAdapter(Protocol):
    """Contract every Airtable implementation must satisfy."""

    async def list_records(
        self, base_id: str, table: str, formula: str | None = None, max_records: int = 100
    ) -> list[dict[str, Any]]: ...

    async def get_record(self, base_id: str, table: str, record_id: str) -> dict[str, Any]: ...

    async def create_record(
        self, base_id: str, table: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def update_record(
        self, base_id: str, table: str, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...


class Airtable:
    """Real Airtable REST client. Async, no third-party SDK."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("AIRTABLE_API_KEY", "")
        if not self.token:
            raise RuntimeError("AIRTABLE_API_KEY not set")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def list_records(
        self,
        base_id: str,
        table: str,
        formula: str | None = None,
        max_records: int = 100,
        fields: list[str] | None = None,
        sort: list[dict[str, str]] | None = None,
        view: str | None = None,
    ) -> list[dict[str, Any]]:
        """Records as [{id, fields, createdTime}]. Paginates until max_records."""
        params: list[tuple[str, str]] = [("pageSize", "100")]
        if formula:
            params.append(("filterByFormula", formula))
        if view:
            params.append(("view", view))
        for f in fields or []:
            params.append(("fields[]", f))
        for i, s in enumerate(sort or []):
            params.append((f"sort[{i}][field]", s["field"]))
            params.append((f"sort[{i}][direction]", s.get("direction", "asc")))

        out: list[dict[str, Any]] = []
        offset: str | None = None
        async with aiohttp.ClientSession() as session:
            while len(out) < max_records:
                page_params = list(params)
                if offset:
                    page_params.append(("offset", offset))
                async with session.get(
                    f"{API_ROOT}/{base_id}/{table}",
                    headers=self._headers(),
                    params=page_params,
                    timeout=aiohttp.ClientTimeout(total=40),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                out.extend(data.get("records", []))
                offset = data.get("offset")
                if not offset:
                    break
        return out[:max_records]

    async def get_record(self, base_id: str, table: str, record_id: str) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_ROOT}/{base_id}/{table}/{record_id}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def create_record(
        self, base_id: str, table: str, fields: dict[str, Any], typecast: bool = True
    ) -> dict[str, Any]:
        """Create one row. typecast lets select strings map to existing options."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_ROOT}/{base_id}/{table}",
                headers=self._headers(),
                json={"fields": fields, "typecast": typecast},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status >= 400:
                    raise RuntimeError(f"airtable create failed ({response.status}): {await response.text()}")
                return await response.json()

    async def update_record(
        self,
        base_id: str,
        table: str,
        record_id: str,
        fields: dict[str, Any],
        typecast: bool = True,
    ) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{API_ROOT}/{base_id}/{table}/{record_id}",
                headers=self._headers(),
                json={"fields": fields, "typecast": typecast},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status >= 400:
                    raise RuntimeError(f"airtable update failed ({response.status}): {await response.text()}")
                return await response.json()

    @staticmethod
    def val(record: dict, field: str, default: str = "") -> str:
        """Best-effort plain read of a field. Selects come back as objects or
        arrays of objects; links/attachments as arrays."""
        v = record.get("fields", {}).get(field, default)
        if isinstance(v, dict):
            return str(v.get("name", v.get("id", "")))
        if isinstance(v, list):
            parts = []
            for item in v:
                if isinstance(item, dict):
                    parts.append(str(item.get("name", item.get("id", ""))))
                else:
                    parts.append(str(item))
            return ", ".join(parts)
        return str(v) if v not in (None, "") else default


class NotImplementedAirtable:
    """Bound in AgentContext when AIRTABLE_API_KEY is absent — agents that
    don't use Airtable never trip this; agents that do get a clear message."""

    def __getattr__(self, name: str):
        raise NotImplementedError(
            "Airtable is not configured — set AIRTABLE_API_KEY in the environment "
            "for agents that use it (e.g. velo, the Florra ops agent)."
        )
