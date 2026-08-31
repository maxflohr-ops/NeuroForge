#!/usr/bin/env python3
"""
NeuroForge - AI Educational Content Pipeline
Generates structured educational content using the Anthropic Claude API.
"""

import anthropic
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
OUTPUT_BASE_DIR = "output"

MAX_TOKENS = {
    "outline": 4096,
    "script":  8192,
    "notes":   4096,
    "quiz":    4096,
    "bio":     1024,
}

VALID_MODES = ["full", "outline", "script", "notes", "quiz", "bio"]

# ── UI Helpers ────────────────────────────────────────────────────────────────

def print_banner(ctx: dict) -> None:
    line = "=" * 60
    print(line)
    print("  NeuroForge - AI Educational Content Pipeline")
    print(line)
    print(f"  Topic  : {ctx['topic']}")
    print(f"  Faculty: {ctx['faculty']}")
    print(f"  Mode   : {ctx['mode']}")
    print(f"  Output : {ctx['output_dir']}/")
    print(line)
    print()


def print_progress(step: int, total: int, label: str) -> None:
    bar_width = 40
    filled = int(bar_width * step / total)
    bar = "#" * filled + "-" * (bar_width - filled)
    print(f"\r[{bar}] {step}/{total} - {label}", end="", flush=True)
    if step == total:
        print()


# ── Client ────────────────────────────────────────────────────────────────────

_SESSION_TOKEN_FILE = "/home/claude/.claude/remote/.session_ingress_token"


class NeuroForgeClient:
    def __init__(self) -> None:
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
            elif os.path.exists(_SESSION_TOKEN_FILE):
                token = Path(_SESSION_TOKEN_FILE).read_text().strip()
                self.client = anthropic.Anthropic(auth_token=token)
            else:
                self.client = anthropic.Anthropic()
        except Exception as e:
            print(f"\nError initializing Anthropic client: {e}", file=sys.stderr)
            print("Ensure ANTHROPIC_API_KEY is set in your environment.", file=sys.stderr)
            sys.exit(1)

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text
        except anthropic.AuthenticationError as e:
            print(f"\nAuthentication error: {e}", file=sys.stderr)
            print("Check that ANTHROPIC_API_KEY is valid.", file=sys.stderr)
            sys.exit(1)
        except anthropic.APIError as e:
            print(f"\nAPI error: {e}", file=sys.stderr)
            sys.exit(1)


# ── Generators ────────────────────────────────────────────────────────────────

def generate_outline(client: NeuroForgeClient, ctx: dict) -> dict:
    system = (
        "You are an expert curriculum designer specializing in professional "
        "development and cognitive psychology courses."
    )
    user = f"""Create a comprehensive course outline for the topic: "{ctx['topic']}"
This course will be taught by {ctx['faculty']}.

Requirements:
- 3 to 5 modules
- Each module must have 2 to 4 lessons
- Each lesson must have 3 to 5 learning objectives
- Each lesson should have an estimated duration in minutes

Return a JSON object with this exact schema:
{{
  "topic": "<string>",
  "modules": [
    {{
      "module_number": <int>,
      "title": "<string>",
      "description": "<string>",
      "lessons": [
        {{
          "lesson_number": <int>,
          "title": "<string>",
          "learning_objectives": ["<string>", ...],
          "duration_minutes": <int>
        }}
      ]
    }}
  ],
  "total_modules": <int>,
  "total_lessons": <int>
}}

Respond ONLY with valid JSON. Do not include markdown code fences, explanations, or any text outside the JSON object."""

    raw = client.generate(system, user, MAX_TOKENS["outline"])
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse outline JSON. Raw output:\n{raw}")


def generate_lecture_script(client: NeuroForgeClient, ctx: dict, outline: dict) -> str:
    system = (
        f"You are {ctx['faculty']}, a leading expert and educator on the topic of "
        f"{ctx['topic']}. You communicate with clarity, warmth, and deep expertise."
    )
    outline_summary = json.dumps(outline, indent=2)
    user = f"""Write a comprehensive lecture script for your course on "{ctx['topic']}".

Here is the course outline you will follow:
{outline_summary}

Your script should include:
- A warm, engaging introduction and greeting from you as the faculty
- Section headers corresponding to each module (use ## for module headers)
- Key concepts explained in accessible, engaging prose with examples
- Smooth transitions between sections
- Practical insights and real-world applications throughout
- A closing summary that reinforces the core takeaways

Format your response as clean Markdown. Do not include any preamble or commentary outside the document content."""

    return client.generate(system, user, MAX_TOKENS["script"])


def generate_study_notes(client: NeuroForgeClient, ctx: dict, outline: dict) -> str:
    system = (
        "You are an expert educational content writer specializing in creating "
        "concise, high-retention study materials."
    )
    outline_summary = json.dumps(outline, indent=2)
    user = f"""Create comprehensive study notes for the course: "{ctx['topic']}"

Based on this course outline:
{outline_summary}

Requirements:
- Use bullet points for key concepts
- Bold important terms using **term** syntax
- Organize notes by module structure from the outline
- Include a "Key Takeaways" section at the end
- Keep language concise and memorable

Format your response as clean Markdown. Do not include any preamble or commentary outside the document content."""

    return client.generate(system, user, MAX_TOKENS["notes"])


def generate_quiz(client: NeuroForgeClient, ctx: dict) -> dict:
    system = (
        "You are an expert assessment designer specializing in cognitive science "
        "and professional development education."
    )
    user = f"""Create a quiz for the course: "{ctx['topic']}"

Requirements:
- Exactly 10 multiple-choice questions
- Questions progress from recall/knowledge (questions 1-4) to comprehension (5-7) to application (8-10)
- Each question has exactly 4 options labeled A, B, C, D
- Include the correct answer letter and a brief explanation for each question

Return a JSON object with this exact schema:
{{
  "topic": "<string>",
  "questions": [
    {{
      "question_number": <int>,
      "question": "<string>",
      "options": {{
        "A": "<string>",
        "B": "<string>",
        "C": "<string>",
        "D": "<string>"
      }},
      "correct_answer": "<A|B|C|D>",
      "explanation": "<string>"
    }}
  ],
  "total_questions": 10
}}

Respond ONLY with valid JSON. Do not include markdown code fences, explanations, or any text outside the JSON object."""

    raw = client.generate(system, user, MAX_TOKENS["quiz"])
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse quiz JSON. Raw output:\n{raw}")


def generate_faculty_bio(client: NeuroForgeClient, ctx: dict) -> str:
    system = (
        "You are a professional biographical writer for academic and corporate educators."
    )
    user = f"""Write a professional biography for {ctx['faculty']}, an expert educator and researcher specializing in "{ctx['topic']}".

Requirements:
- 2 to 3 paragraphs
- Professional, authoritative tone
- Include academic background, research focus, and teaching philosophy
- Highlight their passion for the topic and impact on students/practitioners
- Write in third person

Format your response as clean Markdown. Do not include any preamble or commentary outside the document content."""

    return client.generate(system, user, MAX_TOKENS["bio"])


# ── Output Writers ────────────────────────────────────────────────────────────

def _file_header(ctx: dict) -> str:
    return (
        f"<!-- Generated by NeuroForge | Topic: {ctx['topic']} | "
        f"Faculty: {ctx['faculty']} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -->\n\n"
    )


def save_json(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_markdown(content: str, path: Path, ctx: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(_file_header(ctx))
        f.write(content)


def save_outline(outline: dict, output_dir: Path, ctx: dict) -> None:
    save_json(outline, output_dir / "outline.json")

    lines = [f"# Course Outline: {outline.get('topic', ctx['topic'])}\n\n"]
    for module in outline.get("modules", []):
        lines.append(f"## Module {module['module_number']}: {module['title']}\n\n")
        lines.append(f"{module.get('description', '')}\n\n")
        for lesson in module.get("lessons", []):
            lines.append(
                f"### Lesson {lesson['lesson_number']}: {lesson['title']} "
                f"({lesson.get('duration_minutes', '?')} min)\n\n"
            )
            for obj in lesson.get("learning_objectives", []):
                lines.append(f"- {obj}\n")
            lines.append("\n")

    with open(output_dir / "outline.md", "w", encoding="utf-8") as f:
        f.write(_file_header(ctx))
        f.writelines(lines)


def save_quiz(quiz: dict, output_dir: Path, ctx: dict) -> None:
    save_json(quiz, output_dir / "quiz.json")

    lines = [f"# Quiz: {quiz.get('topic', ctx['topic'])}\n\n"]
    answer_key = ["## Answer Key\n\n"]

    for q in quiz.get("questions", []):
        n = q["question_number"]
        lines.append(f"**{n}. {q['question']}**\n\n")
        for letter, text in q.get("options", {}).items():
            lines.append(f"   {letter}. {text}\n")
        lines.append("\n")
        answer_key.append(
            f"{n}. **{q['correct_answer']}** — {q.get('explanation', '')}\n\n"
        )

    lines.append("---\n\n")
    lines.extend(answer_key)

    with open(output_dir / "quiz.md", "w", encoding="utf-8") as f:
        f.write(_file_header(ctx))
        f.writelines(lines)


# ── Pipeline Orchestration ────────────────────────────────────────────────────

def build_context(args: argparse.Namespace) -> dict:
    slug = args.topic.lower().replace(" ", "_")
    slug = "".join(c for c in slug if c.isalnum() or c == "_")
    output_dir = Path(OUTPUT_BASE_DIR) / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "topic": args.topic,
        "faculty": args.faculty,
        "mode": args.mode,
        "output_dir": output_dir,
        "slug": slug,
    }


def run_mode(client: NeuroForgeClient, ctx: dict) -> None:
    mode = ctx["mode"]
    output_dir = ctx["output_dir"]

    if mode == "full":
        total = 5
        print_progress(0, total, "Starting...")

        print_progress(0, total, "Generating course outline...")
        outline = generate_outline(client, ctx)
        save_outline(outline, output_dir, ctx)
        print_progress(1, total, "Outline complete")

        print_progress(1, total, "Generating lecture script...")
        script = generate_lecture_script(client, ctx, outline)
        save_markdown(script, output_dir / "lecture_script.md", ctx)
        print_progress(2, total, "Lecture script complete")

        print_progress(2, total, "Generating study notes...")
        notes = generate_study_notes(client, ctx, outline)
        save_markdown(notes, output_dir / "study_notes.md", ctx)
        print_progress(3, total, "Study notes complete")

        print_progress(3, total, "Generating quiz...")
        quiz = generate_quiz(client, ctx)
        save_quiz(quiz, output_dir, ctx)
        print_progress(4, total, "Quiz complete")

        print_progress(4, total, "Generating faculty bio...")
        bio = generate_faculty_bio(client, ctx)
        save_markdown(bio, output_dir / "faculty_bio.md", ctx)
        print_progress(5, total, "All content generated")

    elif mode == "outline":
        print("Generating course outline...")
        outline = generate_outline(client, ctx)
        save_outline(outline, output_dir, ctx)
        print("Done.")

    elif mode == "script":
        print("Generating outline (required for script)...")
        outline = generate_outline(client, ctx)
        print("Generating lecture script...")
        script = generate_lecture_script(client, ctx, outline)
        save_markdown(script, output_dir / "lecture_script.md", ctx)
        print("Done.")

    elif mode == "notes":
        print("Generating outline (required for notes)...")
        outline = generate_outline(client, ctx)
        print("Generating study notes...")
        notes = generate_study_notes(client, ctx, outline)
        save_markdown(notes, output_dir / "study_notes.md", ctx)
        print("Done.")

    elif mode == "quiz":
        print("Generating quiz...")
        quiz = generate_quiz(client, ctx)
        save_quiz(quiz, output_dir, ctx)
        print("Done.")

    elif mode == "bio":
        print("Generating faculty bio...")
        bio = generate_faculty_bio(client, ctx)
        save_markdown(bio, output_dir / "faculty_bio.md", ctx)
        print("Done.")


def print_summary(ctx: dict) -> None:
    output_dir = ctx["output_dir"]
    files = sorted(output_dir.iterdir())
    print(f"\nOutput files in {output_dir}/:")
    print("-" * 50)
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<30} {size_kb:6.1f} KB")
    print("-" * 50)
    print(f"  {'Total files:':<30} {len(files)}")
    print()


# ── Entry Point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NeuroForge - AI Educational Content Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python neuroforge_pipeline.py --topic \"Stop Overthinking\" "
               "--faculty \"Dr. Nova Vale\" --mode full",
    )
    parser.add_argument(
        "--topic", required=True, help="The educational topic to generate content for"
    )
    parser.add_argument(
        "--faculty", required=True, help="The name of the virtual faculty/instructor"
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default="full",
        help=f"Pipeline mode: {', '.join(VALID_MODES)} (default: full)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ctx = build_context(args)
    print_banner(ctx)

    client = NeuroForgeClient()
    run_mode(client, ctx)
    print_summary(ctx)
    print("NeuroForge pipeline complete.")


if __name__ == "__main__":
    main()
