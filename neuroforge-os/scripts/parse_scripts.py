#!/usr/bin/env python3
"""
NeuroForge OS — Script Parser
==============================
Parses a batch shorts script file (04_shorts_scripts_*.md) into individual
JSON files, one per script. Each JSON contains all fields needed by heygen_producer.py.

Usage:
    python parse_scripts.py \
        --file output/stop_overthinking/04_shorts_scripts_*.md \
        --topic "Stop Overthinking" \
        --faculty "Dr. Nova Vale"

Output:
    output/stop_overthinking/scripts_parsed/
        script_01.json
        script_02.json
        ...
        script_20.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"


def parse_batch_file(text: str) -> list[dict]:
    """
    Parse all numbered scripts from a batch MD file.
    Returns list of dicts with keys: number, hook, topic, duration, body, visual_direction,
    text_overlay, caption_hook.
    """
    scripts = []

    # Split on script headers: "**SCRIPT N**"
    blocks = re.split(r"\*\*SCRIPT\s+(\d+)\*\*", text)
    # blocks = [pre_text, "1", script_1_body, "2", script_2_body, ...]

    i = 1
    while i < len(blocks) - 1:
        number = int(blocks[i])
        body_raw = blocks[i + 1]
        i += 2

        # Extract metadata lines
        hook = _extract_field(body_raw, "Hook")
        topic = _extract_field(body_raw, "Topic")
        duration = _extract_field(body_raw, "Estimated Duration")
        visual_direction = _extract_field(body_raw, "VISUAL DIRECTION")
        text_overlay = _extract_field(body_raw, "TEXT OVERLAY")
        caption_hook = _extract_field(body_raw, "Caption Hook")

        # Script body = text between the first --- separator and the VISUAL DIRECTION block
        # The structure is: metadata lines, ---, [body], ---, VISUAL DIRECTION...
        # Strip metadata lines first, then extract between first and last ---
        body_clean = _extract_script_body(body_raw)

        scripts.append({
            "number": number,
            "hook": hook,
            "topic": topic,
            "duration": duration,
            "body": body_clean,
            "visual_direction": visual_direction,
            "text_overlay": text_overlay,
            "caption_hook": caption_hook,
        })

    return scripts


def _extract_field(text: str, field: str) -> str:
    """Extract value of **Field:** or **FIELD:** line."""
    pattern = rf"\*\*{re.escape(field)}:\*\*\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_script_body(text: str) -> str:
    """
    Extract the spoken script body — everything between the first --- separator
    (after the metadata block) and the VISUAL DIRECTION line.
    """
    # Remove metadata lines (lines starting with **)
    lines = text.splitlines()
    past_metadata = False
    in_body = False
    body_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip metadata header lines
        if not past_metadata:
            if stripped == "---":
                past_metadata = True
                in_body = True
            continue

        # We're past the first ---
        if in_body:
            # Stop when we hit VISUAL DIRECTION
            if stripped.startswith("**VISUAL DIRECTION"):
                break
            # Stop at the second --- block (separator between body and visual notes)
            if stripped == "---":
                # Could be end-of-body separator — check if visual direction follows soon
                # Just stop here and clean up trailing dashes
                break
            body_lines.append(line)

    return "\n".join(body_lines).strip()


def save_parsed_scripts(scripts: list[dict], topic: str) -> Path:
    """Save each script as a numbered JSON file."""
    safe_topic = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
    out_dir = OUTPUT_DIR / safe_topic / "scripts_parsed"
    out_dir.mkdir(parents=True, exist_ok=True)

    for script in scripts:
        filepath = out_dir / f"script_{script['number']:02d}.json"
        filepath.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ {filepath.name}")

    print(f"\n  {len(scripts)} scripts saved to: {out_dir}")
    return out_dir


def main():
    parser = argparse.ArgumentParser(description="Parse batch scripts MD into individual JSONs")
    parser.add_argument("--file", required=True, help="Path to 04_shorts_scripts_*.md batch file")
    parser.add_argument("--topic", required=True, help='Topic name e.g. "Stop Overthinking"')
    parser.add_argument("--faculty", default="", help="Faculty name (for reference only)")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    scripts = parse_batch_file(text)

    if not scripts:
        print("Error: No scripts found in file. Check the format.")
        sys.exit(1)

    print(f"\nParsed {len(scripts)} scripts from {Path(args.file).name}")
    out_dir = save_parsed_scripts(scripts, args.topic)

    # Print preview of first script
    first = scripts[0]
    print(f"\nScript 1 preview:")
    print(f"  Hook:     {first['hook'][:80]}...")
    print(f"  Overlay:  {first['text_overlay']}")
    print(f"  Duration: {first['duration']}")


if __name__ == "__main__":
    main()
