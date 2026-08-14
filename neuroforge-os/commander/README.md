# Agent Commander & Command Center

A control plane for the NeuroForge fleet, and the real-time console that
visualises it. Every agent in `scripts/` becomes something you can launch,
watch and stop from one screen, with a live architecture map showing where work
actually is.

Runs on the Python standard library alone — nothing new in `requirements.txt`,
no build step, no npm. The existing Docker image serves it as-is.

---

## Run it

```bash
cd neuroforge-os

# Rehearse the whole fleet with no API keys and no writes anywhere
python -m commander --simulate

# Live — dispatches the real agents
python -m commander
```

Then open <http://127.0.0.1:8787>.

```bash
docker compose up commander        # same thing, in the existing image
```

### Flags

| Flag | Default | What it does |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Loopback only unless you change it. |
| `--port` | `8787` | |
| `--simulate` | off | Dispatch simulated runs instead of real agents. |
| `--max-concurrent` | `2` | How many agents may run at once. |
| `--token` | — | Require `Authorization: Bearer <token>` on every request. |
| `--no-env` | off | Skip loading `.env`. |
| `--verbose` | off | Log every HTTP request. |

Each has an environment equivalent: `COMMANDER_HOST`, `COMMANDER_PORT`,
`COMMANDER_SIMULATE`, `COMMANDER_MAX_CONCURRENT`, `COMMANDER_TOKEN`.

**Before binding anything but loopback, set a token.** The commander launches
processes; treat access to it as access to the machine.

```bash
python -m commander --host 0.0.0.0 --token "$(openssl rand -hex 16)"
# then open http://<host>:8787/?token=<the token>
```

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

**KPI strip.** Active runs, QA average with a sparkline, topics, artifacts,
estimated spend, and how many agents are credentialled.

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

Every event carries a monotonic `seq`. The console reconnects with the last one
it applied, so a dropped connection resumes rather than losing the middle of a
mission.

---

## Tests

```bash
python -m unittest discover -s commander/tests -t .
```

63 tests, standard library only. The end-to-end cases drive the real supervisor
against the simulator, so dispatch, interpretation, the event bus and the store
are exercised together rather than mocked past.

---

## State on disk

`commander/state/` holds `runs.json` (run history, no log bodies) and
`events.jsonl` (the full telemetry record). It is gitignored and safe to
delete — the commander rebuilds from an empty directory.
