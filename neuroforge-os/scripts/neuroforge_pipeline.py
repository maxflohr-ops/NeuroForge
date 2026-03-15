#!/usr/bin/env python3
"""
NeuroForge OS — Production Pipeline Orchestrator
================================================
Chains all 6 agents in sequence for a single topic.
Saves every output to disk and logs QA scores to a JSON database.

Usage:
    python neuroforge_pipeline.py --topic "Stop Overthinking" \
                                  --faculty "Dr. Nova Vale" \
                                  --pillar "Overthinking, anxiety, emotional regulation" \
                                  --mode full

Modes:
    research   — Run Research Agent only
    blueprint  — Run Research + Book Architect
    manuscript — Run Research + Blueprint + one chapter (specify --chapter)
    scripts    — Run Shorts Script Agent on existing brief
    funnel     — Run Funnel Agent on existing brief
    full       — Run all agents in sequence (production mode)
    qa         — Run QA Agent on an existing file (specify --file)
"""

import anthropic
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8000
OUTPUT_DIR = Path("./output")
PROMPT_DIR = Path("./prompts")
DB_FILE = Path("./neuroforge_db.json")

FACULTY_PROFILES = {
    "Dr. Nova Vale": {
        "domain": "Anxiety, overthinking, intrusive thoughts, emotional regulation",
        "tone": "Calm, intelligent, reassuring, clear",
        "pillar": "Overthinking, anxiety, emotional regulation",
    },
    "Kai Ren": {
        "domain": "Focus, dopamine, habits, productivity",
        "tone": "Sharp, minimalist, tactical",
        "pillar": "Focus, dopamine, productivity",
    },
    "Marcus Voss": {
        "domain": "Discipline, stoicism, self-respect, mental toughness",
        "tone": "Direct, masculine, controlled, no fluff",
        "pillar": "Discipline, identity, life design",
    },
    "Luna Hart": {
        "domain": "Relationships, attachment, boundaries, communication",
        "tone": "Warm, emotionally intelligent, insightful",
        "pillar": "Relationships, attachment, boundaries",
    },
    "Dr. Orion Hale": {
        "domain": "Neuroscience, sleep, brain optimization, mental performance",
        "tone": "Clinical but accessible",
        "pillar": "Focus, dopamine, productivity",
    },
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    """Load a system prompt from the prompts directory."""
    path = PROMPT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def save_output(topic: str, agent_name: str, content: str) -> Path:
    """Save agent output to a structured folder."""
    safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
    topic_dir = OUTPUT_DIR / safe_topic
    topic_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{agent_name}_{timestamp}.md"
    filepath = topic_dir / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"  ✓ Saved: {filepath}")
    return filepath


def log_to_db(topic: str, agent: str, filepath: str, qa_score: int = None):
    """Append a run record to the local JSON database."""
    db = []
    if DB_FILE.exists():
        with open(DB_FILE) as f:
            db = json.load(f)

    record = {
        "timestamp": datetime.now().isoformat(),
        "topic": topic,
        "agent": agent,
        "output_file": str(filepath),
        "qa_score": qa_score,
    }
    db.append(record)

    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


def extract_qa_score(qa_output: str) -> int:
    """Parse total QA score from QA Agent output."""
    match = re.search(r"\*\*TOTAL\*\*.*?(\d+)/50", qa_output)
    if match:
        return int(match.group(1))
    # fallback: search for X/50
    match = re.search(r"(\d+)/50", qa_output)
    if match:
        return int(match.group(1))
    return None


def call_claude(system_prompt: str, user_message: str, label: str = "") -> str:
    """Single Claude API call. Returns text content."""
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

    print(f"\n{'─'*50}")
    print(f"  Calling: {label}")
    print(f"  Model:   {MODEL}")
    print(f"{'─'*50}")

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


# ─────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────

def run_research_agent(topic: str, pillar: str, faculty: str, audience_notes: str = "") -> str:
    """Agent 1: Research Brief"""
    print("\n🔬 RESEARCH AGENT — Starting")

    system_prompt = load_prompt("01_research_agent.md")
    faculty_info = FACULTY_PROFILES.get(faculty, {})

    user_message = f"""
Please produce a complete research brief for the following topic.

**Topic:** {topic}
**Pillar:** {pillar}
**Faculty:** {faculty}
**Faculty Domain:** {faculty_info.get('domain', 'N/A')}
**Faculty Tone:** {faculty_info.get('tone', 'N/A')}
**Audience Notes:** {audience_notes if audience_notes else "None provided — use standard audience for this faculty member."}

Produce the full research brief now, following the output format exactly.
""".strip()

    output = call_claude(system_prompt, user_message, label="Research Agent")
    return output


def run_book_architect_agent(research_brief: str, faculty: str, word_count: str = "25,000–30,000") -> str:
    """Agent 2: Book Blueprint"""
    print("\n📐 BOOK ARCHITECT AGENT — Starting")

    system_prompt = load_prompt("02_book_architect_agent.md")

    user_message = f"""
Please produce a complete book blueprint based on the following research brief.

**Faculty:** {faculty}
**Target Word Count:** {word_count} words

---

{research_brief}

---

Produce the full book blueprint now, following the output format exactly.
""".strip()

    output = call_claude(system_prompt, user_message, label="Book Architect Agent")
    return output


def run_manuscript_agent(blueprint: str, chapter_num: int, faculty: str, chapter_word_count: str = "2,500–3,500") -> str:
    """Agent 3: Manuscript Chapter"""
    print(f"\n✍️  MANUSCRIPT AGENT — Chapter {chapter_num}")

    system_prompt = load_prompt("03_manuscript_agent.md")

    user_message = f"""
Please write Chapter {chapter_num} of the book based on the blueprint below.

**Faculty:** {faculty}
**Chapter Number:** {chapter_num}
**Target Word Count:** {chapter_word_count} words

Write the full chapter now as flowing prose. Remember: do not start with "In this chapter..." and do not end with a bullet-point summary. Follow the output format in your instructions exactly.

---

BOOK BLUEPRINT:
{blueprint}
""".strip()

    output = call_claude(system_prompt, user_message, label=f"Manuscript Agent (Chapter {chapter_num})")
    return output


def run_shorts_agent(research_brief: str, faculty: str, num_scripts: int = 20, cta: str = "link in bio") -> str:
    """Agent 4: Short-Form Scripts"""
    print(f"\n🎬 SHORTS SCRIPT AGENT — {num_scripts} scripts")

    system_prompt = load_prompt("04_shorts_script_agent.md")

    user_message = f"""
Please produce {num_scripts} short-form video scripts based on the research brief below.

**Faculty:** {faculty}
**Number of Scripts:** {num_scripts}
**Target Platforms:** TikTok, Instagram Reels, YouTube Shorts
**CTA Destination:** {cta}

Follow the batch output structure in your instructions (hooks, mechanism, counterintuitive, tool, story, objection scripts in sequence).
Also include the 10 quote graphics and 5 carousel concepts at the end.

---

RESEARCH BRIEF:
{research_brief}
""".strip()

    output = call_claude(system_prompt, user_message, label="Shorts Script Agent")
    return output


def run_funnel_agent(research_brief: str, blueprint: str, faculty: str, price: str = "$17", cta_url: str = "[LANDING_PAGE_URL]") -> str:
    """Agent 5: Funnel Copy"""
    print("\n💰 FUNNEL AGENT — Starting")

    system_prompt = load_prompt("05_funnel_agent.md")

    user_message = f"""
Please produce the complete funnel copy package for this topic.

**Faculty:** {faculty}
**Book Price:** {price}
**CTA URL:** {cta_url}

Produce all five sections: landing page, thank you page + book offer, 5-email sequence, Google Ads copy, and the quality check.

---

RESEARCH BRIEF:
{research_brief}

---

BOOK BLUEPRINT (for chapter references and offer copy):
{blueprint}
""".strip()

    output = call_claude(system_prompt, user_message, label="Funnel Agent")
    return output


def run_qa_agent(content: str, content_type: str, faculty: str, topic: str) -> tuple[str, int]:
    """Agent 6: QA Review. Returns (qa_report, score)."""
    print(f"\n🔍 QA AGENT — Reviewing {content_type}")

    system_prompt = load_prompt("06_qa_agent.md")

    user_message = f"""
Please review the following content and produce a full QA report.

**Content Type:** {content_type}
**Faculty:** {faculty}
**Topic:** {topic}

---

CONTENT TO REVIEW:
{content}
""".strip()

    qa_output = call_claude(system_prompt, user_message, label="QA Agent")
    score = extract_qa_score(qa_output)
    return qa_output, score


# ─────────────────────────────────────────────
# PIPELINE MODES
# ─────────────────────────────────────────────

def pipeline_research_only(args):
    """Run Research Agent only."""
    brief = run_research_agent(args.topic, args.pillar, args.faculty, args.audience_notes)
    path = save_output(args.topic, "01_research_brief", brief)

    # QA the brief
    qa_report, score = run_qa_agent(brief, "Research Brief", args.faculty, args.topic)
    qa_path = save_output(args.topic, "01_research_brief_QA", qa_report)

    log_to_db(args.topic, "Research Agent", path, score)
    print(f"\n✅ Research brief complete. QA Score: {score}/50")
    return brief


def pipeline_blueprint(args):
    """Run Research + Book Architect."""
    brief = pipeline_research_only(args)

    blueprint = run_book_architect_agent(brief, args.faculty)
    path = save_output(args.topic, "02_book_blueprint", blueprint)

    qa_report, score = run_qa_agent(blueprint, "Book Blueprint", args.faculty, args.topic)
    save_output(args.topic, "02_book_blueprint_QA", qa_report)
    log_to_db(args.topic, "Book Architect Agent", path, score)

    print(f"\n✅ Blueprint complete. QA Score: {score}/50")
    return brief, blueprint


def pipeline_manuscript(args):
    """Run full pipeline up to one manuscript chapter."""
    brief, blueprint = pipeline_blueprint(args)

    chapter_num = args.chapter if args.chapter else 1
    chapter = run_manuscript_agent(blueprint, chapter_num, args.faculty)
    path = save_output(args.topic, f"03_chapter_{chapter_num:02d}", chapter)

    qa_report, score = run_qa_agent(chapter, "Manuscript Chapter", args.faculty, args.topic)
    save_output(args.topic, f"03_chapter_{chapter_num:02d}_QA", qa_report)
    log_to_db(args.topic, f"Manuscript Agent Ch{chapter_num}", path, score)

    print(f"\n✅ Chapter {chapter_num} complete. QA Score: {score}/50")
    return brief, blueprint, chapter


def pipeline_full(args):
    """Run the complete pipeline: research → blueprint → chapter 1 → scripts → funnel."""
    print(f"\n{'='*60}")
    print(f"  NEUROFORGE OS — FULL PIPELINE")
    print(f"  Topic:   {args.topic}")
    print(f"  Faculty: {args.faculty}")
    print(f"{'='*60}")

    # Step 1: Research
    brief = run_research_agent(args.topic, args.pillar, args.faculty, args.audience_notes)
    brief_path = save_output(args.topic, "01_research_brief", brief)
    brief_qa, brief_score = run_qa_agent(brief, "Research Brief", args.faculty, args.topic)
    save_output(args.topic, "01_research_brief_QA", brief_qa)
    log_to_db(args.topic, "Research Agent", brief_path, brief_score)

    if brief_score and brief_score < 35:
        print(f"\n⚠️  Research brief failed QA ({brief_score}/50). Review before continuing.")
        print("    Output saved. Stopping pipeline. Fix the brief and re-run from --mode blueprint.")
        return

    # Step 2: Blueprint
    blueprint = run_book_architect_agent(brief, args.faculty)
    bp_path = save_output(args.topic, "02_book_blueprint", blueprint)
    bp_qa, bp_score = run_qa_agent(blueprint, "Book Blueprint", args.faculty, args.topic)
    save_output(args.topic, "02_book_blueprint_QA", bp_qa)
    log_to_db(args.topic, "Book Architect Agent", bp_path, bp_score)

    if bp_score and bp_score < 35:
        print(f"\n⚠️  Blueprint failed QA ({bp_score}/50). Review before continuing.")
        return

    # Step 3: Chapter 1
    chapter = run_manuscript_agent(blueprint, 1, args.faculty)
    ch_path = save_output(args.topic, "03_chapter_01", chapter)
    ch_qa, ch_score = run_qa_agent(chapter, "Manuscript Chapter", args.faculty, args.topic)
    save_output(args.topic, "03_chapter_01_QA", ch_qa)
    log_to_db(args.topic, "Manuscript Agent Ch1", ch_path, ch_score)

    # Step 4: Scripts (20 scripts)
    scripts = run_shorts_agent(brief, args.faculty, num_scripts=20)
    sc_path = save_output(args.topic, "04_shorts_scripts", scripts)
    sc_qa, sc_score = run_qa_agent(scripts, "Short-Form Scripts", args.faculty, args.topic)
    save_output(args.topic, "04_shorts_scripts_QA", sc_qa)
    log_to_db(args.topic, "Shorts Script Agent", sc_path, sc_score)

    # Step 5: Funnel
    funnel = run_funnel_agent(brief, blueprint, args.faculty)
    fn_path = save_output(args.topic, "05_funnel_copy", funnel)
    fn_qa, fn_score = run_qa_agent(funnel, "Funnel Copy", args.faculty, args.topic)
    save_output(args.topic, "05_funnel_copy_QA", fn_qa)
    log_to_db(args.topic, "Funnel Agent", fn_path, fn_score)

    # Summary
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {args.topic}")
    print(f"{'='*60}")
    print(f"  Research Brief QA:    {brief_score}/50")
    print(f"  Book Blueprint QA:    {bp_score}/50")
    print(f"  Chapter 1 QA:         {ch_score}/50")
    print(f"  Scripts QA:           {sc_score}/50")
    print(f"  Funnel Copy QA:       {fn_score}/50")

    avg = sum(filter(None, [brief_score, bp_score, ch_score, sc_score, fn_score]))
    count = len([x for x in [brief_score, bp_score, ch_score, sc_score, fn_score] if x])
    print(f"\n  Average QA Score:     {avg // count}/50" if count else "")
    print(f"\n  All outputs saved to: ./output/{re.sub(r'[^a-zA-Z0-9_]', '_', args.topic.lower())}/")
    print(f"  Database updated:     ./neuroforge_db.json")
    print(f"{'='*60}\n")


def pipeline_qa_file(args):
    """QA an existing file."""
    if not args.file:
        print("Error: --file required for qa mode")
        sys.exit(1)
    content = Path(args.file).read_text(encoding="utf-8")
    qa_report, score = run_qa_agent(content, args.content_type or "Manuscript Chapter", args.faculty, args.topic)
    save_output(args.topic, "qa_review", qa_report)
    print(f"\n✅ QA complete. Score: {score}/50")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NeuroForge OS Pipeline Orchestrator")

    parser.add_argument("--topic", required=True, help='Topic name e.g. "Stop Overthinking"')
    parser.add_argument("--faculty", required=True, help='Faculty member e.g. "Dr. Nova Vale"')
    parser.add_argument("--pillar", default="", help="Content pillar")
    parser.add_argument("--audience_notes", default="", help="Optional audience context")
    parser.add_argument("--mode", default="full",
                        choices=["research", "blueprint", "manuscript", "scripts", "funnel", "full", "qa"],
                        help="Pipeline mode")
    parser.add_argument("--chapter", type=int, default=1, help="Chapter number for manuscript mode")
    parser.add_argument("--file", default="", help="File path for qa mode")
    parser.add_argument("--content_type", default="", help="Content type for qa mode")

    args = parser.parse_args()

    # Set default pillar from faculty if not provided
    if not args.pillar and args.faculty in FACULTY_PROFILES:
        args.pillar = FACULTY_PROFILES[args.faculty]["pillar"]

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nError: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    # Route to correct mode
    if args.mode == "research":
        pipeline_research_only(args)
    elif args.mode == "blueprint":
        pipeline_blueprint(args)
    elif args.mode == "manuscript":
        pipeline_manuscript(args)
    elif args.mode == "full":
        pipeline_full(args)
    elif args.mode == "qa":
        pipeline_qa_file(args)
    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
