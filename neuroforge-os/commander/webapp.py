#!/usr/bin/env python3
"""
Static Console Build
====================
Packages the command center into one self-contained HTML file: no server, no
backend, nothing fetched at load. It ships the *real* console assets — the same
`web/styles.css`, `web/graph.js` and `web/app.js` the live commander serves —
and swaps only the transport underneath them, so the demo cannot drift from the
console it is demonstrating.

Why it is read-only. The live commander launches subprocesses; putting that on
a public URL would be handing anyone who finds it the ability to run commands
on the host. This build has no dispatch path at all. It replays a recording:

    /api/*        answered from a baked snapshot
    /api/events   replayed from a recorded run on a clock
    POST anything never reaches a process — it restarts the replay

    python -m commander.webapp --out docs/console-demo.html
    python -m commander.webapp --out demo.html --record       # capture first

The page states that it is a recording, in the interface, so it is never
mistaken for a live fleet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import graph, profiles, registry

WEB_DIR = Path(__file__).resolve().parent / "web"
STATE_DIR = Path(__file__).resolve().parent / "state"

# Replay pacing: keep the real rhythm, but never let a gap stall the demo.
MAX_GAP_MS = 700
LEAD_IN_MS = 900


def load_events(path: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    """Read an events.jsonl recording, optionally narrowed to one run."""
    if not path.exists():
        raise SystemExit(f"no recording at {path} — run the commander first, "
                         f"or pass --events")
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if run_id and event.get("run_id") not in (run_id, None):
            continue
        events.append(event)
    if not events:
        raise SystemExit("recording contained no usable events")
    return events


def pace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert absolute timestamps into a playable schedule."""
    paced: list[dict[str, Any]] = []
    previous = events[0].get("ts", 0)
    clock = LEAD_IN_MS
    for event in events:
        ts = event.get("ts", previous)
        gap = min(MAX_GAP_MS, max(0, int((ts - previous) * 1000)))
        clock += gap
        previous = ts
        paced.append({**event, "at": clock})
    return paced


def idle(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Rewind fleet state so the recording plays from a cold start."""
    snapshot = json.loads(json.dumps(snapshot))

    for agent in snapshot.get("fleet", {}).get("agents", []):
        agent["state"] = {"status": "idle", "detail": "", "run_id": None,
                          "last_score": None, "since": 0}
    for node in snapshot.get("graph", {}).get("ir", {}).get("nodes", []):
        node["state"] = {"status": "idle"}

    # Empty the recorded run so the timeline fills from the replay rather than
    # arriving pre-populated and then doubling as events land.
    for run in snapshot.get("runs", {}).get("runs", []):
        run["stages"] = []
        run["scores"] = {}
        run["artifacts"] = []
        run["status"] = "queued"
        run["started_at"] = None
        run["finished_at"] = None

    autopilot = snapshot.get("autopilot")
    if autopilot:
        autopilot["status"] = "paused"
        autopilot["detail"] = "recording — press Start to replay"
        autopilot["active_run"] = None
        # Point the objective at the run actually being replayed, so the panel
        # and the timeline beside it are not describing different topics.
        recorded = (snapshot.get("runs", {}).get("runs") or [{}])[0]
        params = recorded.get("params") or {}
        if params.get("topic"):
            autopilot["objective"] = params["topic"]
            autopilot["faculty"] = params.get("faculty", autopilot.get("faculty"))
    return snapshot


def build_snapshot(project_dir: Path, fleet: str) -> dict[str, Any]:
    """Assemble every API response the console boots against, without a server.

    All of them: the console's boot sequence awaits them together, and one
    missing endpoint fails the whole start rather than degrading.
    """
    from .autopilot import Autopilot
    from .eventbus import EventBus
    from .runner import Runner
    from .store import FleetStore

    profile = profiles.load(fleet)
    store = FleetStore(project_dir, STATE_DIR)
    bus = EventBus(None)
    # Nothing is started here — the autopilot is constructed only to report
    # the state a live one would have.
    pilot = Autopilot(profile, Runner(project_dir, bus, store), store, bus,
                      STATE_DIR)

    fleet_payload = store.fleet_snapshot()
    fleet_payload["profile"] = profile.to_dict()
    fleet_payload["fleets"] = profiles.available()

    ir = graph.build({spec.id: store.agent_state(spec.id)
                      for spec in registry.AGENTS})

    return {
        "fleet": fleet_payload,
        "graph": {"ir": ir, "validation": graph.validate(ir),
                  "registry_errors": registry.validate()},
        "metrics": store.metrics(),
        "runs": {"runs": store.runs(40)},
        "health": {"ok": True, "cursor": 0, "simulate": True,
                   "active_runs": 0, "watchers": 1, "uptime": 0},
        "autopilot": pilot.snapshot(),
        "topics": {"topics": store.topics_on_disk()},
    }


REPLAY_JS = """
/* Replay transport.
 *
 * The console above is unmodified. Only fetch and EventSource are replaced —
 * fetch answers from a baked snapshot, EventSource plays a recorded run on a
 * clock. There is no dispatch path: a POST restarts the recording instead of
 * reaching a process, because a hosted page must never be able to launch one.
 */
(() => {
  const SNAPSHOT = __SNAPSHOT__;
  const EVENTS = __EVENTS__;
  const DURATION = EVENTS.length ? EVENTS[EVENTS.length - 1].at : 0;

  const json = (body, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });

  let listeners = [];
  let timers = [];
  let running = false;

  function stopReplay() {
    timers.forEach(clearTimeout);
    timers = [];
    running = false;
  }

  /* The runs panel re-fetches on lifecycle events, so the baked snapshot has
     to move with the replay or it would contradict the feed beside it. */
  function syncRun(event) {
    const run = (SNAPSHOT.runs.runs || [])[0];
    if (!run || event.run_id !== run.id) return;
    if (event.type === 'run.started') {
      run.status = 'running';
      run.started_at = Date.now() / 1000;
    } else if (event.type === 'run.finished' || event.type === 'run.cancelled') {
      run.status = event.status || 'ok';
      run.finished_at = Date.now() / 1000;
      run.scores = event.scores || {};
      run.artifacts = event.artifacts || [];
    }
  }

  function startReplay() {
    stopReplay();
    const run = (SNAPSHOT.runs.runs || [])[0];
    if (run) { run.status = 'queued'; run.started_at = null; run.finished_at = null; }
    running = true;
    EVENTS.forEach((event, index) => {
      timers.push(setTimeout(() => {
        const payload = { ...event, ts: Date.now() / 1000, seq: index + 1 };
        syncRun(payload);
        listeners.forEach((fn) => fn({ data: JSON.stringify(payload) }));
        if (index === EVENTS.length - 1) running = false;
      }, event.at));
    });
  }

  const route = (path) => {
    if (path.startsWith('/api/health')) return SNAPSHOT.health;
    if (path.startsWith('/api/fleet')) return SNAPSHOT.fleet;
    if (path.startsWith('/api/graph')) return SNAPSHOT.graph;
    if (path.startsWith('/api/metrics')) {
      // Polled on a timer, so it has to follow the replay rather than report
      // a frozen count beside a run that is visibly in flight.
      const run = (SNAPSHOT.runs.runs || [])[0] || {};
      const live = ['queued', 'running'].includes(run.status) ? 1 : 0;
      return { ...SNAPSHOT.metrics, runs_active: live };
    }
    if (path.startsWith('/api/topics')) return SNAPSHOT.topics;
    if (path.startsWith('/api/autopilot')) return SNAPSHOT.autopilot;
    const run = path.match(/^\\/api\\/runs\\/([\\w-]+)$/);
    if (run) {
      const found = (SNAPSHOT.runs.runs || []).find((r) => r.id === run[1]);
      return found ? { ...found, log: [] } : null;
    }
    if (path.startsWith('/api/runs')) return SNAPSHOT.runs;
    return null;
  };

  window.fetch = async (input, options = {}) => {
    const path = String(input).replace(/^https?:\\/\\/[^/]+/, '');
    const method = (options.method || 'GET').toUpperCase();

    if (method === 'POST') {
      if (path.startsWith('/api/autopilot/')) {
        const command = path.split('/').pop();
        if (SNAPSHOT.autopilot) {
          SNAPSHOT.autopilot = {
            ...SNAPSHOT.autopilot,
            status: command === 'start' ? 'running' : 'paused',
            detail: command === 'start'
              ? 'replaying a recorded mission'
              : 'recording — press Start to replay',
          };
        }
        if (command === 'start') startReplay();
        if (command === 'pause') stopReplay();
        return json(SNAPSHOT.autopilot || {});
      }
      if (path === '/api/runs') {
        startReplay();
        return json({ run: (SNAPSHOT.runs.runs || [])[0] || {} }, 202);
      }
      return json({ error: 'This is a recording — nothing is dispatched here.' }, 409);
    }

    const body = route(path);
    return body === null || body === undefined
      ? json({ error: 'not found' }, 404)
      : json(body);
  };

  window.EventSource = class {
    constructor() {
      this.onmessage = null;
      this.onopen = null;
      this.onerror = null;
      const push = (event) => this.onmessage && this.onmessage(event);
      listeners.push(push);
      this._push = push;
      setTimeout(() => this.onopen && this.onopen(), 0);
      if (!running && !timers.length) startReplay();
    }
    close() {
      listeners = listeners.filter((fn) => fn !== this._push);
    }
  };

  // Say plainly what this is, in the interface rather than only in a caption.
  window.addEventListener('DOMContentLoaded', () => {
    const bar = document.querySelector('.link-state');
    if (!bar) return;
    const chip = document.createElement('span');
    chip.className = 'replay-chip';
    chip.textContent = 'recorded · read-only';
    chip.title = 'A recorded mission playing back. No agents run here.';
    bar.parentNode.insertBefore(chip, bar);

    const launch = document.getElementById('launch-button');
    if (launch) launch.textContent = 'Replay mission';
    const blurb = document.getElementById('launch-blurb');
    if (blurb) {
      blurb.dataset.replay = '1';
    }
  });
})();
"""

REPLAY_CSS = """
.replay-chip {
  font-size: 10.5px; letter-spacing: 0.07em; text-transform: uppercase;
  color: var(--warning); border: 1px solid rgba(250, 178, 25, 0.4);
  border-radius: 999px; padding: 3px 10px; white-space: nowrap;
  font-family: var(--mono);
}
"""


def build(project_dir: Path, fleet: str, events_path: Path,
          run_id: str | None, standalone: bool) -> str:
    index = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    styles = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    graph_js = (WEB_DIR / "graph.js").read_text(encoding="utf-8")
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    snapshot = idle(build_snapshot(project_dir, fleet))
    events = pace(load_events(events_path, run_id))

    replay = (REPLAY_JS
              .replace("__SNAPSHOT__", json.dumps(snapshot, default=str))
              .replace("__EVENTS__", json.dumps(events, default=str)))

    body = re.search(r"<body>(.*)</body>", index, re.S)
    if not body:
        raise SystemExit("web/index.html has no <body> — cannot build")
    markup = body.group(1)
    # The bundle inlines everything; drop the tags that would fetch it.
    markup = re.sub(r'\s*<script src="[^"]+"></script>', "", markup)

    profile = profiles.load(fleet)
    title = f"{profile.name} Console"

    parts = [
        f"<title>{title}</title>",
        f"<style>\n{styles}\n{REPLAY_CSS}\n</style>",
        markup.strip(),
        f"<script>\n{replay}\n</script>",
        f"<script>\n{graph_js}\n</script>",
        f"<script>\n{app_js}\n</script>",
    ]
    page = "\n\n".join(parts)

    if standalone:
        page = ('<!doctype html>\n<html lang="en" data-theme="dark">\n<head>\n'
                '<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                f"{parts[0]}\n{parts[1]}\n</head>\n<body>\n"
                + "\n\n".join(parts[2:])
                + "\n</body>\n</html>\n")
    return page


def main() -> int:
    import argparse

    project_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Build the console as one self-contained, read-only page")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fleet", default=profiles.DEFAULT_FLEET)
    parser.add_argument("--events", default=str(STATE_DIR / "events.jsonl"),
                        help="Recording to replay")
    parser.add_argument("--run", default=None, help="Limit to one run id")
    parser.add_argument("--standalone", action="store_true",
                        help="Emit a complete HTML document rather than a fragment")
    args = parser.parse_args()

    page = build(project_dir, args.fleet, Path(args.events), args.run,
                 args.standalone)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"✓ {out} · {len(page) // 1024}KB · read-only replay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
