#!/usr/bin/env python3
"""
NeuroForge Agent Commander — entry point.

    python -m commander                      # localhost:8787
    python -m commander --simulate           # rehearse without API keys
    python -m commander --host 0.0.0.0 --token $(openssl rand -hex 16)

Runs on the standard library alone, so `docker compose run commander` works
against the existing image with no extra dependencies.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Allow `python commander/__main__.py` as well as `python -m commander`.
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_DIR))
    __package__ = "commander"

from commander import registry  # noqa: E402
from commander.server import serve  # noqa: E402

BANNER = r"""
  ███  NEUROFORGE COMMAND CENTER
  Agent commander + real-time fleet visualisation
"""


def load_dotenv(path: Path) -> int:
    """Load .env into the environment without overwriting real env vars."""
    if not path.exists():
        return 0
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NeuroForge Agent Commander and visual command center")
    parser.add_argument("--host", default=os.getenv("COMMANDER_HOST", "127.0.0.1"),
                        help="Bind address (default: loopback only)")
    parser.add_argument("--port", type=int,
                        default=int(os.getenv("COMMANDER_PORT", "8787")))
    parser.add_argument("--max-concurrent", type=int,
                        default=int(os.getenv("COMMANDER_MAX_CONCURRENT", "2")),
                        help="How many agents may run at once")
    parser.add_argument("--simulate", action="store_true",
                        default=os.getenv("COMMANDER_SIMULATE", "") not in ("", "0"),
                        help="Dispatch simulated runs instead of real agents")
    parser.add_argument("--token", default=os.getenv("COMMANDER_TOKEN"),
                        help="Require this bearer token on every request")
    parser.add_argument("--no-env", action="store_true",
                        help="Skip loading .env")
    parser.add_argument("--verbose", action="store_true",
                        help="Log every HTTP request")
    args = parser.parse_args()

    if not args.no_env:
        loaded = load_dotenv(PROJECT_DIR / ".env")
        if loaded:
            print(f"  loaded {loaded} variable(s) from .env")

    errors = registry.validate()
    if errors:
        for error in errors:
            print(f"  ✗ registry: {error}", file=sys.stderr)
        return 1

    try:
        server = serve(PROJECT_DIR, host=args.host, port=args.port,
                       max_concurrent=args.max_concurrent,
                       simulate=args.simulate, token=args.token,
                       verbose=args.verbose)
    except OSError as exc:
        print(f"  ✗ cannot bind {args.host}:{args.port} — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"  ✗ {exc}", file=sys.stderr)
        return 1

    dispatchable = [a for a in registry.AGENTS if a.dispatchable]
    ready = [a for a in dispatchable if not registry.missing_env(a)]

    print(BANNER)
    print(f"  fleet      {len(registry.AGENTS)} agents · "
          f"{len(dispatchable)} launchable · {len(ready)} credentialled")
    print(f"  mode       {'SIMULATION — no API calls, no writes' if args.simulate else 'LIVE'}")
    print(f"  auth       {'bearer token required' if args.token else 'open (loopback)'}")
    print(f"  console    http://{args.host}:{args.port}/")
    print("\n  Ctrl-C to stop.\n")

    if not args.simulate and len(ready) < len(dispatchable):
        blocked = len(dispatchable) - len(ready)
        print(f"  note: {blocked} agent(s) lack credentials and are shown dark on "
              f"the map.\n        Run with --simulate to rehearse them.\n")

    stop = threading.Event()

    def shutdown(signum, frame):  # noqa: ANN001, ARG001
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        stop.wait()
    finally:
        print("\n  stopping agents…")
        server.commander.runner.shutdown()
        server.shutdown()
        server.server_close()
        print("  fleet stood down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
