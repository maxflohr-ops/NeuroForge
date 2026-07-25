"""Anthropic client wrapper + per-agent model router.

Tasks route by tier, configured in agent.yaml -> .env:
  classify  cheapest tier (taking test, class numbers, dedupe judgment)
  standard  mid tier (caption cards, filing summaries)
  canon     top tier (anything written in the estate's voice)

Every call logs token usage to the agent's log so cost is inspectable.
"""

from __future__ import annotations

import json
import logging
import re

import anthropic

from core.log import log_event

CLASSIFY = "classify"
STANDARD = "standard"
CANON = "canon"


class ModelRouter:
    def __init__(
        self,
        models: dict[str, str],
        logger: logging.Logger,
        default_max_tokens: int = 1024,
    ):
        self.models = models
        self.logger = logger
        self.default_max_tokens = default_max_tokens
        self.client = anthropic.AsyncAnthropic()  # ANTHROPIC_API_KEY from env

    def model_for(self, task: str) -> str:
        try:
            return self.models[task]
        except KeyError:
            raise ValueError(f"no model configured for task tier {task!r}") from None

    async def complete(
        self,
        task: str,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        images: list[tuple[str, str]] | None = None,
    ) -> str:
        """One-shot completion. Returns the text of the response ('' on refusal).

        images: optional [(media_type, base64_data)] shown before the prompt.
        """
        model = self.model_for(task)
        content: str | list = prompt
        if images:
            content = [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                }
                for media_type, b64 in images
            ] + [{"type": "text", "text": prompt}]
        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens or self.default_max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        log_event(
            self.logger,
            "llm_call",
            task=task,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
        if response.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in response.content if b.type == "text").strip()

    async def complete_json(
        self,
        task: str,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        images: list[tuple[str, str]] | None = None,
    ) -> dict | None:
        """Completion that expects a single JSON object back. None if unparseable —
        callers must treat None as 'uncertain', never guess."""
        text = await self.complete(task, system, prompt, max_tokens=max_tokens, images=images)
        return _extract_json(text)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    # tolerate ```json fences and surrounding prose
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None
