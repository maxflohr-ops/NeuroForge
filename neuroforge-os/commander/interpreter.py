#!/usr/bin/env python3
"""
Log Interpreter
===============
The existing agents already narrate themselves on stdout. Rather than rewrite
them to emit telemetry, the commander reads what they print and reconstructs
structured events from it — so the visual map stays live without any agent
having to know the commander exists.

Agents that want to say something the printed output cannot express can emit a
single line of the explicit protocol instead:

    NEUROFORGE_EVENT {"kind": "stage_start", "stage": "Voice pass"}

Interpretation is pure: feed a line, get events back. No I/O, no globals.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .registry import AGENTS, AGENTS_BY_ID

EVENT_PREFIX = "NEUROFORGE_EVENT"

LEVEL_ERROR = "error"
LEVEL_WARN = "warn"
LEVEL_SUCCESS = "success"
LEVEL_INFO = "info"

# Banner lines the pipeline prints when an agent takes over, e.g.
#   "🔬 RESEARCH AGENT — Starting"  /  "✍️  MANUSCRIPT AGENT — Chapter 1"
_BANNER = re.compile(
    r"^\s*\W*\s*(?P<name>[A-Z][A-Z0-9 ]*AGENT)\s*[—\-–:]\s*(?P<detail>.+?)\s*$"
)
# "  Calling: Research Agent"
_CALLING = re.compile(r"^\s*Calling:\s*(?P<label>.+?)\s*$")
# "  ✓ Saved: /app/output/topic/01_research_brief_2026....md"
_SAVED = re.compile(r"Saved:\s*(?P<path>\S.*?)\s*$")
# "✅ Research brief complete. QA Score: 42/50"
_SCORE_LABELLED = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z \-]{2,40}?)\s*(?:complete\.\s*QA Score:|:)?\s*"
    r"\b(?P<score>\d{1,2})\s*/\s*50\b"
)
_SCORE_ANY = re.compile(r"\b(?P<score>\d{1,2})\s*/\s*50\b")
# "  ↩ Resuming Research Brief from: 01_research_brief_2026....md"
_RESUME = re.compile(r"Resuming\s+(?P<label>.+?)\s+from:\s*(?P<path>\S+)")
# Orchestrator step markers: "1️⃣ Step 1: Syncing ..."
_STEP = re.compile(r"Step\s+(?P<num>\d+):\s*(?P<label>.+?)\s*$")

_ERROR_HINTS = re.compile(r"❌|\bTraceback\b|\bError\b|\bERROR\b|\bFailed\b|\bfailed\b")
_WARN_HINTS = re.compile(r"⚠|\bWarning\b|\bWARN\b|\bSkipping\b")
_SUCCESS_HINTS = re.compile(r"✅|✓")

# Map printed output back to a registry id, so the architecture map can light
# up the right node while a single pipeline process runs. Banners are checked
# first; aliases (QA content types, output-file prefixes) catch the lines that
# name an artifact rather than an agent — a resumed step, say.
_SIGNATURES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(spec.log_signature, re.IGNORECASE), spec.id)
    for spec in AGENTS
    if spec.log_signature
]

_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile("|".join(re.escape(alias) for alias in spec.aliases), re.IGNORECASE),
     spec.id)
    for spec in AGENTS
    if spec.aliases
]


def resolve_agent(text: str) -> str | None:
    """Which registry agent, if any, this line is about."""
    for pattern, agent_id in _SIGNATURES:
        if pattern.search(text):
            return agent_id
    for pattern, agent_id in _ALIASES:
        if pattern.search(text):
            return agent_id
    return None


def classify(line: str) -> str:
    if _ERROR_HINTS.search(line):
        return LEVEL_ERROR
    if _WARN_HINTS.search(line):
        return LEVEL_WARN
    if _SUCCESS_HINTS.search(line):
        return LEVEL_SUCCESS
    return LEVEL_INFO


class LogInterpreter:
    """Stateful per-run reader. Tracks the open stage so it can close it."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.current_stage: str | None = None
        self.current_agent: str | None = None
        self._pending_score_stage: str | None = None

    # ── main entry point ──────────────────────────────────────────────────

    def feed(self, line: str) -> list[dict[str, Any]]:
        """Interpret one stdout line into zero or more structured events."""
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped:
            return []

        explicit = self._explicit_event(stripped)
        if explicit is not None:
            return explicit

        events: list[dict[str, Any]] = [{
            "kind": "log",
            "line": raw,
            "level": classify(raw),
            "agent": self.current_agent or self.agent_id,
        }]

        events.extend(self._structural_events(stripped))
        return events

    def close(self, status: str) -> list[dict[str, Any]]:
        """Close any stage still open when the process exits."""
        if not self.current_stage:
            return []
        event = {
            "kind": "stage_end",
            "stage": self.current_stage,
            "agent": self.current_agent,
            "status": status,
        }
        self.current_stage = None
        self.current_agent = None
        return [event]

    # ── internals ─────────────────────────────────────────────────────────

    def _explicit_event(self, line: str) -> list[dict[str, Any]] | None:
        if not line.startswith(EVENT_PREFIX):
            return None
        payload = line[len(EVENT_PREFIX):].strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return [{"kind": "log", "line": line, "level": LEVEL_WARN,
                     "agent": self.agent_id}]
        if not isinstance(parsed, dict) or "kind" not in parsed:
            return [{"kind": "log", "line": line, "level": LEVEL_WARN,
                     "agent": self.agent_id}]
        parsed.setdefault("agent", self.current_agent or self.agent_id)
        if parsed["kind"] == "stage_start":
            self.current_stage = parsed.get("stage")
            self.current_agent = parsed.get("agent")
        elif parsed["kind"] == "stage_end":
            self.current_stage = None
        return [parsed]

    def _structural_events(self, line: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        banner = _BANNER.match(line)
        if banner:
            # Prefer the registry's own name so shouted banners keep their
            # capitalisation ("QA AGENT" must not become "Qa Agent").
            agent_id = resolve_agent(line)
            label = (AGENTS_BY_ID[agent_id].name if agent_id
                     else banner.group("name").title())
            events.extend(self._open_stage(label, banner.group("detail"), agent_id))
            return events

        calling = _CALLING.match(line)
        if calling:
            resolved = resolve_agent(calling.group("label"))
            if resolved and resolved != self.current_agent:
                events.extend(self._open_stage(
                    AGENTS_BY_ID[resolved].name, "calling model", resolved))
            return events

        resumed = _RESUME.search(line)
        if resumed:
            label = resumed.group("label")
            agent_id = resolve_agent(label) or resolve_agent(resumed.group("path"))
            events.append({
                "kind": "stage_skipped",
                "stage": label,
                "agent": agent_id,
                "artifact": resumed.group("path"),
            })
            return events

        saved = _SAVED.search(line)
        if saved:
            path = saved.group("path")
            events.append({
                "kind": "artifact",
                "path": path,
                "agent": self.current_agent or resolve_agent(path) or self.agent_id,
                "is_qa": "_QA_" in path,
            })
            return events

        step = _STEP.search(line)
        if step:
            events.extend(self._open_stage(
                f"Step {step.group('num')}", step.group("label"), None))
            return events

        score_event = self._score_event(line)
        if score_event:
            events.append(score_event)
        return events

    def _open_stage(self, label: str, detail: str,
                    agent_id: str | None) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self.current_stage and self.current_stage != label:
            events.append({
                "kind": "stage_end",
                "stage": self.current_stage,
                "agent": self.current_agent,
                "status": "ok",
            })
        if self.current_stage == label:
            return events
        self.current_stage = label
        self.current_agent = agent_id or self.current_agent
        events.append({
            "kind": "stage_start",
            "stage": label,
            "detail": detail,
            "agent": self.current_agent,
        })
        return events

    def _score_event(self, line: str) -> dict[str, Any] | None:
        if "/50" not in line:
            return None
        match = _SCORE_LABELLED.search(line)
        if match:
            label = match.group("label").strip()
            score = int(match.group("score"))
        else:
            plain = _SCORE_ANY.search(line)
            if not plain:
                return None
            label = self.current_stage or "QA"
            score = int(plain.group("score"))

        # "Average QA Score: 43/50" is a roll-up, not a per-artifact score.
        rollup = "average" in label.lower()
        return {
            "kind": "score",
            "label": _normalise_label(label),
            "score": score,
            "rollup": rollup,
            "agent": self.current_agent or self.agent_id,
            "failed": score < 35,
        }


_LABEL_CLEANUP = re.compile(r"^(?:✅|✓|⚠️?|\W)+|\s+$")
_LABEL_ALIASES = {
    "research brief": "Research Brief",
    "blueprint": "Book Blueprint",
    "book blueprint": "Book Blueprint",
    "chapter 1": "Manuscript Chapter",
    "manuscript chapter": "Manuscript Chapter",
    "short-form scripts": "Short-Form Scripts",
    "scripts": "Short-Form Scripts",
    "funnel copy": "Funnel Copy",
}


def _normalise_label(label: str) -> str:
    cleaned = _LABEL_CLEANUP.sub("", label).strip()
    return _LABEL_ALIASES.get(cleaned.lower(), cleaned or "QA")
