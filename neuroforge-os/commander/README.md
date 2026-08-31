# Agent Commander & Command Center

A control plane for the agent fleet, and the real-time console that visualises
it. Every agent in `scripts/` becomes something you can launch, watch and stop
from one screen, with a live architecture map showing where work actually is —
and an autopilot that works the mission book around the clock without anyone
clicking Deploy.

Runs on the Python standard library alone — nothing new in `requirements.txt`,
no build step, no npm. The existing Docker image serves it as-is.

**Fleets shipped here:**

| Fleet | Callsign | Derived from | Autopilot |
|---|---|---|---|
| `neuroforge` | NF | — | off |
| `florra_alpha` | FFA | `neuroforge` | on, **simulate** |

---

## Run it

```bash
cd neuroforge-os

# Florra Fleet Alpha, working its book continuously — simulated, costs nothing
python -m commander --fleet florra_alpha

# The base fleet, hands-on, no autopilot
python -m commander --fleet neuroforge --no-autopilot

# Everything simulated, including manual launches
python -m commander --simulate
```

Then open <http://127.0.0.1:8787>.

```bash
docker compose up commander           # hands-on console
docker compose up -d florra-alpha     # 24/7, restarts with the host
```

### Flags

| Flag | Default | What it does |
|---|---|---|
| `--fleet` | `florra_alpha` | Which fleet profile to command. |
| `--autopilot` / `--no-autopilot` | from profile | Override whether it self-starts. |
| `--host` | `127.0.0.1` | Bind address. Loopback only unless you change it. |
| `--port` | `8787` | |
| `--simulate` | off | Dispatch simulated runs instead of real agents. |
| `--max-concurrent` | `2` | How many agents may run at once. |
| `--token` | — | Require `Authorization: Bearer <token>` on every request. |
| `--no-env` | off | Skip loading `.env`. |
| `--verbose` | off | Log every HTTP request. |

Each has an environment equivalent: `COMMANDER_FLEET`, `COMMANDER_HOST`,
`COMMANDER_PORT`, `COMMANDER_SIMULATE`, `COMMANDER_MAX_CONCURRENT`,
`COMMANDER_TOKEN`.

**Before binding anything but loopback, set a token.** The commander launches
processes; treat access to it as access to the machine.

```bash
python -m commander --host 0.0.0.0 --token "$(openssl rand -hex 16)"
# then open http://<host>:8787/?token=<the token>
```

---

## Fleets and cloning

A fleet is one *deployment* of the agent architecture. `registry.py` describes
the agents; a profile in `commander/fleets/` describes a fleet that runs them —
its name, its mission book, its budget and its cadence.

**Florra Fleet Alpha is a clone of NeuroForge in exactly that sense.** It states
only what differs — identity, budget, cadence, QA floor — and inherits the rest,
so architectural fixes reach every fleet while each keeps its own operating
policy.

```bash
python -m commander.profiles                     # list and validate every fleet
python -m commander.profiles --show florra_alpha # the resolved profile
python -m commander.profiles --clone florra_alpha --as florra_beta \
                             --name "Florra Fleet Beta"
```

A fresh clone always lands with autopilot **off** and mode **simulate**. Turning
a fleet loose is a decision someone has to make on purpose.

### The mission book

`backlog` is an ordered list of objectives — a topic and the faculty voice that
writes it. The autopilot works down it in order. Add work by appending to the
profile:

```json
{ "topic": "The Sleep Protocol", "faculty": "Dr. Orion Hale" }
```

Topics that already have a full set of artifacts in `output/` are marked
pre-existing and skipped (`skip_completed`), so a fleet resuming against a
half-finished book goes straight to real work.

---

## 24/7 self-improving operation

The autopilot closes the loop the pipeline was designed for:

```
next objective → full mission → QA scores every artifact
       ↑                              ↓
       └── prompt optimizer ←── QA history in neuroforge_db.json
```

Every `optimize_every` missions it dispatches the prompt optimizer against
accumulated QA data. Below the QA floor, a topic is reworked; if rework does not
clear the bar it is **quarantined** rather than passed downstream, and waits for
a human.

### The rails

An unattended process that spends money needs to be boring and stoppable. Every
one of these is enforced in `autopilot.py` and covered by tests:

| Rail | Effect |
|---|---|
| `budget_usd` | Hard ceiling on estimated spend. The fleet stops itself and **cannot raise it** — only an operator can. |
| `daily_mission_cap` | A bug cannot burn a month of budget overnight. |
| `qa_floor` | Weak work is reworked, then quarantined. Never shipped onward. |
| `max_consecutive_failures` | Exponential backoff, then a full halt that needs a human. |
| `mode: simulate` | The whole loop runs end to end for nothing. |
| `optimize_applies: false` | The optimizer proposes prompt rewrites; it does not overwrite them. |
| persisted state | A restart resumes; it does not replay work already done. |

Spend is an **estimate** — roughly $0.17 per full mission, from the cost table
in the project README. The pipeline does not report token usage, so the ceiling
is a guard rail, not an invoice. Keep a hard limit on the API key too.

### Going live

Florra Fleet Alpha ships in simulate mode. To let it spend:

1. Put a real `ANTHROPIC_API_KEY` in `.env`.
2. Set `"mode": "live"` in `commander/fleets/florra_alpha.json`.
3. Set `budget_usd` to what you are willing to lose to a bug.
4. Watch the first few missions before walking away.
5. Only then consider `"optimize_applies": true`, which lets the fleet edit its
   own prompts. Old versions are backed up to `prompts/versions/`, but this is
   the one setting that changes the system's own behaviour unattended.

```bash
docker compose up -d florra-alpha   # restart: unless-stopped
docker compose logs -f florra-alpha
```

Autopilot state lives in `commander/state/autopilot_<fleet>.json` — delete it to
start the book over.

---

## What the console shows

**Architecture map.** Every agent as a node, positioned by squad, with live
status written inside it. Solid lines carry work and animate while the agent
downstream of them is running. Faint lines are QA reviews and external calls;
both are toggleable so the primary flow stays readable. Click a node to trace
its neighbours and open its detail drawer; drag to pan, scroll to zoom.

**Fleet roster.** Every agent grouped by squad. Agents whose credentials are
missing read `dark` and are drawn with a dashed outline — you can see at a
glance what is actually armed.

**Mission timeline.** Each stage of the selected run as a bar, with its QA
score where one landed.

**Live feed.** Everything the running agent prints, tagged by which agent said
it, filterable down to just events or just problems.

**Launch console.** Pick an agent, fill in its parameters (the form is
generated from the registry, so it always matches what the agent accepts), and
deploy. Runs can be cancelled from the runs list.

**Autopilot panel.** Current objective, mission-book progress, spend against
budget, what happens next and when, plus Hold and Skip. It tells you which rail
stopped the fleet when one does.

**KPI strip.** Active runs, QA average with a sparkline, topics, artifacts,
lifetime logged spend, and how many agents are credentialled. (Logged spend is
the estimate across all history in `neuroforge_db.json`; the autopilot's budget
meter tracks only what that fleet has spent.)

---

## How it works

```
registry.py     what agents exist, how they launch, how work flows between them
memory.py       optional cross-mission recall, fail-open and off by default
export.py       the map as a standalone SVG or self-contained HTML page
webapp.py       the whole console as one hostable, read-only page
runner.py       launches them as subprocesses and supervises the result
interpreter.py  reconstructs structure from what the agents print
eventbus.py     ordered, replayable telemetry with a JSONL record
store.py        live fleet state, run history, metrics
graph.py        typed architecture IR + validator + deterministic layout
server.py       stdlib HTTP, REST + Server-Sent Events, static assets
simulator.py    realistic runs with no API calls, for demos and tests
web/            the console — vanilla JS, no build step
```

### The agents narrate themselves

The pipeline already prints `🔬 RESEARCH AGENT — Starting`, `✓ Saved: …` and
`QA Score: 42/50`. The interpreter reads those lines and rebuilds stages,
artifacts and scores from them, so **no existing script had to change** to
appear on the map.

An agent that wants to say something the printed output cannot express can emit
one line of the explicit protocol:

```python
print('NEUROFORGE_EVENT {"kind": "stage_start", "stage": "Voice pass"}')
```

Supported kinds: `stage_start`, `stage_end`, `stage_skipped`, `artifact`,
`score`, `log`.

### Dispatch safety

The console can launch processes, so the path from HTTP request to `Popen` is
deliberately narrow:

- Only agents declared in `registry.py` can be launched at all.
- Commands are **argv lists**, never shell strings — a topic name cannot
  become a command.
- Every parameter is validated against its `ParamSpec` (pattern, choice list or
  numeric range) before it is used. `"Stop Overthinking; rm -rf /"` is rejected
  at the registry, not sanitised downstream.
- Live dispatch refuses to start an agent whose credentials are missing or
  still placeholders, and says which ones.
- Static assets resolve inside `web/` only.

### The map is validated before it is drawn

`graph.py` produces a typed IR — nodes, edges, lanes and fully resolved
geometry — and checks it atomically before serving: schema, edge integrity,
node overlap, route bounds, and label-to-node clearance. Labels that cannot be
placed clear of a box are moved along their route, and dropped with a warning
if no clear position exists, so a validated map never contains unreadable text.
The commander **refuses to serve** if the map is unsound.

```bash
python -m commander.graph --validate   # exit 1 if the map is broken
python -m commander.graph --json       # print the IR
```

### Exporting the map

The same validated IR renders to a picture you can commit, attach to a doc or
open from disk years from now — no scripts, no fonts, no network:

```bash
python -m commander.export --format html --out docs/fleet-architecture.html
python -m commander.export --format svg  --out docs/fleet-architecture.svg
python -m commander.export --format svg  --include flow --out docs/fleet-flow.svg
```

Colour is applied through CSS custom properties per squad rather than baked
into the shapes, so one fragment reads correctly on a light or a dark ground.
An unsound map is an error, not a crooked diagram — export refuses.

Layout is deterministic: the same registry always produces the same picture, so
the IR can be diffed and tested like any other artifact.

---

## The Evidence Agent (smolagents)

One agent in the fleet writes and executes Python: `scripts/evidence_agent.py`
is a smolagents `CodeAgent`. It reads an artifact, pulls out the checkable
factual claims, searches for real sources, and writes an evidence table —
claim, verdict, URL. It exists because the project's non-negotiables forbid
fabricated citations and nothing was actually checking.

```bash
python scripts/evidence_agent.py --selftest          # wiring only, no model call
python scripts/evidence_agent.py \
    --topic "Stop Overthinking" \
    --file output/stop_overthinking/01_research_brief_20260101_120000.md
```

Output lands at `output/<topic>/06_evidence_<timestamp>.md`.

### Containing it

Generated code is untrusted by construction, so this agent is bounded more
tightly than the rest:

| Guard | Effect |
|---|---|
| `--executor docker` | **The default.** Generated code runs in a container, never in the commander's process. |
| `--executor local` | Refused outright unless `EVIDENCE_ALLOW_LOCAL=1` is set for a supervised run. Never appropriate unattended. |
| `--executor e2b` | Available; requires `E2B_API_KEY`. |
| Import allowlist | `json, re, collections, itertools, statistics` only — no filesystem, network or subprocess. |
| Not autopilot-dispatched | The unattended loop only launches missions and the optimizer. This one runs when a person asks. |

### Why no LiteLLM

smolagents ships no Anthropic model, and its LiteLLM path pulls a large
dependency tree in for no gain — this project already depends on `anthropic`.
The agent uses a small `Model` subclass over that SDK instead, which has a
useful side effect: it reports **real token counts**, where the rest of the
fleet only estimates spend.

Search is keyless DuckDuckGo (`ddgs`) by default, or a keyed API when
`SERPER_API_KEY` / `SEARCHAPI_API_KEY` is set.

---

## Cross-mission memory (optional)

Every mission currently starts from nothing. Six of the ten objectives in the
book are adjacent and three share a faculty voice on overlapping ground, so the
Research Agent rediscovers the same territory each time. Attaching a memory
server closes that gap: what an earlier mission learned, and what QA objected
to, is handed to the next one.

The fleet speaks the [TencentDB Agent Memory](https://github.com/Tencent/TencentDB-Agent-Memory)
v2 protocol (MIT). **Despite the name it needs no Tencent Cloud account** — it
is three Docker services and an OpenAI-compatible LLM endpoint of your choosing.

```bash
git clone https://github.com/Tencent/TencentDB-Agent-Memory
cd TencentDB-Agent-Memory/deploy/global-images
cp .env.example .env && $EDITOR .env && ./start-all.sh
```

Then in the fleet's `.env`:

```bash
MEMORY_ENDPOINT=http://127.0.0.1:8420
MEMORY_API_KEY=...
MEMORY_SERVICE_ID=...        # the memory space id
MEMORY_AGENT_ID=florra-fleet # scopes recall to this fleet
```

### How it behaves

| | |
|---|---|
| Before a mission | Recalls prior work on the topic and hands it to the Research Agent as `--audience_notes` |
| After a mission | Writes back what it produced, which stage was weakest, and whether it was quarantined |
| Not configured | **Every call is a no-op.** The fleet behaves exactly as it does today |
| Server down or slow | **Fails open.** The mission runs without context rather than not running |

`commander/memory.py` speaks the protocol over `urllib` — the official SDK
works fine, but the commander stays standard library. Failures are counted and
surfaced in the autopilot panel rather than swallowed silently.

### Two things worth knowing before you turn it on

**It has its own LLM spend.** The memory pipeline runs its own model calls on
its own key to build structured memory from conversations. That cost is real
and the fleet's `budget_usd` ceiling does not see it — the ceiling only counts
missions. Put a limit on that key too.

**It is three more services.** Memory Core, Memory Hub and a Proxy, plus their
volumes. That is a reasonable trade for a fleet working a long book; it is
overkill for a handful of one-off runs.

---

## Shipping the console as a web app

The live commander launches subprocesses. Putting **that** on a public URL
would hand anyone who finds it the ability to run commands on the host, so it
is not something to deploy. What you can host is a read-only build:

```bash
python -m commander.webapp --out docs/console-demo.html --standalone
```

One self-contained HTML file — no server, no backend, nothing fetched at load.
Open it from disk, drop it on any static host, attach it to a deck.

It ships the **real** console assets — the same `web/styles.css`,
`web/graph.js` and `web/app.js` the commander serves — and replaces only the
transport beneath them, so the demo cannot drift from the console it
demonstrates:

| Endpoint | In the build |
|---|---|
| `GET /api/*` | Answered from a baked snapshot of a real fleet |
| `GET /api/events` | A recorded run, replayed on a clock at its original rhythm |
| `POST /api/runs` | Restarts the replay. **There is no dispatch path.** |
| `POST /api/autopilot/*` | Toggles the panel locally; launches nothing |

The page says `recorded · read-only` in its own header, so it is never mistaken
for a live fleet, and the Deploy button reads *Replay mission*.

### Recording one

The build replays `commander/state/events.jsonl`, which the commander writes as
it runs. To capture a fresh one:

```bash
python -m commander --simulate --no-autopilot &
curl -s localhost:8787/api/runs -H 'Content-Type: application/json' \
     -d '{"agent":"mission","params":{"topic":"Stop Negative Thoughts",
          "faculty":"Dr. Nova Vale"},"simulate":true}'
python -m commander.webapp --out docs/console-demo.html --standalone
```

`--run <id>` narrows the build to a single run; `--fleet` picks which fleet's
identity and snapshot to bake in.

---

## Adding an agent

Add one `AgentSpec` to `registry.py`. The dispatcher, the launch form, the
credential checks, the roster and the map all pick it up — there is nothing
else to wire.

```python
AgentSpec(
    id="thumbnails",
    name="Thumbnail Agent",
    squad="production",
    kind=KIND_TOOL,
    glyph="🖼",
    summary="Renders thumbnails for every short-form script.",
    command=("python", "scripts/thumbnails.py"),
    params=(_TOPIC, _DRY_RUN),
    requires_env=("HEYGEN_API_KEY",),
    feeds=("flowstage",),
    feed_labels={"flowstage": "thumbnails"},
)
```

Then re-validate:

```bash
python -m commander.graph --validate
python -m unittest discover -s commander/tests -t .
```

---

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness, event cursor, active run count |
| GET | `/api/fleet` | Agents, squads, readiness, live state |
| GET | `/api/graph` | Validated architecture IR + validation report |
| GET | `/api/metrics` | QA history and spend roll-up |
| GET | `/api/topics` | Topics with output on disk |
| GET | `/api/runs` | Recent runs |
| GET | `/api/runs/<id>` | One run, including its log tail |
| POST | `/api/runs` | Dispatch — `{agent, params, simulate}` |
| POST | `/api/runs/<id>/cancel` | Stop a running agent |
| GET | `/api/events?since=N` | Server-Sent Events, replayed from a cursor |
| GET | `/api/autopilot` | Fleet identity, status, book progress, budget |
| POST | `/api/autopilot/start` | Begin working the mission book |
| POST | `/api/autopilot/pause` | Hold after the current mission |
| POST | `/api/autopilot/skip` | Abandon the current objective |
| POST | `/api/autopilot/budget` | Raise the ceiling — `{budget_usd}` |

Every event carries a monotonic `seq`. The console reconnects with the last one
it applied, so a dropped connection resumes rather than losing the middle of a
mission.

---

## Tests

```bash
python -m unittest discover -s commander/tests -t .
```

170 tests. The commander itself is standard library only; the Evidence Agent
tests skip cleanly when smolagents is absent, and the static-build tests skip
when no recording is present. The end-to-end cases drive the real supervisor
against the simulator, so dispatch, interpretation, the event bus and the store
are exercised together rather than mocked past. The autopilot is driven by
calling `tick()` directly, so each decision — budget stop, daily cap, rework,
quarantine, backoff, halt — is asserted rather than waited for.

---

## State on disk

`commander/state/` holds `runs.json` (run history, no log bodies),
`events.jsonl` (the full telemetry record) and `autopilot_<fleet>.json` (mission
book position, spend, outcomes). It is gitignored and safe to delete — the
commander rebuilds from an empty directory, though the autopilot will restart
its mission book from the top.
