# florra-agent — architecture and extension guide

ADK port of Florra OS (`neuroforge-os/FLORRA_AIRTABLE.md`): UGC music
marketing — TikTok sound research → creator scoring → outreach → content →
Spark Ads. Lives in `florra-agent/`.

## Why this one is tools-first (the design lesson)

NeuroForge's work is text transforming text, so it's a sequential LLM
pipeline. Florra's work is mostly deterministic: scoring math, Airtable
reads/writes, status transitions. Those live as Python tools in
`app/tools.py` so results are consistent and auditable; the LLM only handles
judgment — DM copy, briefs, ad strategy — via two small sub-agents. Follow
this split for any future agent: if a step has one correct answer, it's a
tool, not a prompt.

## Agent tree

```
florra_orchestrator (LlmAgent, gemini-3.7-flash)
├── tools (app/tools.py):
│   ├── score_creator(followers, engagement_rate, posts_with_sound, avg_views)
│   ├── add_creator(...)                → Airtable People table
│   ├── add_to_ugc_pipeline(...)        → UGC Pipeline table
│   ├── update_pipeline_status(rec, st) → stage transitions
│   ├── get_pipeline_by_status(status)  → pipeline queries
│   └── add_spark_code(...)             → Spark Codes table
├── outreach_agent        → output_key: outreach_package  (DM + creator brief)
└── ads_strategist_agent  → output_key: ad_strategy       (4 Florra ad plays)
```

Pipeline stages: Identified → Outreach → Contract → Content → Paid
(`PIPELINE_STAGES` in tools.py; writes validate against it).

## Scoring model (tunable, in code not prompts)

`score_creator` weights: engagement 40% (8% = elite), sound-trend activity
25% (5 posts with the sound = max), reach 20% (capped at 500k), view
efficiency 15% (avg views / followers, 2x = max). Tiers: Nano <10k, Micro
<100k, Mid <500k, Macro <1M, Mega 1M+. Thresholds: 70+ strong candidate,
45+ worth a look. **There was no scoring formula in Florra OS (sound-lookup.js
was a "next step") — this is a first implementation. Tune the weights in
`app/tools.py` and the unit tests in `tests/unit/test_tools.py` together.**

## Airtable wiring

Base `applXEAjh6k3Xmybl`; table IDs are in `_TABLES` in tools.py, mirrored
from `neuroforge-os/scripts/florra_airtable_logger.py`. Set
`AIRTABLE_API_KEY` (and optionally `AIRTABLE_BASE_ID`) in `florra-agent/.env`.
Without the key, Airtable tools return a structured error the orchestrator
relays — scoring and outreach still work. The orchestrator is instructed to
confirm before writes and echo record IDs after.

## Not yet wired (Florra OS next steps — extend here)

- **Chartex sound lookup** (`sound → creators using it`): add a tool that
  calls the Chartex API; feed results straight into `score_creator`.
- **Cobalt content downloads** + Content Library logging.
- **Meta / TikTok Ads APIs**: `neuroforge-os/scripts/meta_ads_integration.py`
  and `tiktok_ads_integration.py` have the call patterns — wrap as tools
  behind a human-approval gate (see the approval-gate recipe in Google's
  `google-agents-cli-adk-code` skill → `references/samples.md` before
  building one by hand).
- **Modash outreach loading**: the `modash-campaign-templates` skill covers
  loading sequences into Modash; the outreach_agent's DM/brief output is its
  natural input.

## Eval cases

`tests/eval/datasets/basic-dataset.json`: capabilities, creator scoring
(reference: @wavey.jules ≈ high-80s, Mid tier, strong candidate — checks the
model actually calls the tool instead of guessing), outreach dispatch.
Unit tests cover the scorer and stage validation; keep them in lockstep with
any weight changes.
