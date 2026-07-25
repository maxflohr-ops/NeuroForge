"""Airtable adapter — interface only, for future agents (002 velo-scout etc.).

Nothing in agent 001 uses Airtable. The interface is defined now so future
agents code against a stable surface and core/ never needs restructuring.
"""

from __future__ import annotations

from typing import Any, Protocol


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


class NotImplementedAirtable:
    """Stub bound in AgentContext until a real implementation ships with agent 002."""

    def __getattr__(self, name: str):
        raise NotImplementedError(
            "Airtable adapter is a stub — implement core/airtable.py when the first "
            "Airtable-using agent (velo-scout) is built."
        )
