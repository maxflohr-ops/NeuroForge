#!/usr/bin/env python3
"""
Fleet Memory
============
An optional link to a TencentDB Agent Memory server (MIT, self-hosted — despite
the name it needs no Tencent Cloud account, only Docker and an OpenAI-compatible
LLM endpoint of your choosing).

What it buys this fleet. Every mission currently starts from nothing. Six of the
ten objectives in the book are adjacent — three of them are the same faculty
voice on overlapping ground — and the Research Agent rediscovers that ground
each time. With memory attached, what a previous mission learned, and what QA
objected to, is handed to the next one as context.

Three properties this module holds to, because the fleet runs unattended:

  * **Off by default.** No MEMORY_ENDPOINT, no behaviour change at all.
  * **Fail open.** A memory server that is down, slow or broken must never stop
    a mission. Every call swallows its errors and returns nothing useful
    instead of raising.
  * **No new dependency.** The official SDK is fine, but the commander stays
    standard library; this speaks the v2 HTTP protocol directly.

    POST {endpoint}/v2/conversation/add   record what happened
    POST {endpoint}/v2/atomic/search      recall what is relevant
    POST {endpoint}/v2/core/read          the fleet's standing profile
    headers: Authorization: Bearer <key>, x-tdai-service-id: <space>
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_TIMEOUT = 4.0          # a mission must not wait on memory
MAX_RECALL_CHARS = 3500        # what the pipeline will accept as context
RECALL_LIMIT = 6


class MemoryLink:
    """A thin, fail-open client. Disabled unless an endpoint is configured."""

    def __init__(self, endpoint: str | None = None, api_key: str = "",
                 service_id: str = "", agent_id: str = "florra-fleet",
                 timeout: float = DEFAULT_TIMEOUT,
                 on_error: Callable[[str], None] | None = None):
        self.endpoint = (endpoint or "").rstrip("/")
        self.api_key = api_key
        self.service_id = service_id
        self.agent_id = agent_id
        self.timeout = timeout
        self.on_error = on_error or (lambda message: None)
        self.failures = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None,
                 **kwargs: Any) -> "MemoryLink":
        env = os.environ if env is None else env
        try:
            timeout = float(env.get("MEMORY_TIMEOUT", DEFAULT_TIMEOUT))
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        return cls(
            endpoint=env.get("MEMORY_ENDPOINT", ""),
            api_key=env.get("MEMORY_API_KEY", ""),
            service_id=env.get("MEMORY_SERVICE_ID", ""),
            agent_id=env.get("MEMORY_AGENT_ID", "florra-fleet"),
            timeout=timeout,
            **kwargs,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint)

    # ── transport ─────────────────────────────────────────────────────────

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST and return the decoded body, or None on any failure at all."""
        if not self.enabled:
            return None

        body = json.dumps({**payload, "agent_id": self.agent_id}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}{path}", data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "x-tdai-service-id": self.service_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError, ValueError) as exc:
            # Memory is an enhancement. Losing it degrades the fleet's context;
            # it must never take the fleet down.
            self.failures += 1
            self.on_error(f"memory unavailable: {exc}")
            return None

    # ── operations ────────────────────────────────────────────────────────

    def recall(self, query: str, limit: int = RECALL_LIMIT) -> str:
        """Prior context relevant to this query, as a text block ('' if none)."""
        result = self._post("/v2/atomic/search", {"query": query, "limit": limit})
        if not isinstance(result, dict):
            return ""

        items = result.get("items")
        if not isinstance(items, list) or not items:
            return ""

        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            background = str(item.get("background") or "").strip()
            lines.append(f"- {content}" + (f" ({background})" if background else ""))

        if not lines:
            return ""

        block = "Prior work by this fleet on related topics:\n" + "\n".join(lines)
        return block[:MAX_RECALL_CHARS]

    def record(self, session_id: str, summary: str,
               detail: str = "") -> bool:
        """Write what a mission produced back to memory."""
        messages = [
            {"role": "user", "content": summary},
            {"role": "assistant", "content": detail or summary},
        ]
        result = self._post("/v2/conversation/add",
                            {"session_id": session_id, "messages": messages})
        return result is not None

    def profile(self) -> str:
        """The fleet's standing core memory, if the server has built one."""
        result = self._post("/v2/core/read", {})
        if not isinstance(result, dict):
            return ""
        return str(result.get("content") or "").strip()

    def health(self) -> bool:
        """True when the server answers. Never raises."""
        return self._post("/v2/atomic/search", {"query": "ping", "limit": 1}) is not None

    # ── reporting ─────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint or None,
            "service_id": self.service_id or None,
            "failures": self.failures,
        }


def mission_summary(topic: str, faculty: str, scores: dict[str, int],
                    outcome: str) -> str:
    """One line a future mission can actually use, not a metrics dump."""
    if scores:
        ranked = sorted(scores.items(), key=lambda pair: pair[1])
        weakest, weakest_score = ranked[0]
        strongest, strongest_score = ranked[-1]
        detail = (f"weakest stage {weakest} at {weakest_score}/50, "
                  f"strongest {strongest} at {strongest_score}/50")
    else:
        detail = "no QA scores recorded"
    return (f"Fleet ran '{topic}' in the voice of {faculty}. "
            f"Outcome: {outcome}. {detail}.")
