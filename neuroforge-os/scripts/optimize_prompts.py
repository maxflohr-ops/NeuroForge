#!/usr/bin/env python3
"""
NeuroForge OS — Prompt Optimizer
=================================
Reads QA logs from neuroforge_db.json, identifies underperforming agents,
and uses Claude to rewrite their prompts based on the failure patterns.

This is the "self-improving" layer of NeuroForge OS.

Usage:
    python optimize_prompts.py                  # analyse all agents
    python optimize_prompts.py --agent research # analyse one agent
    python optimize_prompts.py --apply          # apply rewrites (saves new versions)

Run this after every 5–10 completed topics to improve the system.
"""

import anthropic
import argparse
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

MODEL = "claude-sonnet-4-20250514"
DB_FILE = Path("./neuroforge_db.json")
PROMPT_DIR = Path("./prompts")
VERSIONS_DIR = Path("./prompts/versions")

AGENT_MAP = {
    "research":   "01_research_agent.md",
    "blueprint":  "02_book_architect_agent.md",
    "manuscript": "03_manuscript_agent.md",
    "scripts":    "04_shorts_script_agent.md",
    "funnel":     "05_funnel_agent.md",
    "qa":         "06_qa_agent.md",
}

AGENT_NAME_MAP = {
    "Research Agent":          "research",
    "Book Architect Agent":    "blueprint",
    "Manuscript Agent Ch1":    "manuscript",
    "Manuscript Agent Ch2":    "manuscript",
    "Manuscript Agent Ch3":    "manuscript",
    "Shorts Script Agent":     "scripts",
    "Funnel Agent":            "funnel",
}


def load_db():
    if not DB_FILE.exists():
        print("No database found. Run the pipeline on at least 3 topics first.")
        return []
    with open(DB_FILE) as f:
        return json.load(f)


def load_qa_notes(topic_dir: Path, agent_key: str) -> list[str]:
    """Load QA Prompt Improvement Notes from output files."""
    notes = []
    if not topic_dir.exists():
        return notes

    for qa_file in topic_dir.glob(f"*{agent_key}*QA*.md"):
        content = qa_file.read_text(encoding="utf-8")
        # Extract the Prompt Improvement Note section
        match = re.search(r"### PROMPT IMPROVEMENT NOTE\n(.+?)(?:\n---|\Z)", content, re.DOTALL)
        if match:
            notes.append(match.group(1).strip())

    return notes


def analyse_performance(db: list, agent_filter: str = None) -> dict:
    """
    Summarise QA scores and collect failure notes per agent.
    Returns dict: agent_key -> {scores, avg, notes, low_runs}
    """
    agent_data = defaultdict(lambda: {"scores": [], "notes": [], "topics": []})

    for record in db:
        agent_raw = record.get("agent", "")
        agent_key = AGENT_NAME_MAP.get(agent_raw)
        if not agent_key:
            continue
        if agent_filter and agent_key != agent_filter:
            continue

        score = record.get("qa_score")
        if score is not None:
            agent_data[agent_key]["scores"].append(score)
            agent_data[agent_key]["topics"].append(record.get("topic", "unknown"))

        # Try to load QA notes from the output file
        output_file = record.get("output_file", "")
        if output_file:
            qa_file = Path(output_file).parent / (Path(output_file).stem + "_QA.md")
            if qa_file.exists():
                content = qa_file.read_text(encoding="utf-8")
                match = re.search(r"### PROMPT IMPROVEMENT NOTE\n(.+?)(?:\n---|\Z)", content, re.DOTALL)
                if match:
                    agent_data[agent_key]["notes"].append(match.group(1).strip())

    # Compute averages
    results = {}
    for key, data in agent_data.items():
        scores = data["scores"]
        results[key] = {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "min_score": min(scores) if scores else None,
            "max_score": max(scores) if scores else None,
            "run_count": len(scores),
            "low_runs": [s for s in scores if s < 40],
            "notes": data["notes"],
            "topics": data["topics"],
        }

    return results


def print_performance_report(analysis: dict):
    print("\n" + "=" * 60)
    print("  NEUROFORGE OS — AGENT PERFORMANCE REPORT")
    print("=" * 60)
    print(f"  {'Agent':<25} {'Avg':>6} {'Min':>6} {'Max':>6} {'Runs':>6} {'Low Runs':>10}")
    print("  " + "─" * 58)

    for key, data in sorted(analysis.items(), key=lambda x: (x[1]["avg_score"] or 0)):
        avg = f"{data['avg_score']}/50" if data["avg_score"] else "N/A"
        min_s = f"{data['min_score']}" if data["min_score"] else "N/A"
        max_s = f"{data['max_score']}" if data["max_score"] else "N/A"
        runs = str(data["run_count"])
        low = str(len(data["low_runs"]))

        flag = " ⚠️" if data["avg_score"] and data["avg_score"] < 38 else ""
        print(f"  {key:<25} {avg:>6} {min_s:>6} {max_s:>6} {runs:>6} {low:>10}{flag}")

    print("=" * 60)
    print("  ⚠️  = below 38/50 average — candidate for optimisation")
    print()


def optimise_prompt(agent_key: str, analysis: dict, apply: bool = False):
    """
    Use Claude to rewrite the prompt for an underperforming agent.
    """
    data = analysis.get(agent_key)
    if not data:
        print(f"No data for agent: {agent_key}")
        return

    prompt_file = AGENT_MAP.get(agent_key)
    if not prompt_file:
        print(f"No prompt file mapped for: {agent_key}")
        return

    current_prompt = (PROMPT_DIR / prompt_file).read_text(encoding="utf-8")
    notes = "\n\n---\n\n".join(data["notes"]) if data["notes"] else "No specific notes recorded."

    avg = data["avg_score"]
    print(f"\n🔧 Optimising prompt for: {agent_key} (avg score: {avg}/50)")

    optimizer_system = """You are the NeuroForge Prompt Optimizer. You improve AI agent system prompts based on real QA failure data.

Your job:
1. Read the current system prompt
2. Read the QA failure notes from real runs
3. Identify the specific weaknesses the prompt is failing to prevent
4. Rewrite the prompt to address those weaknesses — without breaking what works
5. Return the COMPLETE rewritten prompt, ready to use as a drop-in replacement

Rules:
- Keep the same overall structure (Role, Brand Context, Faculty Context, Output Format, Constraints, Quality Bar)
- Only change what the failure data indicates needs changing
- Make constraints more specific, not more generic
- Add examples where the failures suggest the agent is misunderstanding the instruction
- Do not water down the quality bar — raise it
- Return ONLY the rewritten prompt. No preamble, no explanation, no markdown wrapper."""

    optimizer_user = f"""Here is the current system prompt for the {agent_key} agent:

=== CURRENT PROMPT ===
{current_prompt}
=== END PROMPT ===

Here are the QA failure notes from {data['run_count']} runs (average score: {avg}/50):

=== QA FAILURE NOTES ===
{notes}
=== END NOTES ===

The agent's low runs scored: {data['low_runs']}

Please rewrite the prompt to address these failure patterns. Return the complete rewritten prompt."""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=optimizer_system,
        messages=[{"role": "user", "content": optimizer_user}],
    )
    new_prompt = message.content[0].text

    if apply:
        # Version the old prompt before replacing
        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version_file = VERSIONS_DIR / f"{prompt_file.replace('.md', '')}_{timestamp}.md"
        shutil.copy(PROMPT_DIR / prompt_file, version_file)
        print(f"  ✓ Old version saved to: {version_file}")

        # Write new prompt
        (PROMPT_DIR / prompt_file).write_text(new_prompt, encoding="utf-8")
        print(f"  ✓ New prompt written to: {PROMPT_DIR / prompt_file}")
    else:
        # Preview mode — save to a review file
        preview_file = PROMPT_DIR / f"PREVIEW_{prompt_file}"
        preview_file.write_text(new_prompt, encoding="utf-8")
        print(f"  ✓ Preview saved to: {preview_file}")
        print(f"  → Review the preview, then run with --apply to replace the live prompt.")

    return new_prompt


def main():
    parser = argparse.ArgumentParser(description="NeuroForge Prompt Optimizer")
    parser.add_argument("--agent", default=None,
                        choices=list(AGENT_MAP.keys()) + [None],
                        help="Agent to optimise (default: all below threshold)")
    parser.add_argument("--apply", action="store_true",
                        help="Apply rewrites to live prompts (default: preview only)")
    parser.add_argument("--threshold", type=int, default=40,
                        help="Optimise agents below this avg score (default: 40)")
    args = parser.parse_args()

    db = load_db()
    if not db:
        return

    analysis = analyse_performance(db, agent_filter=args.agent)
    print_performance_report(analysis)

    if not analysis:
        print("No performance data found. Run the pipeline on some topics first.")
        return

    # Optimise
    candidates = []
    if args.agent:
        candidates = [args.agent]
    else:
        # Auto-select agents below threshold
        candidates = [
            key for key, data in analysis.items()
            if data["avg_score"] and data["avg_score"] < args.threshold and data["run_count"] >= 2
        ]

    if not candidates:
        print(f"✅ All agents scoring above {args.threshold}/50. No optimisation needed.")
        print("   Lower --threshold to force optimisation.")
        return

    print(f"\nCandidates for optimisation: {', '.join(candidates)}")
    if not args.apply:
        print("Running in PREVIEW mode. Use --apply to replace live prompts.\n")

    for agent_key in candidates:
        optimise_prompt(agent_key, analysis, apply=args.apply)

    print("\n✅ Optimisation complete.")
    if not args.apply:
        print("Review PREVIEW_ files in the prompts directory before applying.")


if __name__ == "__main__":
    main()
