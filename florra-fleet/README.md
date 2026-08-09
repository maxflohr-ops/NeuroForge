# florra-fleet

Multi-agent Discord fleet for Florra. Fleet infrastructure with one agent
shipped: **the Archivist** (agent 001) — the backend lore-management bot for
the Bandersnatch Discord. It does not roleplay. It files things.

```
florra-fleet/
├── core/                  # shared by every agent — imports nothing from agents/
│   ├── llm.py             # Anthropic client wrapper + model router (per-call token logging)
│   ├── config.py          # loads agents/<name>/agent.yaml + .env
│   ├── context.py         # AgentContext — the core↔agent contract
│   ├── memory.py          # per-channel rolling context + dedupe (SQLite, disposable)
│   ├── notion.py          # Notion adapter (data sources + pages; no delete, ever)
│   ├── airtable.py        # interface stub for future agents
│   ├── ratelimit.py       # per-user + per-channel throttles
│   └── log.py             # structured JSON logging, one file per agent
├── agents/
│   └── archivist/         # agent 001
│       ├── agent.yaml     # identity, model routing, intake channels, limits
│       ├── prompts/       # system.md (role+rules+formats) + BIBLE.md (synced canon)
│       ├── commands.py    # /ping /file /test /lorecheck /untitled /status
│       ├── intake.py      # passive loc.gov watcher + @mention answers
│       ├── filing.py      # the filing pipeline (shared by commands + intake)
│       └── loc.py         # loc.gov item JSON fetcher
├── runner.py              # python runner.py <agent> — boots exactly one agent
├── scripts/sync_bible.py  # Notion bible page -> BIBLE.md
├── Dockerfile · docker-compose.yml · .env.example
```

## Maps

Interactive, validated architecture maps (open in a browser; dark/light aware):

- [`docs/fleet-architecture.html`](docs/fleet-architecture.html) — the whole fleet: Discord + website paths, model routing, sources of truth
- [`docs/filing-pipeline.html`](docs/filing-pipeline.html) — how a loc.gov link becomes a holding of THE FILE

Regenerate with the `archify` skill (`.claude/skills/archify`).

## Run it

```bash
cp .env.example .env       # fill in the four keys
pip install -r requirements.txt
python scripts/sync_bible.py   # optional: refresh BIBLE.md from Notion
python runner.py archivist
```

Docker: `docker compose up archivist` (data + logs on named volumes).

Max provides: Anthropic API key, a Discord application + bot token
(message content intent ON, invited with `applications.commands` + `bot`
scopes), a Notion internal integration token shared with the estate page AND
with THE FILE database, and the guild id. Passive intake is off until channel
ids are listed under `intake_channels` in `agents/archivist/agent.yaml`.

## The Archivist — behavior

Gated: responds only to its slash commands, direct @mentions, and loc.gov
links in `intake_channels`. Replies are plain and backend-toned.

| command | does |
|---|---|
| `/ping` | agent name + model routing |
| `/file <url or text>` | full intake: fetch loc.gov JSON → taking test (cheap tier) → class + region → "What Was Taken" (house voice) → row in THE FILE → caption card. Dedupes on Source URL against SQLite **and** a live Notion query. |
| `/test <material> [file:true]` | taking test only — `pass` / `fail weather` / `pending` + one-line reason |
| `/lorecheck <idea>` | CONSISTENT / CONTRADICTS (with the exact clashing canon line) / NOT IN THE FILE. Never auto-canonizes. |
| `/untitled <idea>` | zero-friction capture: Status=untitled, Class=.0000, Chapter=unassigned |
| `/status <query>` | reads THE FILE by status, chapter, or title text |
| `/hunt <query>` | scouts loc.gov, pre-screens candidates against the taking test (cheap tier), returns top picks with thumbnails — nothing filed |
| `/draft <negative> <kind>` | product copy / obituary drop announcement / caption card for a filed holding, written by the canon tier |
| `/coverage` | maps holdings against the 12 subjects of Shooting Script No. 1 |
| `/ledger` | what the office filed this week (also auto-posts sundays 10 a.m., see `options.ledger` in agent.yaml) |

Every filed row also gets: the photograph downloaded from LOC and attached
(Plate property + page cover + body image), a canon-tier lore memo appended to
the page, and a **Suggested Chapter** (Chapter itself stays `unassigned` until
a human confirms). The taking test judges the actual photograph and flags
visible people ("print the places, not the people").

**Tip line** (built, gated off): set `options.tipline.channel_id` in
agent.yaml to open it — fan reports in that channel are kept as untitled
harbor-contract candidates. Per the bible, the submission-license paragraph
must exist first.

## Website chat — the front desk

The same agent, served as a website chat with a warmer persona
(`prompts/frontdesk.md`): a courteous host who answers lore and store
questions from the bible only, never invents, never shows the beast.

```bash
python web_runner.py archivist --port 8080   # POST /chat · GET /widget.js · GET /health
```

Docker: `docker compose up archivist-web`. Per-visitor rolling memory and
rate limits ride the same core services.

**Embedding on Shopify** (after deploying archivist-web somewhere public):
Online Store → Themes → Edit code → `theme.liquid`, before `</body>` add:

```html
<script src="https://YOUR-DEPLOYED-HOST/widget.js"></script>
```

The widget is a floating 🕯️ bell, styled to the house theme (bg `#141210`,
text `#E6E0D3`). It auto-wires its endpoint from wherever the script is
served; to point elsewhere set `window.ESTATE_CHAT_URL` before the tag.

Doctrine enforced in the prompt and the pipeline: the beast is never shown
whole · print the places, not the people · weather fails the taking test
(rows are filed `refused`, never deleted) · unknown canon → **"not in the
file."** · classification uncertainty → `.0000 unclassified` + `pending`,
never a guess.

Model routing (ids live in `.env` only): `classify` = cheapest tier (taking
test, class numbers, dedupe) · `standard` = mid tier (caption cards,
lorecheck, summaries) · `canon` = top tier (anything in the estate's voice).
Every call logs model + token usage to `logs/archivist.log`.

## Adding agent 002 (zero changes to core/)

1. Create a new Discord application + bot token; add its env var to `.env`
   (e.g. `DISCORD_TOKEN_VELO_SCOUT`).
2. `mkdir agents/velo-scout/` with:
   - `agent.yaml` — name, `discord_token_env`, model tier → env-var map, limits
   - `__init__.py` — `async def setup(bot, ctx): ...` registering its cogs
   - its own `prompts/` and handler modules
3. Add a service block to `docker-compose.yml` (copy the commented template —
   only `command: ["velo-scout"]` differs).
4. `python runner.py velo-scout`

That's the whole procedure: a folder, a token, a compose block. `core/` is
untouched — the runner discovers agents by name, config is data, and all
behavior differences live in the agent's own package. The Airtable interface
for velo-scout already exists in `core/airtable.py` (stub to implement).

## Data & durability

- **Notion is the source of truth** for lore. THE FILE data source id:
  `d1d87642-4cc6-4339-a375-e951b31ed8f3`. Nothing is ever deleted through
  this codebase — rejected material is `refused`, unprinted is `untitled`.
- **SQLite is disposable** ops state (rolling context, dedupe cache, in a
  mounted volume). Losing it costs nothing but a few duplicate Notion queries.
- `BIBLE.md` is a mirror of the Notion bible; regenerate with
  `python scripts/sync_bible.py`. If it ever exceeds ~50k tokens, split
  per-command sections — no vector store.
