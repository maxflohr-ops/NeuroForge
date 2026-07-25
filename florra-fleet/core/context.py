"""AgentContext — the bundle of shared services the runner hands to an agent.

Agents receive this in their setup(bot, ctx) entrypoint. This is the whole
contract between core/ and agents/: core never imports agents, agents only
consume this object.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.config import AgentConfig
from core.llm import ModelRouter
from core.memory import Memory
from core.notion import NotionAdapter
from core.ratelimit import RateLimiter


@dataclass
class AgentContext:
    config: AgentConfig
    llm: ModelRouter
    notion: NotionAdapter
    memory: Memory
    limiter: RateLimiter
    log: logging.Logger
