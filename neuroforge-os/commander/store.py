#!/usr/bin/env python3
"""
Fleet State Store
=================
Holds what the command center draws: the live status of every agent, the runs
that produced those statuses, and the metrics rolled up from QA history.

The store is the only thing that mutates fleet state; the runner reports into
it and the HTTP layer reads snapshots out of it.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from . import registry

# Agent live states, in the order the UI ranks them by severity.
IDLE = "idle"
QUEUED = "queued"
RUNNING = "running"
OK = "ok"
WARN = "warn"
ERROR = "error"

MAX_LOG_LINES = 600      # kept in memory per run for the log panel
MAX_RUN_HISTORY = 200


class FleetStore:
    def __init__(self, project_dir: Path, state_dir: Path):
        self.project_dir = project_dir
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_path = state_dir / "runs.json"

        self._lock = threading.RLock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._agent_state: dict[str, dict[str, Any]] = {
            spec.id: {
                "status": IDLE,
                "since": time.time(),
                "run_id": None,
                "detail": "",
                "last_score": None,
            }
            for spec in registry.AGENTS
        }
        self.started_at = time.time()
        self._load()

    # ── persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.runs_path.exists():
            return
        try:
            saved = json.loads(self.runs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for run in saved.get("runs", [])[-MAX_RUN_HISTORY:]:
            # Anything still marked live when we shut down is not live now.
            if run.get("status") in (QUEUED, RUNNING):
                run["status"] = "interrupted"
            run["log"] = []
            self._runs[run["id"]] = run
            self._order.append(run["id"])

    def _persist(self) -> None:
        """Write run history atomically, without the (large) log bodies."""
        with self._lock:
            runs = []
            for run_id in self._order[-MAX_RUN_HISTORY:]:
                run = dict(self._runs[run_id])
                run.pop("log", None)
                runs.append(run)
        tmp = self.runs_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps({"runs": runs}, indent=2, default=str),
                           encoding="utf-8")
            os.replace(tmp, self.runs_path)
        except OSError:
            pass

    # ── runs ──────────────────────────────────────────────────────────────

    def create_run(self, run_id: str, agent_id: str, params: dict[str, Any],
                   argv: list[str], simulated: bool = False) -> dict[str, Any]:
        spec = registry.get(agent_id)
        run = {
            "id": run_id,
            "agent": agent_id,
            "agent_name": spec.name,
            "squad": spec.squad,
            "params": params,
            "argv": argv,
            "simulated": simulated,
            "status": QUEUED,
            "queued_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "stages": [],
            "artifacts": [],
            "scores": {},
            "error": None,
            "log": [],
        }
        with self._lock:
            self._runs[run_id] = run
            self._order.append(run_id)
            self._trim()
        self.set_agent_status(agent_id, QUEUED, run_id=run_id, detail="queued")
        self._persist()
        return run

    def _trim(self) -> None:
        while len(self._order) > MAX_RUN_HISTORY:
            oldest = self._order.pop(0)
            self._runs.pop(oldest, None)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def update_run(self, run_id: str, **fields: Any) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run.update(fields)
        self._persist()

    def append_log(self, run_id: str, line: str, level: str = "info") -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["log"].append({"ts": time.time(), "line": line, "level": level})
            if len(run["log"]) > MAX_LOG_LINES:
                del run["log"][: len(run["log"]) - MAX_LOG_LINES]

    def start_stage(self, run_id: str, stage: str, agent_id: str | None = None) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            for existing in run["stages"]:
                if existing["name"] == stage and existing["finished_at"] is None:
                    return
            run["stages"].append({
                "name": stage,
                "agent": agent_id,
                "started_at": time.time(),
                "finished_at": None,
                "score": None,
                "status": RUNNING,
            })

    def finish_stage(self, run_id: str, stage: str, status: str = OK,
                     score: int | None = None) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            for existing in reversed(run["stages"]):
                if existing["name"] == stage:
                    existing["finished_at"] = time.time()
                    existing["status"] = status
                    if score is not None:
                        existing["score"] = score
                    return

    def score_current_stage(self, run_id: str, score: int, status: str = OK) -> None:
        """Attach a QA score to whichever stage is open, or the most recent one."""
        with self._lock:
            run = self._runs.get(run_id)
            if not run or not run["stages"]:
                return
            open_stages = [s for s in run["stages"] if s["finished_at"] is None]
            target = open_stages[-1] if open_stages else run["stages"][-1]
            target["score"] = score
            if status != OK:
                target["status"] = status

    def add_artifact(self, run_id: str, path: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run and path not in run["artifacts"]:
                run["artifacts"].append(path)

    def add_score(self, run_id: str, label: str, score: int) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["scores"][label] = score

    def runs(self, limit: int = 40) -> list[dict[str, Any]]:
        """Most recent runs first, without log bodies."""
        with self._lock:
            selected = [self._runs[i] for i in reversed(self._order[-limit:])]
            return [{k: v for k, v in run.items() if k != "log"} for run in selected]

    def active_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._runs.values()
                    if r["status"] in (QUEUED, RUNNING)]

    # ── agent state ───────────────────────────────────────────────────────

    def set_agent_status(self, agent_id: str, status: str, run_id: str | None = None,
                         detail: str = "", score: int | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._agent_state.setdefault(
                agent_id, {"status": IDLE, "since": time.time(), "run_id": None,
                           "detail": "", "last_score": None})
            state["status"] = status
            state["since"] = time.time()
            state["run_id"] = run_id
            state["detail"] = detail
            if score is not None:
                state["last_score"] = score
            return dict(state)

    def agent_state(self, agent_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._agent_state.get(agent_id, {"status": IDLE}))

    # ── snapshots ─────────────────────────────────────────────────────────

    def fleet_snapshot(self) -> dict[str, Any]:
        """Everything the UI needs to paint the roster and the map."""
        agents = []
        for spec in registry.AGENTS:
            state = self.agent_state(spec.id)
            agents.append({
                "id": spec.id,
                "name": spec.name,
                "squad": spec.squad,
                "kind": spec.kind,
                "glyph": spec.glyph,
                "summary": spec.summary,
                "doc": spec.doc,
                "dispatchable": spec.dispatchable,
                "readiness": registry.readiness(spec),
                "missing_env": registry.missing_env(spec),
                "params": [
                    {
                        "name": p.name, "label": p.label, "kind": p.kind,
                        "required": p.required, "default": p.default,
                        "choices": list(p.choices), "help": p.help,
                    }
                    for p in spec.params
                ],
                "state": state,
            })
        return {
            "agents": agents,
            "squads": [
                {"id": s.id, "name": s.name, "lane": s.lane,
                 "accent": s.accent, "summary": s.summary}
                for s in registry.SQUADS
            ],
            "mission_chain": list(registry.MISSION_CHAIN),
            "uptime": time.time() - self.started_at,
        }

    # ── metrics ───────────────────────────────────────────────────────────

    def metrics(self) -> dict[str, Any]:
        """QA history from neuroforge_db.json, joined with live run counters."""
        db_path = self.project_dir / "neuroforge_db.json"
        records: list[dict[str, Any]] = []
        if db_path.exists():
            try:
                loaded = json.loads(db_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    records = [r for r in loaded if isinstance(r, dict)]
            except (OSError, json.JSONDecodeError):
                records = []

        by_agent: dict[str, list[int]] = {}
        by_topic: dict[str, list[int]] = {}
        timeline: list[dict[str, Any]] = []
        for record in records:
            score = record.get("qa_score")
            agent = str(record.get("agent", "unknown"))
            topic = str(record.get("topic", "unknown"))
            if isinstance(score, int):
                by_agent.setdefault(agent, []).append(score)
                by_topic.setdefault(topic, []).append(score)
                timeline.append({
                    "ts": record.get("timestamp"),
                    "topic": topic,
                    "agent": agent,
                    "score": score,
                })

        def average(values: list[int]) -> float | None:
            return round(sum(values) / len(values), 1) if values else None

        all_scores = [s for values in by_agent.values() for s in values]
        with self._lock:
            statuses = [r["status"] for r in self._runs.values()]

        # Cost model from the README: ~12 calls per full topic, ~$0.17 total.
        topics_run = len(by_topic)
        return {
            "runs_total": len(statuses),
            "runs_active": sum(1 for s in statuses if s in (QUEUED, RUNNING)),
            "runs_failed": sum(1 for s in statuses if s == ERROR),
            "artifacts_logged": len(records),
            "topics": topics_run,
            "qa_average": average(all_scores),
            "qa_by_agent": {k: average(v) for k, v in sorted(by_agent.items())},
            "qa_by_topic": {k: average(v) for k, v in sorted(by_topic.items())},
            "qa_timeline": timeline[-60:],
            "estimated_spend_usd": round(topics_run * 0.17, 2),
            "uptime": time.time() - self.started_at,
        }

    def topics_on_disk(self) -> list[dict[str, Any]]:
        """Topics with output on disk, newest artifact first."""
        output_dir = self.project_dir / "output"
        if not output_dir.exists():
            return []
        topics = []
        for entry in sorted(output_dir.iterdir()):
            if not entry.is_dir():
                continue
            files = [f for f in entry.glob("*.md")]
            if not files:
                continue
            newest = max(f.stat().st_mtime for f in files)
            topics.append({
                "slug": entry.name,
                "title": entry.name.replace("_", " ").title(),
                "artifacts": len(files),
                "qa_reports": len([f for f in files if "_QA_" in f.name]),
                "updated": newest,
                "stages": sorted({re.sub(r"_\d{8}_\d{6}\.md$", "", f.name)
                                  for f in files if "_QA_" not in f.name}),
            })
        topics.sort(key=lambda t: t["updated"], reverse=True)
        return topics
