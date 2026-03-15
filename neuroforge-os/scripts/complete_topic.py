#!/usr/bin/env python3
"""
NeuroForge OS — Topic Completion Script
========================================
Resume a partially-completed topic from an existing research brief + blueprint.
Runs only the remaining steps: chapter 1, shorts scripts, funnel copy.

Usage:
    python complete_topic.py \
        --topic "Beat Phone Addiction" \
        --faculty "Kai Ren" \
        --brief  output/beat_phone_addiction/01_research_brief_*.md \
        --blueprint output/beat_phone_addiction/02_book_blueprint_*.md \
        [--no-qa]
"""

import argparse
import sys
from pathlib import Path

# Reuse all agents/helpers from the main pipeline
sys.path.insert(0, str(Path(__file__).resolve().parent))
from neuroforge_pipeline import (
    run_manuscript_agent,
    run_shorts_agent,
    run_funnel_agent,
    run_qa_agent,
    save_output,
    log_to_db,
    FACULTY_PROFILES,
)


def main():
    parser = argparse.ArgumentParser(description="Resume a topic from existing brief + blueprint")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--faculty", required=True)
    parser.add_argument("--brief", required=True, help="Path to existing research brief .md")
    parser.add_argument("--blueprint", required=True, help="Path to existing book blueprint .md")
    parser.add_argument("--no-qa", action="store_true", dest="no_qa",
                        help="Skip QA agent (saves ~50%% of tokens)")
    args = parser.parse_args()

    brief = Path(args.brief).read_text(encoding="utf-8")
    blueprint = Path(args.blueprint).read_text(encoding="utf-8")

    def maybe_qa(content, content_type, save_prefix):
        if args.no_qa:
            return None
        qa_report, score = run_qa_agent(content, content_type, args.faculty, args.topic)
        save_output(args.topic, save_prefix, qa_report)
        return score

    print(f"\n{'='*60}")
    print(f"  NEUROFORGE — COMPLETING TOPIC")
    print(f"  Topic:   {args.topic}")
    print(f"  Faculty: {args.faculty}")
    print(f"  Steps:   Chapter 1 → Scripts → Funnel")
    print(f"  QA:      {'disabled' if args.no_qa else 'enabled'}")
    print(f"{'='*60}")

    # Step 3: Chapter 1
    chapter = run_manuscript_agent(blueprint, 1, args.faculty)
    ch_path = save_output(args.topic, "03_chapter_01", chapter)
    ch_score = maybe_qa(chapter, "Manuscript Chapter", "03_chapter_01_QA")
    log_to_db(args.topic, "Manuscript Agent Ch1", ch_path, ch_score)

    # Step 4: Scripts
    scripts = run_shorts_agent(brief, args.faculty, num_scripts=20)
    sc_path = save_output(args.topic, "04_shorts_scripts", scripts)
    sc_score = maybe_qa(scripts, "Short-Form Scripts", "04_shorts_scripts_QA")
    log_to_db(args.topic, "Shorts Script Agent", sc_path, sc_score)

    # Step 5: Funnel
    funnel = run_funnel_agent(brief, blueprint, args.faculty)
    fn_path = save_output(args.topic, "05_funnel_copy", funnel)
    fn_score = maybe_qa(funnel, "Funnel Copy", "05_funnel_copy_QA")
    log_to_db(args.topic, "Funnel Agent", fn_path, fn_score)

    print(f"\n{'='*60}")
    print(f"  COMPLETE — {args.topic}")
    print(f"{'='*60}")
    if not args.no_qa:
        print(f"  Chapter 1 QA:    {ch_score}/50" if ch_score else "  Chapter 1 QA:    N/A")
        print(f"  Scripts QA:      {sc_score}/50" if sc_score else "  Scripts QA:      N/A")
        print(f"  Funnel Copy QA:  {fn_score}/50" if fn_score else "  Funnel Copy QA:  N/A")
    else:
        print("  QA skipped.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
