# NeuroForge / Florra OS

The operating layer — an agent-run content and marketing machine for the Florra
network. The official site is [florra.net](https://florra.net); this repo is
the engine behind the "florra os" petal.

**The loop:** generate → publish → learn → scale. Agents run around the clock;
a human makes the calls.

```
NeuroForge pipeline → Clip Engine → Postiz → OpenClaw/optimizer → dashboard → Notion desk
```

## Quick start

```bash
# See the whole world
cat FLORRA_OS.md

# Generate content for a topic (needs ANTHROPIC_API_KEY)
cd neuroforge-os
python scripts/neuroforge_pipeline.py --topic "Stop Overthinking" --faculty "Dr. Nova Vale" --mode full

# Run the dashboard (works offline, no keys)
python florra_dashboard.py

# Manage the launch desk (local fallback until NOTION_TOKEN is set)
python notion_todo.py list
python notion_todo.py add "Host Postiz and connect accounts" --tag launch
```

## Components

| Component | Path | Needs |
|-----------|------|-------|
| Pipeline (6 agents + QA) | `neuroforge-os/scripts/neuroforge_pipeline.py` | Anthropic key |
| Google ADK agents | `neuroforge-agent/`, `florra-agent/` | `agents-cli`, Gemini key |
| Clip Engine | `clip-engine/` (merge via `merge-clip-engine.sh`) | Postiz key |
| Postiz posting | `neuroforge-os/scripts/postiz_integration.py` | Postiz host + accounts |
| Airtable sync | `neuroforge-os/scripts/airtable_sync.py` | Airtable key |
| Ad integrations | `neuroforge-os/scripts/{meta_ads,tiktok_ads}_integration.py` | ad account creds |
| Optimizer | `neuroforge-os/scripts/optimize_prompts.py` | Anthropic key |
| Weekly cron | `.github/workflows/weekly-content-routine.yml` | GitHub secrets |
| Dashboard | `florra_dashboard.py` | none (reads local files) |
| Notion desk | `notion_todo.py` | `NOTION_TOKEN`, `NOTION_DB_ID` |

## Env

Copy `neuroforge-os/.env.example` → `.env` and fill in keys. For GitHub Actions,
set the same values as repo secrets.

## Non-negotiables

- Honest AI labeling on every post.
- No fake citations, no medical claims, no overclaiming.
- Human review before publishing. Agents run around the clock; a human makes the calls.
