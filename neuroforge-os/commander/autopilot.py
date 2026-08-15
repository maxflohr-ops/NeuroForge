#!/usr/bin/env python3
"""
Autopilot
=========
Runs a fleet around the clock: works its way down the mission book, gates every
topic on its QA scores, reworks what falls short, and folds accumulated QA data
back into the prompts on a cadence. The self-improving loop the pipeline was
designed for, with nobody clicking Deploy.

The rails are the point. An unattended process that spends money and writes to
live systems needs to be boring and stoppable:

  * a hard budget ceiling — it stops itself, it does not ask for more
  * a daily mission cap, so a bug cannot burn a month of budget overnight
  * a QA floor: weak work is reworked, then quarantined, never shipped onward
  * consecutive-failure backoff, then a full stop that needs a human
  * simulate mode that exercises the whole loop for nothing
  * every decision persisted, so a restart resumes instead of replaying

Nothing here bypasses the runner: the autopilot dispatches through exactly the
same validated path a human click uses.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .eventbus import EventBus
from .profiles import FleetProfile, Objective
from .runner import DispatchError, Runner
from .store import ERROR, FleetStore, OK, WARN

AUTOPILOT = "autopilot"

# Lifecycle states. Only `running` dispatches work.
IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
BACKOFF = "backoff"
BUDGET_REACHED = "budget_reached"
CAPPED = "capped"
BACKLOG_EMPTY = "backlog_empty"
HALTED = "halted"

TICK_SECONDS = 5.0

# Reasons a fleet stops on its own and will not restart without a human.
TERMINAL = (HALTED, BUDGET_REACHED)


class Autopilot:
    def __init__(self, profile: FleetProfile, runner: Runner, store: FleetStore,
                 bus: EventBus, state_dir: Path):
        self.profile = profile
        self.policy = profile.autopilot
        self.runner = runner
        self.store = store
        self.bus = bus
        self.state_path = state_dir / f"autopilot_{profile.id}.json"

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = self._load()

    # ── persistence ───────────────────────────────────────────────────────

    def _blank_state(self) -> dict[str, Any]:
        return {
            "fleet": self.profile.id,
            "status": RUNNING if self.policy.enabled else IDLE,
            "detail": "",
            "cursor": 0,                 # index into the backlog
            "completed": [],             # slugs finished to standard
            "preexisting": [],           # slugs already complete on disk
            "quarantined": [],           # slugs that failed rework
            "attempts": {},              # slug -> rework attempts used
            "missions": 0,
            "failures": 0,               # consecutive
            "spend_estimate": 0.0,
            "optimizations": [],
            "day": _today(),
            "today_missions": 0,
            "active_run": None,
            "active_kind": None,         # mission | optimize
            "active_slug": None,
            "next_action_at": 0.0,
            "history": [],
        }

    def _load(self) -> dict[str, Any]:
        state = self._blank_state()
        if not self.state_path.exists():
            return state
        try:
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return state
        if not isinstance(saved, dict) or saved.get("fleet") != self.profile.id:
            return state
        state.update(saved)
        # A run that was in flight when the process died is not in flight now.
        if state.get("active_run"):
            state["active_run"] = None
            state["active_kind"] = None
            state["active_slug"] = None
        # Never resume into dispatching without a deliberate start.
        if state["status"] == RUNNING and not self.policy.enabled:
            state["status"] = PAUSED
        return state

    def _persist(self) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.state, indent=2, default=str),
                           encoding="utf-8")
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start_thread(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="autopilot",
                                        daemon=True)
        self._thread.start()

    def shutdown(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # an autopilot crash must not be silent
                self._emit("autopilot.error", detail=str(exc))
                self._set_status(HALTED, f"autopilot error: {exc}")
            self._stop.wait(TICK_SECONDS)

    # ── controls ──────────────────────────────────────────────────────────

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.state["status"] in TERMINAL:
                # Clearing a terminal stop is an explicit act, not a resume.
                self.state["failures"] = 0
                if self.state["status"] == BUDGET_REACHED:
                    return self.snapshot()
            self.state["next_action_at"] = 0.0
            self._set_status(RUNNING, "started by operator")
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            self._set_status(PAUSED, "paused by operator")
        return self.snapshot()

    def skip(self) -> dict[str, Any]:
        """Abandon the current objective and move to the next one."""
        with self._lock:
            objective = self.current_objective()
            if objective:
                self._record(objective.slug, "skipped", None)
                self.state["cursor"] += 1
            run_id = self.state.get("active_run")
            self.state["next_action_at"] = 0.0
            self._persist()
        if run_id:
            self.runner.cancel(run_id)
        self._emit("autopilot.skipped")
        return self.snapshot()

    def raise_budget(self, budget_usd: float) -> dict[str, Any]:
        """Lift the ceiling. Deliberately explicit — the fleet cannot do this."""
        if budget_usd <= self.state["spend_estimate"]:
            raise ValueError("new budget must exceed what has already been spent")
        with self._lock:
            self.policy = replace(self.policy, budget_usd=float(budget_usd))
            if self.state["status"] == BUDGET_REACHED:
                self._set_status(PAUSED, "budget raised — start to resume")
            self._persist()
        return self.snapshot()

    # ── the loop body ─────────────────────────────────────────────────────

    def tick(self) -> None:
        with self._lock:
            self._roll_day()

            if self.state.get("active_run"):
                self._check_active()
                return

            if self.state["status"] == BACKOFF:
                if time.time() >= self.state["next_action_at"]:
                    self._set_status(RUNNING, "backoff elapsed")
                return

            if self.state["status"] != RUNNING:
                return

            if self.state["today_missions"] >= self.policy.daily_mission_cap:
                self._set_status(CAPPED, "daily mission cap reached")
                return

            if self._budget_exhausted():
                self._set_status(
                    BUDGET_REACHED,
                    f"estimated spend ${self.state['spend_estimate']:.2f} would exceed "
                    f"the ${self.policy.budget_usd:.2f} ceiling")
                return

            if time.time() < self.state["next_action_at"]:
                return

            if self._optimizer_due():
                self._dispatch_optimizer()
                return

            objective = self._next_unfinished()
            if objective is None:
                self._set_status(BACKLOG_EMPTY, "mission book complete")
                return

            self._dispatch_mission(objective)

    def _next_unfinished(self) -> Objective | None:
        """Advance past anything already complete on disk, then return the next.

        Done in one pass rather than one per tick: a fleet resuming against a
        mostly-finished mission book should reach live work immediately.
        """
        while True:
            objective = self.current_objective()
            if objective is None:
                return None
            if not (self.policy.skip_completed and self._already_done(objective)):
                return objective
            self.state["preexisting"].append(objective.slug)
            self._record(objective.slug, "already on disk", None)
            self.state["cursor"] += 1
            self._persist()

    def _roll_day(self) -> None:
        today = _today()
        if self.state["day"] != today:
            self.state["day"] = today
            self.state["today_missions"] = 0
            if self.state["status"] == CAPPED:
                self._set_status(RUNNING, "new day — cap reset")

    def _budget_exhausted(self) -> bool:
        projected = self.state["spend_estimate"] + self.policy.cost_per_mission
        return projected > self.policy.budget_usd

    def _optimizer_due(self) -> bool:
        """Every `optimize_every` missions, fold QA history back into the prompts."""
        done = self.state["missions"]
        if done == 0:
            return False
        already = len(self.state["optimizations"])
        return done // self.policy.optimize_every > already

    def current_objective(self) -> Objective | None:
        cursor = self.state["cursor"]
        if cursor >= len(self.profile.backlog):
            return None
        return self.profile.backlog[cursor]

    def _already_done(self, objective: Objective) -> bool:
        """True when the topic already has a full set of artifacts on disk."""
        topic_dir = self.store.project_dir / "output" / objective.slug
        if not topic_dir.is_dir():
            return False
        prefixes = ("01_research_brief", "02_book_blueprint", "03_chapter_01",
                    "04_shorts_scripts", "05_funnel_copy")
        return all(any(topic_dir.glob(f"{prefix}_*.md")) for prefix in prefixes)

    # ── dispatch ──────────────────────────────────────────────────────────

    def _dispatch_mission(self, objective: Objective) -> None:
        params = objective.mission_params(no_qa=self.policy.no_qa)
        try:
            run = self.runner.dispatch("mission", params,
                                       simulate=self.policy.mode == "simulate")
        except (DispatchError, ValueError) as exc:
            self._fail(f"{objective.topic}: {exc}", objective.slug)
            return

        self.state["active_run"] = run["id"]
        self.state["active_kind"] = "mission"
        self.state["active_slug"] = objective.slug
        self._persist()
        self._emit("autopilot.dispatched", objective=objective.topic,
                   faculty=objective.faculty, run_id=run["id"], kind="mission",
                   simulated=self.policy.mode == "simulate")

    def _dispatch_optimizer(self) -> None:
        params: dict[str, Any] = {"threshold": self.policy.qa_floor}
        if self.policy.optimize_applies:
            params["apply"] = True
        try:
            run = self.runner.dispatch("optimizer", params,
                                       simulate=self.policy.mode == "simulate")
        except (DispatchError, ValueError) as exc:
            # A missed optimisation pass must not stall the mission book.
            self.state["optimizations"].append({
                "at": time.time(), "missions": self.state["missions"],
                "status": "unavailable", "detail": str(exc),
            })
            self._persist()
            self._emit("autopilot.optimizer_skipped", detail=str(exc))
            return

        self.state["active_run"] = run["id"]
        self.state["active_kind"] = "optimize"
        self.state["active_slug"] = None
        self._persist()
        self._emit("autopilot.dispatched", kind="optimize", run_id=run["id"],
                   applies=self.policy.optimize_applies)

    # ── outcome handling ──────────────────────────────────────────────────

    def _check_active(self) -> None:
        run = self.store.get_run(self.state["active_run"])
        if run is None:
            self._clear_active()
            return
        if run["status"] in ("queued", "running"):
            return

        kind = self.state["active_kind"]
        self._clear_active()

        if kind == "optimize":
            self.state["optimizations"].append({
                "at": time.time(),
                "missions": self.state["missions"],
                "status": run["status"],
                "applied": self.policy.optimize_applies,
            })
            self._schedule_next()
            self._persist()
            self._emit("autopilot.optimized", status=run["status"],
                       applied=self.policy.optimize_applies)
            return

        self._handle_mission_outcome(run)

    def _handle_mission_outcome(self, run: dict[str, Any]) -> None:
        objective = self.current_objective()
        topic = run["params"].get("topic", "")
        slug = objective.slug if objective else re.sub(r"[^a-z0-9_]", "_", topic.lower())
        label = objective.topic if objective else (topic or "mission")

        # Simulated runs cost nothing; only real ones move the spend estimate.
        if self.policy.mode != "simulate":
            self.state["spend_estimate"] += self.policy.cost_per_mission
        self.state["today_missions"] += 1

        scores = [s for s in run.get("scores", {}).values() if isinstance(s, int)]
        average = round(sum(scores) / len(scores), 1) if scores else None

        if run["status"] == ERROR:
            self._fail(f"{label}: run failed ({run.get('error') or 'non-zero exit'})",
                       slug)
            return

        if average is not None and average < self.policy.qa_floor:
            self._handle_weak_result(label, slug, average)
            return

        self.state["missions"] += 1
        self.state["failures"] = 0
        self.state["completed"].append(slug)
        self.state["cursor"] += 1
        self._record(slug, "complete", average)
        self._schedule_next()
        self._persist()
        self._emit("autopilot.completed", objective=label, average=average,
                   missions=self.state["missions"],
                   spend=round(self.state["spend_estimate"], 2))

    def _handle_weak_result(self, label: str, slug: str, average: float) -> None:
        """Below the QA floor: rework once, then quarantine rather than ship."""
        used = self.state["attempts"].get(slug, 0)
        self.state["missions"] += 1
        self.state["failures"] = 0

        if used < self.policy.rework_attempts:
            self.state["attempts"][slug] = used + 1
            self._record(slug, f"rework ({average}/50 below {self.policy.qa_floor})",
                         average)
            self._emit("autopilot.rework", objective=label, average=average,
                       attempt=used + 1)
        else:
            self.state["quarantined"].append(slug)
            self.state["cursor"] += 1
            self._record(slug, f"quarantined ({average}/50)", average)
            self._emit("autopilot.quarantined", objective=label, average=average)

        self._schedule_next()
        self._persist()

    def _fail(self, detail: str, slug: str | None = None) -> None:
        self.state["failures"] += 1
        if slug:
            self._record(slug, f"failed — {detail}", None)
        self._emit("autopilot.failed", detail=detail,
                   consecutive=self.state["failures"])

        if self.state["failures"] >= self.policy.max_consecutive_failures:
            self._set_status(
                HALTED,
                f"{self.state['failures']} consecutive failures — needs a human")
        else:
            wait = self.policy.backoff_seconds * (2 ** (self.state["failures"] - 1))
            self.state["next_action_at"] = time.time() + wait
            self._set_status(BACKOFF, f"retrying in {int(wait)}s — {detail}")
        self._persist()

    def _schedule_next(self) -> None:
        self.state["next_action_at"] = time.time() + self.policy.cadence_seconds

    def _clear_active(self) -> None:
        self.state["active_run"] = None
        self.state["active_kind"] = None
        self.state["active_slug"] = None

    def _record(self, slug: str, outcome: str, score: float | None) -> None:
        self.state["history"].append({
            "at": time.time(), "objective": slug, "outcome": outcome, "score": score,
        })
        self.state["history"] = self.state["history"][-80:]

    # ── reporting ─────────────────────────────────────────────────────────

    def _set_status(self, status: str, detail: str = "") -> None:
        changed = self.state["status"] != status
        self.state["status"] = status
        self.state["detail"] = detail
        self._persist()
        if changed:
            self._emit("autopilot.status", status=status, detail=detail)

    def _emit(self, event_type: str, **payload: Any) -> None:
        self.bus.publish(event_type, agent=AUTOPILOT, fleet=self.profile.id,
                         state=self.snapshot(), **payload)

    def snapshot(self) -> dict[str, Any]:
        objective = self.current_objective()
        backlog = len(self.profile.backlog)
        settled = (len(self.state["completed"]) + len(self.state["quarantined"])
                   + len(self.state["preexisting"]))
        remaining_budget = max(0.0, self.policy.budget_usd - self.state["spend_estimate"])
        return {
            "fleet": {
                "id": self.profile.id,
                "name": self.profile.name,
                "callsign": self.profile.callsign,
                "summary": self.profile.summary,
                "derived_from": self.profile.derived_from,
            },
            "status": self.state["status"],
            "detail": self.state["detail"],
            "mode": self.policy.mode,
            "objective": objective.topic if objective else None,
            "faculty": objective.faculty if objective else None,
            "active_run": self.state["active_run"],
            "active_kind": self.state["active_kind"],
            "cursor": self.state["cursor"],
            "backlog_total": backlog,
            "settled": settled,
            "completed": len(self.state["completed"]),
            "preexisting": len(self.state["preexisting"]),
            "quarantined": len(self.state["quarantined"]),
            "missions": self.state["missions"],
            "failures": self.state["failures"],
            "today_missions": self.state["today_missions"],
            "daily_cap": self.policy.daily_mission_cap,
            "spend_estimate": round(self.state["spend_estimate"], 2),
            "budget_usd": self.policy.budget_usd,
            "budget_remaining": round(remaining_budget, 2),
            "missions_affordable": int(remaining_budget // self.policy.cost_per_mission),
            "cadence_seconds": self.policy.cadence_seconds,
            "next_action_at": self.state["next_action_at"],
            "optimizations": self.state["optimizations"][-10:],
            "optimize_every": self.policy.optimize_every,
            "optimize_applies": self.policy.optimize_applies,
            "qa_floor": self.policy.qa_floor,
            "history": self.state["history"][-20:],
        }


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
