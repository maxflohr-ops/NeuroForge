#!/usr/bin/env python3
"""
Agent Registry
==============
The declarative model of the NeuroForge fleet: every agent, what squad it
belongs to, how it is launched, what it needs to be operational, and how work
flows between agents.

Everything else in the commander reads from here. Adding an agent to the fleet
means adding one AgentSpec below — the dispatcher, the architecture map, the
credential checks and the UI all pick it up automatically.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Kinds drive node shape and colour on the architecture map.
KIND_COMMAND = "command"    # the commander itself
KIND_LLM = "llm"            # Claude-backed reasoning agents
KIND_TOOL = "tool"          # deterministic local processing
KIND_SYNC = "sync"          # moves data between systems
KIND_EXTERNAL = "external"  # third-party endpoint we do not control


@dataclass(frozen=True)
class ParamSpec:
    """One dispatch parameter, validated before it ever reaches a subprocess."""

    name: str
    label: str
    kind: str = "string"          # string | choice | int | flag
    flag: str | None = None       # CLI flag; None means positional-free (flag only)
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    pattern: str = r"^[\w \-.,'/:()]{1,120}$"
    help: str = ""

    def validate(self, value: Any) -> Any:
        """Return the coerced value or raise ValueError with a usable message."""
        if value is None or value == "":
            if self.required:
                raise ValueError(f"{self.name} is required")
            return None

        if self.kind == "flag":
            return bool(value)

        if self.kind == "int":
            try:
                coerced = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{self.name} must be a whole number")
            if not 0 <= coerced <= 10_000:
                raise ValueError(f"{self.name} out of range 0–10000")
            return coerced

        text = str(value).strip()
        if self.kind == "choice":
            if text not in self.choices:
                raise ValueError(
                    f"{self.name} must be one of: {', '.join(self.choices)}"
                )
            return text

        if not re.fullmatch(self.pattern, text):
            raise ValueError(f"{self.name} contains unsupported characters")
        return text


@dataclass(frozen=True)
class AgentSpec:
    """A dispatchable unit of the fleet, or an external system it talks to."""

    id: str
    name: str
    squad: str
    kind: str
    summary: str
    glyph: str = "◆"
    command: tuple[str, ...] = ()          # argv prefix, relative to PROJECT_DIR
    params: tuple[ParamSpec, ...] = ()
    requires_env: tuple[str, ...] = ()     # env vars needed to be operational
    feeds: tuple[str, ...] = ()            # downstream node ids
    feed_labels: dict[str, str] = field(default_factory=dict)
    log_signature: str | None = None       # regex marking this agent live in stdout
    # Other names this agent answers to in output: QA content-type labels and
    # output-file prefixes, so a resumed or saved artifact is attributed even
    # when no banner was printed for it.
    aliases: tuple[str, ...] = ()
    doc: str = ""

    @property
    def dispatchable(self) -> bool:
        return bool(self.command)

    def build_argv(self, params: dict[str, Any]) -> list[str]:
        """Validate params and produce a safe argv list (never a shell string)."""
        unknown = set(params) - {p.name for p in self.params}
        if unknown:
            raise ValueError(f"unknown parameter(s): {', '.join(sorted(unknown))}")

        argv = list(self.command)
        for spec in self.params:
            raw = params.get(spec.name, spec.default)
            value = spec.validate(raw)
            if value is None or value is False:
                continue
            if spec.kind == "flag":
                argv.append(spec.flag or f"--{spec.name}")
            else:
                argv.extend([spec.flag or f"--{spec.name}", str(value)])
        return argv


@dataclass(frozen=True)
class Squad:
    """A lane on the architecture map — one column of related agents."""

    id: str
    name: str
    lane: int
    accent: str
    summary: str


# Accents are the validated categorical order for a dark surface, assigned in
# fixed slot order. Squad colour is lane identity only — an agent's status is
# carried by its own indicator and label, never by its squad hue.
SQUADS: tuple[Squad, ...] = (
    Squad("command", "Command", 0, "#3987e5",
          "Mission intake and fleet supervision"),
    Squad("forge", "Content Forge", 1, "#d95926",
          "Claude agents that write the product"),
    Squad("production", "Production", 2, "#199e70",
          "Turns text into shippable media"),
    Squad("distribution", "Distribution", 3, "#c98500",
          "Moves finished assets into the stack"),
    Squad("growth", "Growth", 4, "#d55181",
          "Paid amplification and audience building"),
    Squad("intelligence", "Intelligence", 5, "#008300",
          "Closes the loop and improves the system"),
    Squad("external", "External Systems", 6, "#9085e9",
          "Third-party endpoints the fleet depends on"),
)

FACULTY = (
    "Dr. Nova Vale",
    "Kai Ren",
    "Marcus Voss",
    "Luna Hart",
    "Dr. Orion Hale",
)

_PIPELINE = ("python", "scripts/neuroforge_pipeline.py")

_TOPIC = ParamSpec("topic", "Topic", flag="--topic", required=True,
                   default="Stop Overthinking",
                   help='Content topic, e.g. "Stop Overthinking"')
_FACULTY = ParamSpec("faculty", "Faculty", kind="choice", flag="--faculty",
                     required=True, default=FACULTY[0], choices=FACULTY,
                     help="Which faculty voice writes this")
_PILLAR = ParamSpec("pillar", "Pillar", flag="--pillar",
                    help="Content pillar override (defaults from faculty)")
_NO_QA = ParamSpec("no_qa", "Skip QA", kind="flag", flag="--no-qa",
                   help="Skip the QA agent after each step (~50% fewer tokens)")
_RESUME = ParamSpec("resume", "Resume", kind="flag", flag="--resume",
                    help="Reuse outputs already on disk instead of regenerating")
_DRY_RUN = ParamSpec("dry_run", "Dry run", kind="flag", flag="--dry-run",
                     help="Preview only — write nothing to the remote system")


AGENTS: tuple[AgentSpec, ...] = (
    # ── Command ───────────────────────────────────────────────────────────
    AgentSpec(
        id="commander",
        name="Agent Commander",
        squad="command",
        kind=KIND_COMMAND,
        glyph="⌘",
        summary="Dispatches every agent, supervises runs, streams live telemetry.",
        feeds=("mission",),
        feed_labels={"mission": "launch"},
        doc="The control plane you are looking at. Runs locally, holds no secrets "
            "of its own, and can only launch commands declared in this registry.",
    ),
    AgentSpec(
        id="mission",
        name="Full Mission",
        squad="command",
        kind=KIND_COMMAND,
        glyph="▶",
        summary="Runs the complete forge chain for one topic: research → funnel.",
        command=_PIPELINE + ("--mode", "full"),
        params=(_TOPIC, _FACULTY, _PILLAR, _NO_QA, _RESUME),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("research",),
        feed_labels={"research": "kickoff"},
        doc="The standard production run. Five artifacts plus QA reports, "
            "roughly $0.17 of tokens per topic.",
    ),

    # ── Content Forge ─────────────────────────────────────────────────────
    AgentSpec(
        id="research",
        name="Research Agent",
        squad="forge",
        kind=KIND_LLM,
        glyph="🔬",
        summary="Builds the structured strategy brief every later agent reads.",
        command=_PIPELINE + ("--mode", "research"),
        params=(_TOPIC, _FACULTY, _PILLAR, _NO_QA),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("architect", "shorts", "funnel", "qa"),
        feed_labels={"architect": "brief", "shorts": "brief", "funnel": "brief"},
        log_signature=r"RESEARCH AGENT|Research Agent",
        aliases=("Research Brief", "01_research_brief"),
        doc="Prompt: prompts/01_research_agent.md",
    ),
    AgentSpec(
        id="architect",
        name="Book Architect",
        squad="forge",
        kind=KIND_LLM,
        glyph="📐",
        summary="Turns the brief into a full book blueprint and transformation arc.",
        command=_PIPELINE + ("--mode", "blueprint"),
        params=(_TOPIC, _FACULTY, _PILLAR, _NO_QA),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("manuscript", "funnel", "qa"),
        feed_labels={"manuscript": "blueprint", "funnel": "blueprint"},
        log_signature=r"BOOK ARCHITECT AGENT|Book Architect Agent",
        aliases=("Book Blueprint", "Blueprint", "02_book_blueprint"),
        doc="Prompt: prompts/02_book_architect_agent.md",
    ),
    AgentSpec(
        id="manuscript",
        name="Manuscript Agent",
        squad="forge",
        kind=KIND_LLM,
        glyph="✍",
        summary="Writes chapters in faculty voice; chapter 1 anchors every other voice.",
        command=_PIPELINE + ("--mode", "manuscript"),
        params=(_TOPIC, _FACULTY, _PILLAR,
                ParamSpec("chapter", "Chapter", kind="int", flag="--chapter",
                          default=1, help="Chapter number to write"),
                _NO_QA),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("shorts", "funnel", "qa"),
        feed_labels={"shorts": "voice anchor", "funnel": "voice anchor"},
        log_signature=r"MANUSCRIPT AGENT|Manuscript Agent",
        aliases=("Manuscript Chapter", "03_chapter"),
        doc="Prompt: prompts/03_manuscript_agent.md",
    ),
    AgentSpec(
        id="shorts",
        name="Shorts Script Agent",
        squad="forge",
        kind=KIND_LLM,
        glyph="🎬",
        summary="Produces 20–40 short-form scripts plus quote and carousel concepts.",
        command=_PIPELINE + ("--mode", "scripts"),
        params=(_TOPIC, _FACULTY, _PILLAR, _NO_QA),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("parse_scripts", "qa"),
        feed_labels={"parse_scripts": "script batch"},
        log_signature=r"SHORTS SCRIPT AGENT|Shorts Script Agent",
        aliases=("Short-Form Scripts", "Shorts Scripts", "04_shorts_scripts"),
        doc="Prompt: prompts/04_shorts_script_agent.md",
    ),
    AgentSpec(
        id="funnel",
        name="Funnel Agent",
        squad="forge",
        kind=KIND_LLM,
        glyph="💰",
        summary="Landing page, thank-you page, 5-email sequence and ad copy.",
        command=_PIPELINE + ("--mode", "funnel"),
        params=(_TOPIC, _FACULTY, _PILLAR, _NO_QA),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("qa", "meta_ads"),
        feed_labels={"meta_ads": "ad copy"},
        log_signature=r"FUNNEL AGENT|Funnel Agent",
        aliases=("Funnel Copy", "05_funnel_copy"),
        doc="Prompt: prompts/05_funnel_agent.md",
    ),
    AgentSpec(
        id="qa",
        name="QA Agent",
        squad="forge",
        kind=KIND_LLM,
        glyph="🔍",
        summary="Scores every artifact out of 50 and writes a prompt improvement note.",
        command=_PIPELINE + ("--mode", "qa"),
        params=(_TOPIC, _FACULTY,
                ParamSpec("file", "File", flag="--file", required=True,
                          pattern=r"^[\w\-./ ]{1,200}$",
                          help="Path to the artifact to review"),
                ParamSpec("content_type", "Content type", kind="choice",
                          flag="--content_type", default="Manuscript Chapter",
                          choices=("Research Brief", "Book Blueprint",
                                   "Manuscript Chapter", "Short-Form Scripts",
                                   "Funnel Copy"))),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("optimizer", "airtable_sync"),
        feed_labels={"optimizer": "scores"},
        log_signature=r"QA AGENT|QA Agent",
        doc="Prompt: prompts/06_qa_agent.md. A score below 35/50 halts a full mission.",
    ),

    # ── Production ────────────────────────────────────────────────────────
    AgentSpec(
        id="parse_scripts",
        name="Script Parser",
        squad="production",
        kind=KIND_TOOL,
        glyph="⧉",
        summary="Splits a shorts batch file into one JSON per script.",
        command=("python", "scripts/parse_scripts.py"),
        params=(ParamSpec("file", "Batch file", flag="--file", required=True,
                          pattern=r"^[\w\-./ *]{1,200}$",
                          help="Path to a 04_shorts_scripts_*.md file"),
                _TOPIC,
                ParamSpec("faculty", "Faculty", kind="choice", flag="--faculty",
                          choices=FACULTY, default=FACULTY[0])),
        feeds=("heygen_producer",),
        feed_labels={"heygen_producer": "script JSON"},
        doc="Pure local parsing — no API calls, safe to re-run.",
    ),
    AgentSpec(
        id="heygen_setup",
        name="HeyGen Setup",
        squad="production",
        kind=KIND_TOOL,
        glyph="⚙",
        summary="Matches each faculty member to a stock avatar and voice ID.",
        command=("python", "scripts/heygen_setup.py"),
        params=(ParamSpec("faculty", "Faculty", kind="choice", flag="--faculty",
                          choices=FACULTY, help="Configure one faculty only"),
                ParamSpec("save", "Write .heygen.env", kind="flag", flag="--save"),
                ParamSpec("list", "List catalogue", kind="flag", flag="--list")),
        requires_env=("HEYGEN_API_KEY",),
        feeds=("heygen_producer",),
        feed_labels={"heygen_producer": "avatar IDs"},
    ),
    AgentSpec(
        id="heygen_producer",
        name="HeyGen Producer",
        squad="production",
        kind=KIND_SYNC,
        glyph="🎥",
        summary="Renders avatar video for each parsed short-form script.",
        command=("python", "scripts/heygen_producer.py"),
        params=(_TOPIC, _FACULTY,
                ParamSpec("scripts", "Script range", flag="--scripts",
                          pattern=r"^[\d\-, ]{0,40}$",
                          help='Range or list, e.g. "1-5" or "3,7"'),
                _DRY_RUN),
        requires_env=("HEYGEN_API_KEY",),
        feeds=("heygen_api", "flowstage", "opus"),
        feed_labels={"heygen_api": "render job", "flowstage": "video"},
    ),

    # ── Distribution ──────────────────────────────────────────────────────
    AgentSpec(
        id="orchestrator",
        name="Master Orchestrator",
        squad="distribution",
        kind=KIND_SYNC,
        glyph="📡",
        summary="Runs the cross-system sync: forge → Florra → Opus → OpenClaw.",
        command=("python", "scripts/master_orchestrator.py"),
        params=(ParamSpec("topic", "Topic", flag="--topic",
                          help="Limit the sync to one topic"), _DRY_RUN),
        requires_env=("AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"),
        feeds=("airtable_sync", "florra", "opus", "openclaw"),
    ),
    AgentSpec(
        id="airtable_sync",
        name="Airtable Sync",
        squad="distribution",
        kind=KIND_SYNC,
        glyph="🗂",
        summary="Pushes projects, pipeline runs and QA scores into the Airtable base.",
        command=("python", "scripts/airtable_sync.py"),
        params=(ParamSpec("topic", "Topic", flag="--topic",
                          help="Sync one topic only"), _DRY_RUN),
        requires_env=("AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"),
        feeds=("airtable_api",),
    ),
    AgentSpec(
        id="florra",
        name="Florra Logger",
        squad="distribution",
        kind=KIND_SYNC,
        glyph="🌸",
        summary="Manages the UGC creator pipeline and content library.",
        command=("python", "scripts/florra_airtable_logger.py"),
        requires_env=("AIRTABLE_API_KEY",),
        feeds=("airtable_api", "opus"),
    ),
    AgentSpec(
        id="opus",
        name="Opus Scheduler",
        squad="distribution",
        kind=KIND_SYNC,
        glyph="🎞",
        summary="Clips long-form video and schedules the results per platform.",
        command=("python", "scripts/opus_airtable_logger.py"),
        requires_env=("OPUS_API_KEY",),
        feeds=("flowstage", "openclaw", "airtable_api"),
        feed_labels={"openclaw": "performance"},
    ),
    AgentSpec(
        id="flowstage",
        name="Flowstage Publisher",
        squad="distribution",
        kind=KIND_SYNC,
        glyph="📤",
        summary="Auto-posts finished clips to TikTok, Instagram and YouTube.",
        command=("python", "scripts/flowstage_integration.py"),
        requires_env=("FLOWSTAGE_API_TOKEN",),
        feeds=("tiktok_ads", "meta_ads"),
        feed_labels={"tiktok_ads": "sound signal"},
    ),

    # ── Growth ────────────────────────────────────────────────────────────
    AgentSpec(
        id="meta_ads",
        name="Meta Ads",
        squad="growth",
        kind=KIND_SYNC,
        glyph="🅜",
        summary="Builds custom and lookalike audiences, campaigns and ads.",
        command=("python", "scripts/meta_ads_integration.py"),
        requires_env=("META_ADS_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"),
        feeds=("meta_api",),
    ),
    AgentSpec(
        id="tiktok_ads",
        name="TikTok Ads",
        squad="growth",
        kind=KIND_SYNC,
        glyph="🅣",
        summary="Sound and hashtag retargeting audiences, campaigns and ad groups.",
        command=("python", "scripts/tiktok_ads_integration.py"),
        requires_env=("TIKTOK_ADS_ACCESS_TOKEN", "TIKTOK_ADVERTISER_ID"),
        feeds=("tiktok_api",),
    ),

    # ── Intelligence ──────────────────────────────────────────────────────
    AgentSpec(
        id="openclaw",
        name="OpenClaw",
        squad="intelligence",
        kind=KIND_SYNC,
        glyph="🦾",
        summary="Logs interactions and proposes improvements back to the fleet.",
        command=("python", "scripts/openclaw_airtable_logger.py"),
        requires_env=("TELEGRAM_BOT_TOKEN",),
        feeds=("optimizer", "airtable_api"),
        feed_labels={"optimizer": "improvement notes"},
    ),
    AgentSpec(
        id="optimizer",
        name="Prompt Optimizer",
        squad="intelligence",
        kind=KIND_LLM,
        glyph="♻",
        summary="Rewrites underperforming prompts from accumulated QA data.",
        command=("python", "scripts/optimize_prompts.py"),
        params=(ParamSpec("agent", "Target agent", kind="choice", flag="--agent",
                          choices=("research", "blueprint", "manuscript",
                                   "scripts", "funnel", "qa"),
                          help="Optimise a single agent prompt"),
                ParamSpec("threshold", "Score threshold", kind="int",
                          flag="--threshold", default=40,
                          help="Rewrite agents scoring below this"),
                ParamSpec("apply", "Apply rewrites", kind="flag", flag="--apply",
                          help="Write new prompts (old versions are backed up)")),
        requires_env=("ANTHROPIC_API_KEY",),
        feeds=("research", "architect", "manuscript", "shorts", "funnel", "qa"),
        feed_labels={"research": "rewritten prompts"},
        doc="Run every ~10 topics. Backs up to prompts/versions/ before applying.",
    ),

    # ── External systems ──────────────────────────────────────────────────
    AgentSpec("anthropic_api", "Anthropic API", "external", KIND_EXTERNAL,
              "Claude model endpoint behind every reasoning agent.", glyph="✳",
              requires_env=("ANTHROPIC_API_KEY",)),
    AgentSpec("heygen_api", "HeyGen", "external", KIND_EXTERNAL,
              "Avatar IV video rendering.", glyph="◉",
              requires_env=("HEYGEN_API_KEY",)),
    AgentSpec("airtable_api", "Airtable", "external", KIND_EXTERNAL,
              "System of record for projects, runs, QA and campaigns.", glyph="▦",
              requires_env=("AIRTABLE_API_KEY",)),
    AgentSpec("meta_api", "Meta Ads API", "external", KIND_EXTERNAL,
              "Audiences, campaigns and ad delivery.", glyph="◑",
              requires_env=("META_ADS_ACCESS_TOKEN",)),
    AgentSpec("tiktok_api", "TikTok Ads API", "external", KIND_EXTERNAL,
              "Sound retargeting and campaign delivery.", glyph="◐",
              requires_env=("TIKTOK_ADS_ACCESS_TOKEN",)),
)

# The forge chain, in the order a full mission executes it.
MISSION_CHAIN: tuple[str, ...] = (
    "research", "architect", "manuscript", "shorts", "funnel",
)

AGENTS_BY_ID: dict[str, AgentSpec] = {a.id: a for a in AGENTS}
SQUADS_BY_ID: dict[str, Squad] = {s.id: s for s in SQUADS}


def get(agent_id: str) -> AgentSpec:
    """Look up an agent, raising a clear error for unknown ids."""
    try:
        return AGENTS_BY_ID[agent_id]
    except KeyError:
        raise KeyError(f"unknown agent: {agent_id}")


def missing_env(spec: AgentSpec, env: dict[str, str] | None = None) -> list[str]:
    """Env vars this agent needs that are absent or still placeholders."""
    env = os.environ if env is None else env
    missing = []
    for key in spec.requires_env:
        value = (env.get(key) or "").strip()
        if not value or "PLACEHOLDER" in value.upper() or value.startswith("your_"):
            missing.append(key)
    return missing


def readiness(spec: AgentSpec, env: dict[str, str] | None = None) -> str:
    """operational | unconfigured | passive — how the map colours an idle node."""
    if not spec.requires_env:
        return "operational" if spec.dispatchable or spec.kind == KIND_COMMAND else "passive"
    return "unconfigured" if missing_env(spec, env) else "operational"


def validate() -> list[str]:
    """Structural checks on the registry itself. Empty list means healthy."""
    errors: list[str] = []
    seen: set[str] = set()

    for spec in AGENTS:
        if spec.id in seen:
            errors.append(f"duplicate agent id: {spec.id}")
        seen.add(spec.id)

        if spec.squad not in SQUADS_BY_ID:
            errors.append(f"{spec.id}: unknown squad '{spec.squad}'")

        if spec.kind == KIND_EXTERNAL and spec.dispatchable:
            errors.append(f"{spec.id}: external systems must not be dispatchable")

        for target in spec.feeds:
            if target == spec.id:
                errors.append(f"{spec.id}: self-referencing edge")

        param_names = [p.name for p in spec.params]
        if len(param_names) != len(set(param_names)):
            errors.append(f"{spec.id}: duplicate parameter names")

        for param in spec.params:
            if param.kind == "choice" and not param.choices:
                errors.append(f"{spec.id}.{param.name}: choice param has no choices")
            if param.default is not None and param.kind not in ("flag",):
                try:
                    param.validate(param.default)
                except ValueError as exc:
                    errors.append(f"{spec.id}.{param.name}: bad default — {exc}")

    for spec in AGENTS:
        for target in spec.feeds:
            if target not in seen:
                errors.append(f"{spec.id}: edge to unknown agent '{target}'")
            if target in spec.feed_labels and not spec.feed_labels[target]:
                errors.append(f"{spec.id}: empty edge label for '{target}'")

    for chain_id in MISSION_CHAIN:
        if chain_id not in seen:
            errors.append(f"mission chain references unknown agent '{chain_id}'")

    return errors
