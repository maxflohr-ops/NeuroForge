#!/usr/bin/env python3
"""
Commander HTTP Server
=====================
Standard-library only: no framework, no build step, no new entries in
requirements.txt — the existing Docker image can serve the command center as-is.

Endpoints
    GET  /                     the command center UI
    GET  /api/health           liveness and cursor position
    GET  /api/fleet            agents, squads, readiness, live state
    GET  /api/graph            validated architecture IR
    GET  /api/metrics          QA history and spend roll-up
    GET  /api/topics           topics with output on disk
    GET  /api/runs             recent runs
    GET  /api/runs/<id>        one run, including its log tail
    POST /api/runs             dispatch an agent
    POST /api/runs/<id>/cancel stop a running agent
    GET  /api/events?since=N   Server-Sent Events, replayed from a cursor
"""

from __future__ import annotations

import json
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import graph, registry
from .eventbus import EventBus
from .runner import DispatchError, Runner
from .store import FleetStore

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_BODY_BYTES = 64 * 1024

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}

_RUN_ID = re.compile(r"^run_[a-z0-9]{4,32}$")


class Commander:
    """Wires the pieces together and owns their lifetime."""

    def __init__(self, project_dir: Path, max_concurrent: int = 2,
                 simulate: bool = False, token: str | None = None):
        self.project_dir = project_dir
        self.state_dir = project_dir / "commander" / "state"
        self.bus = EventBus(self.state_dir / "events.jsonl")
        self.store = FleetStore(project_dir, self.state_dir)
        self.runner = Runner(project_dir, self.bus, self.store,
                             max_concurrent=max_concurrent, simulate=simulate)
        self.simulate = simulate
        self.token = token

    def graph_payload(self) -> dict[str, Any]:
        state = {spec.id: self.store.agent_state(spec.id) for spec in registry.AGENTS}
        ir = graph.build(state)
        report = graph.validate(ir)
        return {"ir": ir, "validation": report,
                "registry_errors": registry.validate()}


class Handler(BaseHTTPRequestHandler):
    server_version = "NeuroForgeCommander/1.0"
    protocol_version = "HTTP/1.1"

    # ── plumbing ──────────────────────────────────────────────────────────

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if self.server.verbose:  # type: ignore[attr-defined]
            super().log_message(fmt, *args)

    @property
    def commander(self) -> Commander:  # type: ignore[override]
        return self.server.commander  # type: ignore[attr-defined]

    def _authorised(self, query: dict[str, list[str]]) -> bool:
        token = self.commander.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer ") and header[7:] == token:
            return True
        return query.get("token", [""])[0] == token

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._write(body)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"error": message}, status)

    def _write(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid Content-Length")
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("body must be JSON")
        if not isinstance(parsed, dict):
            raise ValueError("body must be a JSON object")
        return parsed

    # ── routing ───────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"

        if not self._authorised(query):
            self._send_error_json("unauthorised", HTTPStatus.UNAUTHORIZED)
            return

        if route == "/" or route == "/index.html":
            self._serve_file("index.html")
            return

        if route.startswith("/static/"):
            self._serve_file(route[len("/static/"):])
            return

        if route == "/api/health":
            self._send_json({
                "ok": True,
                "cursor": self.commander.bus.seq,
                "simulate": self.commander.simulate,
                "active_runs": self.commander.runner.active_count,
                "watchers": self.commander.bus.subscriber_count,
                "uptime": self.commander.store.metrics()["uptime"],
            })
            return

        if route == "/api/fleet":
            self._send_json(self.commander.store.fleet_snapshot())
            return

        if route == "/api/graph":
            self._send_json(self.commander.graph_payload())
            return

        if route == "/api/metrics":
            self._send_json(self.commander.store.metrics())
            return

        if route == "/api/topics":
            self._send_json({"topics": self.commander.store.topics_on_disk()})
            return

        if route == "/api/runs":
            limit = _int_param(query, "limit", 40, 1, 200)
            self._send_json({"runs": self.commander.store.runs(limit)})
            return

        run_match = re.fullmatch(r"/api/runs/([\w-]+)", route)
        if run_match:
            run = self.commander.store.get_run(run_match.group(1))
            if not run:
                self._send_error_json("no such run", HTTPStatus.NOT_FOUND)
                return
            self._send_json(run)
            return

        if route == "/api/events":
            self._stream_events(_int_param(query, "since", 0, 0, 10**9))
            return

        self._send_error_json("not found", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"

        if not self._authorised(query):
            self._send_error_json("unauthorised", HTTPStatus.UNAUTHORIZED)
            return

        try:
            body = self._read_body()
        except ValueError as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/runs":
            self._dispatch(body)
            return

        cancel = re.fullmatch(r"/api/runs/([\w-]+)/cancel", route)
        if cancel:
            run_id = cancel.group(1)
            if not _RUN_ID.match(run_id):
                self._send_error_json("bad run id", HTTPStatus.BAD_REQUEST)
                return
            stopped = self.commander.runner.cancel(run_id)
            self._send_json({"cancelled": stopped, "run_id": run_id},
                            HTTPStatus.OK if stopped else HTTPStatus.CONFLICT)
            return

        self._send_error_json("not found", HTTPStatus.NOT_FOUND)

    # ── handlers ──────────────────────────────────────────────────────────

    def _dispatch(self, body: dict[str, Any]) -> None:
        agent_id = str(body.get("agent", "")).strip()
        params = body.get("params") or {}
        if not isinstance(params, dict):
            self._send_error_json("params must be an object", HTTPStatus.BAD_REQUEST)
            return

        simulate = body.get("simulate")
        if simulate is not None:
            simulate = bool(simulate)

        try:
            run = self.commander.runner.dispatch(agent_id, params, simulate=simulate)
        except DispatchError as exc:
            self._send_error_json(str(exc), HTTPStatus.CONFLICT)
            return
        except (ValueError, KeyError) as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"run": {k: v for k, v in run.items() if k != "log"}},
                        HTTPStatus.ACCEPTED)

    def _stream_events(self, since: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        if not self._write(b": connected\n\n"):
            return

        for event in self.commander.bus.stream(since):
            frame = f"data: {json.dumps(event, default=str)}\n\n".encode("utf-8")
            if not self._write(frame):
                return

    def _serve_file(self, relative: str) -> None:
        # Resolve inside WEB_DIR only — no traversal out of the asset directory.
        candidate = (WEB_DIR / relative).resolve()
        try:
            candidate.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._send_error_json("forbidden", HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            self._send_error_json("not found", HTTPStatus.NOT_FOUND)
            return

        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type",
                         CONTENT_TYPES.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._write(body)


def _int_param(query: dict[str, list[str]], name: str, default: int,
               low: int, high: int) -> int:
    try:
        value = int(query.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


class CommanderServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], commander: Commander,
                 verbose: bool = False):
        self.commander = commander
        self.verbose = verbose
        super().__init__(address, Handler)


def serve(project_dir: Path, host: str = "127.0.0.1", port: int = 8787,
          max_concurrent: int = 2, simulate: bool = False,
          token: str | None = None, verbose: bool = False) -> CommanderServer:
    """Start the commander. Returns the server so callers can shut it down."""
    commander = Commander(project_dir, max_concurrent=max_concurrent,
                          simulate=simulate, token=token)
    server = CommanderServer((host, port), commander, verbose=verbose)

    report = commander.graph_payload()
    if not report["validation"]["ok"] or report["registry_errors"]:
        for error in report["registry_errors"] + report["validation"]["errors"]:
            print(f"  ✗ {error}")
        raise RuntimeError("fleet map failed validation — refusing to serve")

    thread = threading.Thread(target=server.serve_forever, name="commander-http",
                              daemon=True)
    thread.start()
    return server
