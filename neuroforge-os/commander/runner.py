#!/usr/bin/env python3
"""
Run Supervisor
==============
Launches agents as subprocesses, streams their output through the interpreter,
and turns what comes back into fleet state and live events.

Safety properties worth keeping if you extend this:

  * Commands are argv lists built from the registry — never a shell string, so
    a topic name cannot become a command.
  * Every parameter is validated against its ParamSpec before it is used.
  * Only agents declared in the registry can be launched at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import registry
from .eventbus import (ARTIFACT, EventBus, FLEET, METRIC, RUN_CANCELLED,
                       RUN_FINISHED, RUN_LOG, RUN_QUEUED, RUN_STARTED,
                       STAGE_FINISHED, STAGE_STARTED)
from .interpreter import LogInterpreter
from .store import ERROR, FleetStore, OK, QUEUED, RUNNING, WARN

TERMINATE_GRACE_SECONDS = 5.0


class DispatchError(ValueError):
    """A dispatch that should never have been attempted."""


class Runner:
    def __init__(self, project_dir: Path, bus: EventBus, store: FleetStore,
                 max_concurrent: int = 2, simulate: bool = False):
        self.project_dir = project_dir
        self.bus = bus
        self.store = store
        self.simulate = simulate
        self._slots = threading.Semaphore(max_concurrent)
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._cancelled: set[str] = set()
        self._shutting_down = threading.Event()

    # ── dispatch ──────────────────────────────────────────────────────────

    def dispatch(self, agent_id: str, params: dict[str, Any] | None = None,
                 simulate: bool | None = None) -> dict[str, Any]:
        """Validate, queue and start an agent run. Returns the run record."""
        try:
            spec = registry.get(agent_id)
        except KeyError as exc:
            raise DispatchError(str(exc)) from exc

        if not spec.dispatchable:
            raise DispatchError(f"{spec.name} is not a launchable agent")

        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        argv = spec.build_argv(params)  # raises ValueError on bad params

        use_sim = self.simulate if simulate is None else simulate
        if not use_sim:
            missing = registry.missing_env(spec)
            if missing:
                raise DispatchError(
                    f"{spec.name} needs {', '.join(missing)}. Set it in .env, "
                    f"or launch in simulation mode to rehearse the run."
                )

        run_id = f"run_{uuid.uuid4().hex[:10]}"
        resolved = self._simulated_argv(spec, params) if use_sim else self._resolve(argv)
        run = self.store.create_run(run_id, agent_id, params, resolved, simulated=use_sim)

        self.bus.publish(RUN_QUEUED, run_id=run_id, agent=agent_id,
                         agent_name=spec.name, params=params, simulated=use_sim)
        self._publish_fleet(agent_id, QUEUED, run_id, "queued")

        thread = threading.Thread(target=self._supervise, args=(run, spec),
                                  name=f"run-{run_id}", daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()
        return run

    def _resolve(self, argv: list[str]) -> list[str]:
        """Use the interpreter running the commander rather than bare `python`."""
        resolved = list(argv)
        if resolved and resolved[0] in ("python", "python3"):
            resolved[0] = sys.executable
        return resolved

    def _simulated_argv(self, spec: registry.AgentSpec,
                        params: dict[str, Any]) -> list[str]:
        argv = [sys.executable, "-m", "commander.simulator", "--agent", spec.id]
        for key in ("topic", "faculty"):
            if params.get(key):
                argv.extend([f"--{key}", str(params[key])])
        if params.get("no_qa"):
            argv.append("--no-qa")
        return argv

    # ── supervision ───────────────────────────────────────────────────────

    def _supervise(self, run: dict[str, Any], spec: registry.AgentSpec) -> None:
        run_id = run["id"]
        self._slots.acquire()
        try:
            if self._shutting_down.is_set():
                self._finalise(run_id, spec, ERROR, None, "commander shutting down")
                return
            self._execute(run, spec)
        except Exception as exc:  # a supervisor crash must not be silent
            self.store.append_log(run_id, f"commander error: {exc}", "error")
            self.bus.publish(RUN_LOG, run_id=run_id, agent=spec.id,
                             line=f"commander error: {exc}", level="error")
            self._finalise(run_id, spec, ERROR, None, str(exc))
        finally:
            self._slots.release()

    def _execute(self, run: dict[str, Any], spec: registry.AgentSpec) -> None:
        run_id = run["id"]
        argv = run["argv"]

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["NEUROFORGE_RUN_ID"] = run_id
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(self.project_dir), env.get("PYTHONPATH", "")])
        )

        self.store.update_run(run_id, status=RUNNING, started_at=time.time())
        self.bus.publish(RUN_STARTED, run_id=run_id, agent=spec.id,
                         agent_name=spec.name, argv=argv,
                         simulated=run.get("simulated", False))
        self._publish_fleet(spec.id, RUNNING, run_id, "running")

        try:
            process = subprocess.Popen(
                argv, cwd=str(self.project_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except (OSError, ValueError) as exc:
            self._finalise(run_id, spec, ERROR, None, f"could not launch: {exc}")
            return

        with self._lock:
            self._processes[run_id] = process

        interpreter = LogInterpreter(spec.id)
        touched: set[str] = set()
        worst_level = "info"

        assert process.stdout is not None
        with process.stdout as stream:
            for raw_line in stream:
                for event in interpreter.feed(raw_line):
                    level = self._apply(run_id, spec, event, touched)
                    if level == "error":
                        worst_level = "error"
                    elif level == "warn" and worst_level != "error":
                        worst_level = "warn"

        exit_code = process.wait()
        with self._lock:
            self._processes.pop(run_id, None)

        closing_status = OK if exit_code == 0 else ERROR
        for event in interpreter.close(closing_status):
            self._apply(run_id, spec, event, touched)

        if run_id in self._cancelled:
            status = "cancelled"
        elif exit_code != 0:
            status = ERROR
        elif worst_level == "warn":
            status = WARN
        else:
            status = OK

        for agent_id in touched - {spec.id}:
            self._publish_fleet(agent_id, OK if status != ERROR else ERROR,
                                run_id, "finished")

        self._finalise(run_id, spec, status, exit_code, None)

    def _apply(self, run_id: str, spec: registry.AgentSpec,
               event: dict[str, Any], touched: set[str]) -> str:
        """Route one interpreted event into the store and the bus."""
        kind = event.get("kind")
        agent_id = event.get("agent") or spec.id
        if agent_id in registry.AGENTS_BY_ID:
            touched.add(agent_id)

        if kind == "log":
            level = event.get("level", "info")
            self.store.append_log(run_id, event["line"], level)
            self.bus.publish(RUN_LOG, run_id=run_id, agent=agent_id,
                             line=event["line"], level=level)
            return level

        if kind == "stage_start":
            stage = event.get("stage", "stage")
            self.store.start_stage(run_id, stage, agent_id)
            self.bus.publish(STAGE_STARTED, run_id=run_id, agent=agent_id,
                             stage=stage, detail=event.get("detail", ""))
            if agent_id in registry.AGENTS_BY_ID:
                self._publish_fleet(agent_id, RUNNING, run_id, stage)
            return "info"

        if kind == "stage_end":
            stage = event.get("stage", "stage")
            status = event.get("status", OK)
            self.store.finish_stage(run_id, stage, status)
            self.bus.publish(STAGE_FINISHED, run_id=run_id, agent=agent_id,
                             stage=stage, status=status)
            if agent_id in registry.AGENTS_BY_ID:
                self._publish_fleet(agent_id, status, run_id, f"{stage} done")
            return "info"

        if kind == "stage_skipped":
            stage = event.get("stage", "stage")
            self.store.start_stage(run_id, stage, agent_id)
            self.store.finish_stage(run_id, stage, "skipped")
            self.bus.publish(STAGE_FINISHED, run_id=run_id, agent=agent_id,
                             stage=stage, status="skipped")
            return "info"

        if kind == "artifact":
            path = event.get("path", "")
            self.store.add_artifact(run_id, path)
            self.bus.publish(ARTIFACT, run_id=run_id, agent=agent_id, path=path,
                             is_qa=event.get("is_qa", False))
            return "info"

        if kind == "score":
            score = int(event.get("score", 0))
            label = event.get("label", "QA")
            if not event.get("rollup"):
                self.store.add_score(run_id, label, score)
                self.store.score_current_stage(
                    run_id, score, WARN if event.get("failed") else OK)
            self.bus.publish(METRIC, run_id=run_id, agent=agent_id, metric="qa_score",
                             label=label, value=score, rollup=event.get("rollup", False),
                             failed=event.get("failed", False))
            if agent_id in registry.AGENTS_BY_ID and not event.get("rollup"):
                self._publish_fleet(
                    agent_id, WARN if event.get("failed") else OK, run_id,
                    f"{label} {score}/50", score=score)
            return "warn" if event.get("failed") else "info"

        return "info"

    def _finalise(self, run_id: str, spec: registry.AgentSpec, status: str,
                  exit_code: int | None, error: str | None) -> None:
        self.store.update_run(run_id, status=status, finished_at=time.time(),
                              exit_code=exit_code, error=error)
        run = self.store.get_run(run_id) or {}
        duration = None
        if run.get("started_at"):
            duration = (run.get("finished_at") or time.time()) - run["started_at"]

        event_type = RUN_CANCELLED if status == "cancelled" else RUN_FINISHED
        self.bus.publish(event_type, run_id=run_id, agent=spec.id,
                         agent_name=spec.name, status=status, exit_code=exit_code,
                         error=error, duration=duration,
                         scores=run.get("scores", {}),
                         artifacts=run.get("artifacts", []))
        detail = error or (f"exit {exit_code}" if exit_code else status)
        self._publish_fleet(spec.id, status if status in (OK, WARN, ERROR) else OK,
                            None, detail)
        self._cancelled.discard(run_id)

    def _publish_fleet(self, agent_id: str, status: str, run_id: str | None,
                       detail: str, score: int | None = None) -> None:
        state = self.store.set_agent_status(agent_id, status, run_id, detail, score)
        self.bus.publish(FLEET, agent=agent_id, status=status, run_id=run_id,
                         detail=detail, state=state)

    # ── control ───────────────────────────────────────────────────────────

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            process = self._processes.get(run_id)
        if not process:
            return False
        self._cancelled.add(run_id)
        process.terminate()
        deadline = time.time() + TERMINATE_GRACE_SECONDS
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            process.kill()
        return True

    def shutdown(self, timeout: float = 10.0) -> None:
        """Stop accepting work and end anything still running."""
        self._shutting_down.set()
        with self._lock:
            live = list(self._processes.items())
        for run_id, process in live:
            self._cancelled.add(run_id)
            if process.poll() is None:
                process.terminate()
        deadline = time.time() + timeout
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            remaining = max(0.0, deadline - time.time())
            thread.join(timeout=remaining)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._processes)
