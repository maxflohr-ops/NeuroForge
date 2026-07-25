"""Agent configuration loading.

Every agent lives in agents/<name>/ with an agent.yaml describing identity,
model routing, channels, and limits. Nothing agent-specific is hard-coded
here — adding agent 002 means adding a folder, not editing core/.

Model routing indirection: agent.yaml maps task tiers to *env var names*
(e.g. classify: MODEL_CLASSIFY) so model IDs live in .env, never in code.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

FLEET_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = FLEET_ROOT / "agents"

load_dotenv(FLEET_ROOT / ".env")


class RateLimitConfig(BaseModel):
    per_user_per_minute: int = 4
    per_channel_per_minute: int = 12


class AgentYaml(BaseModel):
    """Raw shape of agents/<name>/agent.yaml."""

    name: str
    description: str = ""
    discord_token_env: str
    guild_id_env: str = "DISCORD_GUILD_ID"
    models: dict[str, str] = Field(
        description="task tier -> env var holding the model id, e.g. classify: MODEL_CLASSIFY"
    )
    max_tokens_default: int = 1024
    intake_channels: list[int] = Field(default_factory=list)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    # agent-specific settings core doesn't interpret — passed through verbatim
    options: dict = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Resolved config: env indirection collapsed to real values."""

    name: str
    description: str = ""
    agent_dir: Path
    discord_token: str
    guild_id: int
    models: dict[str, str]  # task tier -> model id
    max_tokens_default: int
    intake_channels: list[int]
    rate_limit: RateLimitConfig
    options: dict

    # fleet-wide settings (shared across agents, from env)
    notion_token: str
    notion_file_data_source_id: str
    notion_bible_page_id: str
    db_path: Path
    log_dir: Path


def _require_env(var: str, hint: str = "") -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        raise SystemExit(f"missing env var {var}. {hint}".strip())
    return value


def load_agent_config(agent_name: str) -> AgentConfig:
    agent_dir = AGENTS_DIR / agent_name
    yaml_path = agent_dir / "agent.yaml"
    if not yaml_path.exists():
        available = sorted(p.parent.name for p in AGENTS_DIR.glob("*/agent.yaml"))
        raise SystemExit(
            f"no agent named {agent_name!r} (looked for {yaml_path}). "
            f"available agents: {', '.join(available) or 'none'}"
        )

    raw = AgentYaml.model_validate(yaml.safe_load(yaml_path.read_text()))

    models = {
        tier: _require_env(env_var, f"(model id for the {raw.name} {tier!r} tier)")
        for tier, env_var in raw.models.items()
    }

    data_dir = Path(os.environ.get("FLEET_DATA_DIR", str(FLEET_ROOT / "data")))
    log_dir = Path(os.environ.get("FLEET_LOG_DIR", str(FLEET_ROOT / "logs")))
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    return AgentConfig(
        name=raw.name,
        description=raw.description,
        agent_dir=agent_dir,
        discord_token=_require_env(raw.discord_token_env),
        guild_id=int(_require_env(raw.guild_id_env)),
        models=models,
        max_tokens_default=raw.max_tokens_default,
        intake_channels=raw.intake_channels,
        rate_limit=raw.rate_limit,
        options=raw.options,
        notion_token=_require_env("NOTION_TOKEN"),
        notion_file_data_source_id=_require_env("NOTION_FILE_DATA_SOURCE_ID"),
        notion_bible_page_id=os.environ.get("NOTION_BIBLE_PAGE_ID", ""),
        db_path=data_dir / "fleet.db",
        log_dir=log_dir,
    )
