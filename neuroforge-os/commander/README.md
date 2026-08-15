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

Layout is deterministic: the same registry always produces the same picture, so
the IR can be diffed and tested like any other artifact.

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

92 tests, standard library only. The end-to-end cases drive the real supervisor
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
