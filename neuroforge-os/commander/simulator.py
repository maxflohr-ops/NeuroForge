#!/usr/bin/env python3
"""
Fleet Simulator
===============
Replays a realistic agent run without spending a token or touching a remote
system. It prints exactly the shapes the real agents print, so the interpreter,
the event bus and the map are all exercised for real — only the model calls are
imaginary.

Useful for demoing the command center, for rehearsing a mission before paying
for it, and as a fixture for the test suite.

    python -m commander.simulator --agent mission --topic "Stop Overthinking"
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime

from . import registry

# Each forge stage: banner glyph, banner name, detail, output prefix, QA label.
FORGE_STAGES = (
    ("🔬", "RESEARCH AGENT", "Starting", "01_research_brief",
     "Research Brief", "Research Agent"),
    ("📐", "BOOK ARCHITECT AGENT", "Starting", "02_book_blueprint",
     "Book Blueprint", "Book Architect Agent"),
    ("✍️ ", "MANUSCRIPT AGENT", "Chapter 1", "03_chapter_01",
     "Manuscript Chapter", "Manuscript Agent"),
    ("🎬", "SHORTS SCRIPT AGENT", "20 scripts", "04_shorts_scripts",
     "Short-Form Scripts", "Shorts Script Agent"),
    ("💰", "FUNNEL AGENT", "Starting", "05_funnel_copy",
     "Funnel Copy", "Funnel Agent"),
)

AGENT_TO_STAGE = {
    "research": 0,
    "architect": 1,
    "manuscript": 2,
    "shorts": 3,
    "funnel": 4,
}

MODEL = "claude-sonnet-4-6"


def _speed() -> float:
    try:
        return max(0.02, float(os.getenv("COMMANDER_SIM_SPEED", "1")))
    except ValueError:
        return 1.0


def emit(line: str = "") -> None:
    print(line, flush=True)


def beat(seconds: float) -> None:
    time.sleep(seconds / _speed())


def slug(topic: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_stage(index: int, topic: str, faculty: str, no_qa: bool,
              rng: random.Random) -> int | None:
    glyph, name, detail, prefix, qa_label, call_label = FORGE_STAGES[index]

    emit()
    emit(f"{glyph} {name} — {detail}")
    beat(0.4)
    emit("─" * 50)
    emit(f"  Calling: {call_label}")
    emit(f"  Model:   {MODEL}")
    emit("─" * 50)
    beat(1.4)

    path = f"./output/{slug(topic)}/{prefix}_{stamp()}.md"
    emit(f"  ✓ Saved: {path}")

    if no_qa:
        return None

    beat(0.5)
    emit()
    emit(f"🔍 QA AGENT — Reviewing {qa_label}")
    emit("─" * 50)
    emit("  Calling: QA Agent")
    emit(f"  Model:   {MODEL}")
    emit("─" * 50)
    beat(1.0)

    score = rng.choice([36, 38, 39, 41, 42, 43, 44, 45, 46, 47])
    emit(f"  ✓ Saved: ./output/{slug(topic)}/{prefix}_QA_{stamp()}.md")
    emit(f"\n✅ {qa_label} complete. QA Score: {score}/50")
    return score


def simulate_mission(topic: str, faculty: str, no_qa: bool,
                     rng: random.Random) -> int:
    emit("=" * 60)
    emit("  NEUROFORGE OS — FULL PIPELINE  [SIMULATED]")
    emit(f"  Topic:   {topic}")
    emit(f"  Faculty: {faculty}")
    emit(f"  QA:      {'disabled' if no_qa else 'enabled'}")
    emit("=" * 60)

    scores: dict[str, int] = {}
    for index in range(len(FORGE_STAGES)):
        score = run_stage(index, topic, faculty, no_qa, rng)
        if score is not None:
            scores[FORGE_STAGES[index][4]] = score

    emit()
    emit("=" * 60)
    emit(f"  PIPELINE COMPLETE — {topic}")
    emit("=" * 60)
    if no_qa:
        emit("  QA skipped — run --mode qa --file <path> to QA any output individually.")
    else:
        for label, score in scores.items():
            emit(f"  {label:<20} {score}/50")
        emit(f"\n  Average QA Score:     {sum(scores.values()) // len(scores)}/50")
    emit(f"\n  All outputs saved to: ./output/{slug(topic)}/")
    emit("=" * 60)
    return 0


def simulate_sync(agent_id: str, topic: str, rng: random.Random) -> int:
    spec = registry.get(agent_id)
    emit(f"📡 {spec.name} — simulated sync")
    steps = (
        ("Connecting", f"{spec.name} handshake"),
        ("Reading", f"local state for {topic or 'all topics'}"),
        ("Writing", "records to the remote system"),
        ("Verifying", "remote acknowledgements"),
    )
    for index, (label, detail) in enumerate(steps, 1):
        beat(0.7)
        emit(f"{index}️⃣ Step {index}: {label} — {detail}")
        beat(0.5)
        emit(f"✓ [{datetime.now().strftime('%H:%M:%S')}] {label} complete "
             f"({rng.randint(2, 24)} records)")
    emit(f"\n✓ {spec.name} sync complete (simulated — nothing was written)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate an agent run")
    parser.add_argument("--agent", default="mission", help="Registry agent id")
    parser.add_argument("--topic", default="Stop Overthinking")
    parser.add_argument("--faculty", default=registry.FACULTY[0])
    parser.add_argument("--no-qa", action="store_true", dest="no_qa")
    args = parser.parse_args()

    try:
        spec = registry.get(args.agent)
    except KeyError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    # Deterministic per topic+agent so repeat rehearsals are comparable.
    rng = random.Random(f"{args.agent}:{args.topic}")

    if args.agent == "mission":
        return simulate_mission(args.topic, args.faculty, args.no_qa, rng)

    if args.agent in AGENT_TO_STAGE:
        emit(f"  [SIMULATED] {spec.name} — {args.topic}")
        run_stage(AGENT_TO_STAGE[args.agent], args.topic, args.faculty,
                  args.no_qa, rng)
        emit(f"\n✅ {spec.name} complete.")
        return 0

    return simulate_sync(args.agent, args.topic, rng)


if __name__ == "__main__":
    raise SystemExit(main())
