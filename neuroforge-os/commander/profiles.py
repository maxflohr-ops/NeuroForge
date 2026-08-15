#!/usr/bin/env python3
"""
Fleet Profiles
==============
Cloning a fleet means giving it its own identity, mission book and operating
policy — not copying the code. The agent topology in `registry.py` is the
architecture; a profile is one deployment of it.

    commander/fleets/neuroforge.json     the base fleet
    commander/fleets/florra_alpha.json   Florra Fleet Alpha, derived from it

A derived profile inherits everything from its parent and overrides only what
differs, so architectural fixes reach every fleet while each keeps its own
backlog, budget and cadence.

    python -m commander.profiles --list
    python -m commander.profiles --show florra_alpha
    python -m commander.profiles --clone florra_alpha --as florra_beta
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import registry

FLEET_DIR = Path(__file__).resolve().parent / "fleets"
DEFAULT_FLEET = "florra_alpha"

# Cost model from the project README: ~12 API calls and ~$0.17 per full topic.
COST_PER_MISSION_USD = 0.17
COST_PER_MISSION_NO_QA_USD = 0.11

_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


@dataclass(frozen=True)
class AutopilotPolicy:
    """The rules the fleet runs itself by. Every rail defaults to the safe side."""

    enabled: bool = False              # never self-starts unless asked
    mode: str = "simulate"             # simulate | live
    cadence_seconds: int = 900         # gap between missions
    budget_usd: float = 5.0            # hard ceiling on estimated spend
    daily_mission_cap: int = 6
    qa_floor: int = 35                 # below this a topic is reworked
    rework_attempts: int = 1
    optimize_every: int = 10           # missions between optimizer passes
    optimize_applies: bool = False     # propose rewrites; do not overwrite prompts
    max_consecutive_failures: int = 3
    backoff_seconds: int = 300
    skip_completed: bool = True        # don't redo topics already on disk
    no_qa: bool = False                # QA is what makes the loop self-improving

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutopilotPolicy:
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown autopilot setting(s): {', '.join(sorted(unknown))}")
        policy = cls(**{k: v for k, v in data.items() if k in known})
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.mode not in ("simulate", "live"):
            raise ValueError(f"autopilot mode must be simulate or live, not {self.mode!r}")
        if self.cadence_seconds < 30:
            raise ValueError("cadence_seconds must be at least 30")
        if self.budget_usd <= 0:
            raise ValueError("budget_usd must be positive — an unbounded fleet is not shippable")
        if self.daily_mission_cap < 1:
            raise ValueError("daily_mission_cap must be at least 1")
        if not 0 <= self.qa_floor <= 50:
            raise ValueError("qa_floor must be between 0 and 50")
        if self.optimize_every < 1:
            raise ValueError("optimize_every must be at least 1")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")

    @property
    def cost_per_mission(self) -> float:
        return COST_PER_MISSION_NO_QA_USD if self.no_qa else COST_PER_MISSION_USD

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


@dataclass(frozen=True)
class Objective:
    """One item of the mission book: a topic and the faculty voice that writes it."""

    topic: str
    faculty: str
    pillar: str = ""
    note: str = ""

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9_]", "_", self.topic.lower())

    def to_dict(self) -> dict[str, Any]:
        data = {"topic": self.topic, "faculty": self.faculty}
        if self.pillar:
            data["pillar"] = self.pillar
        if self.note:
            data["note"] = self.note
        return data

    def mission_params(self, no_qa: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"topic": self.topic, "faculty": self.faculty}
        if self.pillar:
            params["pillar"] = self.pillar
        if no_qa:
            params["no_qa"] = True
        return params


@dataclass(frozen=True)
class FleetProfile:
    """One deployment of the agent architecture."""

    id: str
    name: str
    callsign: str
    summary: str = ""
    derived_from: str | None = None
    backlog: tuple[Objective, ...] = ()
    autopilot: AutopilotPolicy = field(default_factory=AutopilotPolicy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "callsign": self.callsign,
            "summary": self.summary,
            "derived_from": self.derived_from,
            "backlog": [item.to_dict() for item in self.backlog],
            "autopilot": self.autopilot.to_dict(),
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not _ID.match(self.id):
            errors.append(f"fleet id {self.id!r} must be lowercase snake_case")
        if not self.name.strip():
            errors.append("fleet name is required")
        if not self.callsign.strip():
            errors.append("fleet callsign is required")

        seen: set[str] = set()
        for item in self.backlog:
            if item.faculty not in registry.FACULTY:
                errors.append(f"{item.topic}: unknown faculty {item.faculty!r}")
            if item.slug in seen:
                errors.append(f"duplicate backlog topic: {item.topic}")
            seen.add(item.slug)
            try:
                registry.get("mission").build_argv(item.mission_params())
            except ValueError as exc:
                errors.append(f"{item.topic}: not dispatchable — {exc}")

        try:
            self.autopilot.validate()
        except ValueError as exc:
            errors.append(str(exc))
        return errors


# ── loading ───────────────────────────────────────────────────────────────

def _read(fleet_id: str) -> dict[str, Any]:
    path = FLEET_DIR / f"{fleet_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no such fleet profile: {fleet_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def load(fleet_id: str = DEFAULT_FLEET, _seen: tuple[str, ...] = ()) -> FleetProfile:
    """Load a profile, resolving inheritance from its parent fleet."""
    if not _ID.match(fleet_id):
        raise ValueError(f"invalid fleet id: {fleet_id!r}")
    if fleet_id in _seen:
        raise ValueError(f"circular fleet inheritance: {' → '.join((*_seen, fleet_id))}")

    data = _read(fleet_id)
    parent_id = data.get("derived_from")

    if parent_id:
        parent = load(parent_id, _seen=(*_seen, fleet_id))
        merged = parent.to_dict()
        # Inherit, then override: a derived fleet states only what differs.
        merged.update({k: v for k, v in data.items() if k != "autopilot"})
        merged["autopilot"] = {**parent.autopilot.to_dict(),
                               **(data.get("autopilot") or {})}
        data = merged

    backlog = tuple(
        Objective(
            topic=str(item["topic"]),
            faculty=str(item["faculty"]),
            pillar=str(item.get("pillar", "")),
            note=str(item.get("note", "")),
        )
        for item in data.get("backlog", [])
        if isinstance(item, dict) and item.get("topic") and item.get("faculty")
    )

    profile = FleetProfile(
        id=str(data.get("id", fleet_id)),
        name=str(data.get("name", fleet_id)),
        callsign=str(data.get("callsign", fleet_id[:3].upper())),
        summary=str(data.get("summary", "")),
        derived_from=parent_id,
        backlog=backlog,
        autopilot=AutopilotPolicy.from_dict(data.get("autopilot") or {}),
    )

    errors = profile.validate()
    if errors:
        raise ValueError(f"fleet '{fleet_id}' is invalid:\n  " + "\n  ".join(errors))
    return profile


def available() -> list[str]:
    if not FLEET_DIR.exists():
        return []
    return sorted(path.stem for path in FLEET_DIR.glob("*.json"))


def clone(source_id: str, new_id: str, name: str | None = None,
          callsign: str | None = None) -> Path:
    """Write a new profile deriving from an existing one. Returns its path."""
    if not _ID.match(new_id):
        raise ValueError(f"invalid fleet id: {new_id!r}")
    target = FLEET_DIR / f"{new_id}.json"
    if target.exists():
        raise FileExistsError(f"fleet '{new_id}' already exists")
    load(source_id)  # fail before writing if the source is unsound

    FLEET_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "id": new_id,
        "name": name or new_id.replace("_", " ").title(),
        "callsign": callsign or new_id[:3].upper(),
        "derived_from": source_id,
        "summary": f"Derived from {source_id}.",
        "autopilot": {"enabled": False, "mode": "simulate"},
    }, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fleet profiles")
    parser.add_argument("--list", action="store_true", help="List available fleets")
    parser.add_argument("--show", metavar="FLEET", help="Print a resolved profile")
    parser.add_argument("--validate", action="store_true", help="Validate every fleet")
    parser.add_argument("--clone", metavar="SOURCE", help="Clone an existing fleet")
    parser.add_argument("--as", dest="new_id", metavar="ID", help="Id for the clone")
    parser.add_argument("--name", help="Display name for the clone")
    args = parser.parse_args()

    if args.clone:
        if not args.new_id:
            print("--clone requires --as <id>")
            return 2
        path = clone(args.clone, args.new_id, args.name)
        shown = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        print(f"✓ wrote {shown}")
        return 0

    if args.show:
        print(json.dumps(load(args.show).to_dict(), indent=2))
        return 0

    if args.validate or args.list or True:
        ok = True
        for fleet_id in available():
            try:
                profile = load(fleet_id)
            except (ValueError, FileNotFoundError) as exc:
                ok = False
                print(f"✗ {fleet_id}: {exc}")
                continue
            pending = len(profile.backlog)
            policy = profile.autopilot
            print(f"✓ {profile.id:<16} {profile.name:<22} [{profile.callsign}] "
                  f"{pending} objective(s) · autopilot "
                  f"{'on' if policy.enabled else 'off'}/{policy.mode} · "
                  f"${policy.budget_usd:.2f} ceiling")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
