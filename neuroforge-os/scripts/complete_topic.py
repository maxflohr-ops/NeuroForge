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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from neuroforge_pipeline import (
    CT_CHAPTER, CT_FUNNEL, CT_SCRIPTS,
    log_to_db, maybe_qa, run_funnel_agent,
    run_manuscript_agent, run_shorts_agent, save_output,
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

    def qa(content, content_type, save_prefix):
        return maybe_qa(content, content_type, save_prefix, args.topic, args.faculty, args.no_qa)

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
    ch_score = qa(chapter, CT_CHAPTER, "03_chapter_01_QA")
    log_to_db(args.topic, "Manuscript Agent Ch1", ch_path, ch_score)

    # Step 4: Scripts
    scripts = run_shorts_agent(brief, args.faculty, num_scripts=20)
    sc_path = save_output(args.topic, "04_shorts_scripts", scripts)
    sc_score = qa(scripts, CT_SCRIPTS, "04_shorts_scripts_QA")
    log_to_db(args.topic, "Shorts Script Agent", sc_path, sc_score)

    # Step 5: Funnel
    funnel = run_funnel_agent(brief, blueprint, args.faculty)
    fn_path = save_output(args.topic, "05_funnel_copy", funnel)
    fn_score = qa(funnel, CT_FUNNEL, "05_funnel_copy_QA")
    log_to_db(args.topic, "Funnel Agent", fn_path, fn_score)

    print(f"\n{'='*60}")
    print(f"  COMPLETE — {args.topic}")
    print(f"{'='*60}")
    if not args.no_qa:
        scores = {CT_CHAPTER: ch_score, CT_SCRIPTS: sc_score, CT_FUNNEL: fn_score}
        for label, score in scores.items():
            print(f"  {label:<20} {score}/50" if score else f"  {label:<20} N/A")
    else:
        print("  QA skipped.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
