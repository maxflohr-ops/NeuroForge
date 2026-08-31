# Florra OS — The Operating Layer

> *"A small human team, a large agent team. Agents run it around the clock; a
> human makes the calls."* — florra.net

Florra OS is the agent-run operations platform every florra product sits on.
The official site (florra.net) describes it as **the operating layer**: research,
outreach, CRM, daily desks, builds, reporting. This repo is that layer —
the engine behind the petal.

```
                 ┌─────────────────────────────────────────────────┐
                 │              FLORRA OS  (this repo)             │
                 │        "the operating layer"                    │
                 │                                                  │
   CONTENT       │   NeuroForge pipeline (6 agents)                 │
   ENGINE  ─────►│     research → blueprint → chapter → scripts     │
                 │     → funnel → QA                               │
                 │        │                                        │
                 │        ▼                                        │
   CLIP          │   Clip Engine (podcast → shorts)                │
   ENGINE  ─────►│        │                                        │
                 │        ▼                                        │
   POSTING       │   Postiz (TikTok / IG / YouTube)                │
   LAYER   ─────►│        │                                        │
                 │        ▼                                        │
   OPTIMIZER     │   OpenClaw / optimize_prompts.py (learn loop)   │
                 │        │                                        │
                 │        ▼                                        │
   OBSERVE       │   florra_dashboard.py (the numbers)             │
                 │        │                                        │
                 │        ▼                                        │
   DIRECT        │   notion_todo.py (the daily desk → Notion)      │
                 └─────────────────────────────────────────────────┘
```

## What the operating layer powers

Per florra.net, everything florra ships sits on this layer:

| Product | What it is | How Florra OS serves it |
|---------|-----------|--------------------------|
| **florra records** | Label that signs one song at a time, 50/50 | The network behind a release: creators, clippers, bounties, a desk watching every hour |
| **bounty sounds** | Funders post a purse; clippers capture views; verified views get paid | The clip engine + verification rails that make bounties legible |
| **redstring** | The case board, live beta | The outreach/CRM desk that keeps cases moving |
| **cleared** | Studios for cleared music | The back office for operators |
| **management** | Artists, podcasts, brands | Daily desks + reporting |

## The components

| Component | What it does | Where |
|-----------|--------------|-------|
| **NeuroForge pipeline** | Generates a full content package per topic (6 Claude agents + QA) | `neuroforge-os/scripts/neuroforge_pipeline.py` |
| **Google ADK agents** | Gemini ports of the pipeline + the Florra UGC workflow, deployable to Cloud Run | `neuroforge-agent/`, `florra-agent/` |
| **Clip Engine** | Ingests podcast/source clips → logs to Opus Airtable → schedules to socials | `clip-engine/` |
| **Postiz integration** | Uploads + schedules videos to TikTok/IG/YouTube via the Postiz public API | `neuroforge-os/scripts/postiz_integration.py` |
| **Airtable sync** | Mirrors projects/runs to the master Airtable base (18 tables) | `neuroforge-os/scripts/airtable_sync.py` |
| **Ad integrations** | Meta lookalikes + TikTok sound retargeting (ready, waiting on credentials) | `neuroforge-os/scripts/meta_ads_integration.py`, `tiktok_ads_integration.py` |
| **Optimizer** | Reads QA logs, rewrites underperforming prompts | `neuroforge-os/scripts/optimize_prompts.py` |
| **Dashboard** | Turns the run DB + clip manifest into a readable report | `florra_dashboard.py` |
| **To-do CLI** | Pushes tasks to the Notion "Florra" list (or a local file) | `notion_todo.py` |

## The loop

1. **Weekly cron** (`.github/workflows/weekly-content-routine.yml`) generates the
   next roadmap topic and schedules it to Postiz.
2. **Clip Engine** keeps the short-form feed fed from podcast audio.
3. **Postiz** publishes to TikTok / Instagram / YouTube on Mon/Wed/Fri.
4. **OpenClaw + optimizer** learn from engagement and QA scores.
5. **Dashboard** shows what's working so the next week's topic is a bet, not a guess.
6. **To-do CLI** keeps the daily desk in Notion so a human makes the calls.

## Non-negotiables

- Honest AI labeling on every post (`video_made_with_ai`).
- No fake citations, no medical claims, no overclaiming.
- Human review before anything is published.
- Agents run around the clock; a human makes the calls.

## Status

| Layer | Status |
|-------|--------|
| Content engine | ✅ Live (5 topics generated, QA-scored) |
| Google ADK agents | ✅ Built (deploy via `agents-cli`) |
| Clip engine | ✅ Built + merged |
| Postiz posting | ✅ Built (needs Postiz host + accounts) |
| Airtable sync | ✅ Built (needs API key) |
| Ads (Meta/TikTok) | ⏳ Ready — waiting on API credentials |
| Weekly cron | ✅ Built (needs GitHub secrets) |
| Notion to-do | ✅ Built (needs integration token) |
