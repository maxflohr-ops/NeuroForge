---
name: google-agents
description: >
  Build, run, evaluate, deploy, and extend Google ADK agents for this repo
  using google-agents-cli (Gemini Enterprise Agent Platform). Use this skill
  whenever the user mentions Google agents, agents-cli, ADK, Gemini agents,
  the Google Developer Program, Agent Platform, Agent Runtime, or Gemini
  Enterprise — and whenever they want to run, test, fix, deploy, or add
  features to neuroforge-agent or florra-agent, or spin up a new agent for
  another brand in the stack (Opus, OpenClaw, or anything else). Also use it
  when they say things like "run the pipeline agent", "score a creator with
  the agent", "make me an agent for X", or "publish the agent".
metadata:
  author: Max Flohr Productions
---

# Google Agents (ADK / agents-cli)

This repo carries two Google ADK agents built with `google-agents-cli`, plus
the playbook for building more. The official Google skills suite is the deep
reference; this skill is the map of *our* stack and the lessons already paid
for.

## Setup (once per machine)

```bash
uv tool install google-agents-cli   # installs agents-cli 1.4.x
agents-cli info                     # verify; run from a project dir
```

Optionally install Google's full skill suite (workflow, adk-code, scaffold,
eval, deploy, publish, observability) so deep API references are on hand:
`npx skills add google/agents-cli` — or read them from
https://github.com/google/agents-cli under `skills/`.

**Auth** (needed to actually run agents, evals, or the playground):
- Google AI Studio: set `GEMINI_API_KEY` in the project `.env` (comment out
  the Vertex lines).
- Or Vertex/Agent Platform: `gcloud auth login --update-adc`, then set
  `GOOGLE_CLOUD_PROJECT` in `.env` (`GOOGLE_CLOUD_LOCATION=global`).
Code-level checks (imports, lint, unit tests) work without auth; anything
that calls Gemini does not.

## Our agents

| Agent | What it does | Reference |
|-------|--------------|-----------|
| `neuroforge-agent/` | NeuroForge content studio: orchestrator assigns topic → faculty → pillar, then a SequentialAgent runs the six-stage pipeline (research brief → book blueprint → chapter → shorts scripts → funnel copy → QA report). Stage instructions are the production prompts, loaded verbatim from `app/prompts/`. | `references/neuroforge-agent.md` |
| `florra-agent/` | Florra UGC ops: orchestrator scores creators (deterministic tool), tracks the Airtable UGC pipeline (Identified → Outreach → Contract → Content → Paid), and dispatches `outreach_agent` (DMs + briefs) and `ads_strategist_agent` (Spark Ads, lookalikes, sound retargeting, hashtags). | `references/florra-agent.md` |

Read the matching reference file before touching either agent — each covers
architecture, extension points, and what is deliberately NOT in prompts.

## Daily commands (run inside the agent's directory)

```bash
agents-cli install               # uv sync deps
agents-cli run "prompt"          # smoke test (add -v for tool-call traces)
agents-cli playground            # web UI for manual conversation
agents-cli lint                  # ruff + codespell + ty — keep green
uv run pytest tests/unit         # code-correctness tests only
agents-cli eval run              # behavior tests (LLM-as-judge; needs auth)
```

Deploy later, never without the user's explicit go-ahead:
`agents-cli scaffold enhance . --deployment-target agent_runtime` then
`agents-cli deploy`; register with `agents-cli publish gemini-enterprise`.

## The design lesson (apply to every new agent)

Match the agent shape to the work:
- **Text-pipeline work** (NeuroForge: each stage transforms the previous
  stage's text) → `SequentialAgent` of LLM stages with `output_key` state,
  instructions loaded from prompt files, orchestrator in front.
- **Tool-shaped work** (Florra: scoring math, database reads/writes, status
  transitions) → deterministic Python tools + a routing orchestrator +
  small specialist sub-agents only where judgment lives (copywriting,
  strategy). Never make the LLM do arithmetic or API calls in prose.

Keep brand voice in prompt files or shared constants, not scattered through
code. Give every tool a real docstring — ADK feeds it to the model as the
tool spec.

## Hard-won gotchas

- **Never `mkdir` before `agents-cli scaffold create`** — the CLI makes the
  directory; pre-creating flips it into enhance mode.
- **Never change the scaffolded model** (`gemini-3.7-flash` + the
  `Gemini(retry_options=...)` wrapper) unless the user asks. Model 404s are
  usually `GOOGLE_CLOUD_LOCATION`, not the model name.
- **Preserve scaffold infra**: `agents-cli-manifest.yaml`, `app/__init__.py`
  (App name must match the `app` directory), `app/fast_api_app.py`,
  `app/app_utils/` (A2A comes free from these — never hand-write A2A).
- **Run `uv run ruff format app tests` before `agents-cli lint`** — lint
  fails on formatting alone.
- **Codespell flags brand names** (e.g. "Hart" in Luna Hart). Add them to
  `ignore-words-list` in `pyproject.toml` `[tool.codespell]`.
- **No pytest on LLM output** — pytest is for code correctness (tools,
  imports, schemas); behavior belongs in `agents-cli eval` with judge
  criteria. Integration tests fail without auth; that alone is not a bug.
- Project names for scaffold: ≤26 chars, lowercase, letters/numbers/hyphens.
- Scaffolding a new agent: full flow + flag table in
  `references/agents-cli-playbook.md`.

## Where the domain knowledge lives

- NeuroForge brand, faculty, prompts: `neuroforge-os/prompts/`,
  `neuroforge-os/MARKETING_OPS.md`
- Florra workflow, Airtable schema, ad plays: `neuroforge-os/FLORRA_AIRTABLE.md`,
  `neuroforge-os/scripts/florra_airtable_logger.py`
- Cross-system flow (NeuroForge → Florra → Opus → OpenClaw):
  `neuroforge-os/scripts/master_orchestrator.py`, `neuroforge-os/COMPLETE_BUILD.md`
