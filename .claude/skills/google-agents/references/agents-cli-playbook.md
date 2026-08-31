# agents-cli playbook — scaffolding a new agent from scratch

Condensed from Google's official skills (google/agents-cli → `skills/`),
plus what we learned building neuroforge-agent and florra-agent. Install the
official suite (`npx skills add google/agents-cli`) when you need the deep
ADK API reference, eval schema details, or deployment troubleshooting.

## Lifecycle

1. **Understand** — pin down: what the agent does, external APIs/data, what
   it must NOT do, prototype vs deployment. One or two questions for simple
   agents; don't scaffold on guesses.
2. **Check recipes** — retrieval/RAG, sandboxed code execution, cross-session
   memory, OAuth, approval gates, guardrails, scheduled runs are all
   clone-and-study recipes in Google's `google-agents-cli-adk-code` skill →
   `references/samples.md`. Never hand-build one of those before checking.
3. **Scaffold**:
   ```bash
   agents-cli scaffold create <name> --agent adk --prototype \
     --agent-guidance-filename CLAUDE.md
   ```
   Name ≤26 chars, lowercase/numbers/hyphens. Do NOT mkdir first. `adk` is
   the only template; A2A protocol comes built in.
4. **Build** — edit `app/agent.py` (+ `app/tools.py` for functions). Keep
   the scaffolded model and `Gemini(retry_options=...)` wrapper. Smoke test
   with `agents-cli run "prompt"` (`-v` shows tool calls; `--start-server`
   for repeated calls).
5. **Evaluate** — the main loop. 1–2 cases in
   `tests/eval/datasets/basic-dataset.json` first, `agents-cli eval run`,
   read scores (exit 0 regardless), iterate. `eval compare` for regressions,
   `eval analyze` for failure clusters, `eval optimize` to auto-tune prompts.
6. **Deploy** (only on explicit user approval) —
   `agents-cli scaffold enhance . --deployment-target agent_runtime`
   (or `cloud_run`/`gke`; ask before picking a CI/CD runner), then
   `agents-cli deploy`.
7. **Publish** (optional) — `agents-cli publish gemini-enterprise`.

## ADK patterns cheat sheet

```python
from google.adk.agents import Agent, SequentialAgent, ParallelAgent, LoopAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

worker = Agent(
    name="worker",
    model=Gemini(model="gemini-3.7-flash",
                 retry_options=types.HttpRetryOptions(attempts=3)),
    instruction="...",            # {state_key} injects session state —
    tools=[my_function],          #   only if the key exists; use a callable
    output_key="result",          #   instruction to bypass templating
)
pipeline = SequentialAgent(name="p", sub_agents=[worker, ...])  # in order
root = Agent(..., sub_agents=[pipeline])  # LLM transfers by description
app = App(root_agent=root, name="app")    # name must match app/ dir
```

- Tool functions: plain Python, typed args, full docstring (it becomes the
  tool spec). Return dicts with a `status` field so the model can react to
  errors. External calls: env-driven config + graceful structured error
  when credentials are missing.
- A sub-agent instance can have only ONE parent. Reuse a capability via
  `AgentTool` or a second instance, never by re-parenting.
- `ParallelAgent` for concurrent fan-out (distinct output_keys),
  `LoopAgent` for refine-until-done (needs an escalation checker).

## Project layout (what the scaffold gives you)

- `app/agent.py` — yours. `app/__init__.py`, `app/fast_api_app.py`,
  `app/app_utils/` — scaffold infra (serving, sessions, A2A): don't edit.
- `agents-cli-manifest.yaml` — CLI reads it: don't edit.
- `.env` — auth config (gitignored; `.env.example` is committed).
- `tests/unit` (code correctness) / `tests/integration` (needs auth) /
  `tests/eval` (behavior, LLM-as-judge via `response_quality.py`).
- `pyproject.toml` — deps via `uv add <pkg>`; ruff/codespell/ty config.

## Verification checklist before pushing

```bash
uv run ruff format app tests   # first — lint fails on formatting
agents-cli lint                # ruff + codespell + ty
uv run pytest tests/unit
uv run python -c "from app.agent import app"   # tree assembles
```

Integration tests failing with "No API key was provided" in an
un-authenticated environment is expected, not a code bug.

## Debugging

- Reproduce → localize (`agents-cli run -v`) → fix one thing → rerun →
  add an eval case for non-obvious bugs.
- Same error 3+ times: stop, find the root cause.
- CLI failures: `agents-cli <cmd> --help` ends with a `Source:` line
  pointing at the implementing file.
- Docs index: `curl https://adk.dev/llms.txt`, then fetch the page you need.
