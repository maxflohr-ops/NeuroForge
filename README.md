# NeuroForge

Max's build monorepo. Three things live here:

## [`florra-fleet/`](florra-fleet/) — the agent fleet (active)

Multi-agent Discord fleet for Florra. Agent 001, **the Archivist**, runs the
backend of the Bandersnatch lore: intake, classification, canon-consistency,
and filing to THE FILE in Notion — plus the website front-desk chat on the
Shopify store. Deployed on Railway (two services). Start with the
[fleet README](florra-fleet/README.md) and the interactive
[architecture map](florra-fleet/docs/fleet-architecture.html).

## [`neuroforge-os/`](neuroforge-os/) — content pipeline (earlier build)

NeuroForge + OpenClaw + Florra pipeline: HeyGen avatar production, Airtable
sync, multi-platform ad APIs, master orchestrator.

## [`.claude/skills/`](.claude/skills/) — project skills for Claude Code

- `archify` — validated interactive architecture/workflow diagrams
- `google-ads-api-*`, `data-manager-api-*`, `google-analytics-*` — campaign
  ops groundwork (future agent 004, campaign-monitor)
- `openclaw-memory-tencentdb-setup` — long-term memory for OpenClaw
