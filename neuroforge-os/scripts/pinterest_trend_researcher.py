#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Trend Researcher
============================================
Researches trending Pinterest keywords, rising sounds, and content themes
in Ebril's target niches to generate actionable content briefs.

This agent does NOT download or repost anyone's content. It produces a
research brief that informs what ORIGINAL content Ebril should create.

Prerequisites:
    ANTHROPIC_API_KEY   — for Claude-powered trend analysis

Usage:
    python pinterest_trend_researcher.py --output-dir output/pinterest
    python pinterest_trend_researcher.py --niches aesthetic,music,lifestyle
    python pinterest_trend_researcher.py --dry-run

Output:
    A markdown trend brief (trend-brief-YYYY-MM-DD.md) containing:
      - Top trending keywords per niche
      - Rising content themes
      - 10-15 content ideas with mood, board, and track pairings
      - Hashtag recommendations
      - Weekly content calendar suggestion
"""

import anthropic
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pinterest_config import (
    BASE_HASHTAGS,
    EBRIL_TRACKS,
    NICHE_HASHTAGS,
    NICHE_TO_BOARD,
    PINTEREST_BOARDS,
    TREND_RESEARCH_QUERIES,
    VALID_MOODS,
    VALID_NICHES,
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "output" / "pinterest"
SESSION_TOKEN_FILE = Path("/home/claude/.claude/remote/.session_ingress_token")


# ─────────────────────────────────────────────
# ANTHROPIC CLIENT
# ─────────────────────────────────────────────

def _init_anthropic_client() -> anthropic.Anthropic:
    """Create Anthropic client with best available auth."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    if SESSION_TOKEN_FILE.exists():
        token = SESSION_TOKEN_FILE.read_text().strip()
        return anthropic.Anthropic(auth_token=token)
    return anthropic.Anthropic()


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

TREND_ANALYST_SYSTEM_PROMPT = """\
You are a Pinterest marketing strategist specializing in indie music discovery \
and female aesthetic content. You work for Florra, a lifestyle brand that \
promotes the indie artist Ebril. Your audience is women aged 18-35 who engage \
with aesthetic mood boards, slow living, indie folk playlists, golden hour \
photography, and soft lifestyle content.

You have deep expertise in:
- Pinterest algorithm behavior, keyword search trends, and pin ranking factors
- The aesthetic, cottagecore, indie music, lifestyle, fashion, and wellness niches
- Content formats that drive saves and outbound clicks on Pinterest
- Seasonal and cultural trend cycles relevant to the female 18-35 demographic
- Music discovery behavior on visual platforms

When analyzing trends, you focus on actionable insights that help Ebril's team \
create ORIGINAL content — never copied, scraped, or repurposed from other \
creators. Every recommendation should include specific enough detail that a \
content creator could act on it immediately.

Always return structured, parseable JSON when asked for trend data.\
"""

CONTENT_BRIEF_SYSTEM_PROMPT = """\
You are a senior content strategist at Florra, a lifestyle brand built around \
the indie artist Ebril. You create detailed content briefs that translate \
trend research into an actionable weekly plan.

Your briefs are clean, scannable, and written for a small creative team. Each \
content idea must include:
- A working title
- The target niche and Pinterest board
- A mood tag that maps to one of Ebril's tracks
- Suggested hashtags
- A one-sentence creative direction

You write in markdown and organize by niche. Your tone is professional but \
warm — like a creative director briefing a shoot.\
"""


# ─────────────────────────────────────────────
# TREND RESEARCHER
# ─────────────────────────────────────────────

class TrendResearcher:
    """Researches Pinterest trends and generates content briefs for Ebril."""

    def __init__(self, output_dir: Path, anthropic_client: anthropic.Anthropic):
        self.output_dir = output_dir
        self.client = anthropic_client

    def log(self, message: str, prefix: str = "info"):
        """Print a timestamped log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"  [{timestamp}] {prefix.upper():>5}  {message}")

    def research_pinterest_trends(self, niches: list[str]) -> dict:
        """Use Claude to analyze current Pinterest trends for the given niches.

        Args:
            niches: List of niche tags to research (e.g. ["aesthetic", "music"]).

        Returns:
            Dictionary with trending keywords, rising themes, content ideas,
            and optimal posting times per niche.
        """
        self.log(f"Researching trends for niches: {', '.join(niches)}")

        # Build context about boards, hashtags, and existing queries
        boards_context = "\n".join(
            f"  - {key}: {board['name']} ({', '.join(board['content_types'])})"
            for key, board in PINTEREST_BOARDS.items()
        )
        tracks_context = "\n".join(
            f"  - {mood}: \"{track['title']}\" — {track['use_for']}"
            for mood, track in EBRIL_TRACKS.items()
        )
        queries_context = "\n".join(f"  - {q}" for q in TREND_RESEARCH_QUERIES)
        niche_hashtags_context = "\n".join(
            f"  - {niche}: {', '.join(tags)}"
            for niche, tags in NICHE_HASHTAGS.items()
            if niche in niches
        )

        user_message = f"""\
Analyze current Pinterest trends for the following niches and return structured JSON.

**Niches to research:** {', '.join(niches)}

**Context — Ebril's Pinterest boards:**
{boards_context}

**Context — Ebril's track catalog (mood -> track):**
{tracks_context}

**Context — Existing research queries we monitor:**
{queries_context}

**Context — Our current hashtag sets per niche:**
{niche_hashtags_context}

**Instructions:**
For each niche, identify:
1. **trending_keywords** — 8-12 keywords/phrases currently rising on Pinterest search
2. **rising_themes** — 3-5 broader content themes gaining momentum
3. **content_format_trends** — what pin formats are performing (idea pins, static, video, carousel)
4. **audience_signals** — what the 18-35 female demographic is engaging with right now
5. **seasonal_hooks** — any upcoming seasonal or cultural moments to leverage
6. **suggested_content_ideas** — 3-4 specific content ideas per niche, each with:
   - title (working title for the pin/idea pin)
   - mood_tag (one of: {', '.join(VALID_MOODS)})
   - description (one sentence creative direction)
   - suggested_track (from Ebril's catalog)
7. **optimal_posting** — best days/times based on current engagement patterns

Return ONLY valid JSON with this structure:
{{
  "research_date": "YYYY-MM-DD",
  "niches": {{
    "<niche_name>": {{
      "trending_keywords": ["..."],
      "rising_themes": ["..."],
      "content_format_trends": ["..."],
      "audience_signals": ["..."],
      "seasonal_hooks": ["..."],
      "suggested_content_ideas": [
        {{
          "title": "...",
          "mood_tag": "...",
          "description": "...",
          "suggested_track": "..."
        }}
      ],
      "optimal_posting": {{
        "best_days": ["..."],
        "best_times_est": ["..."]
      }}
    }}
  }}
}}"""

        print(f"\n{'='*60}")
        print(f"  PINTEREST TREND RESEARCHER")
        print(f"  Niches: {', '.join(niches)}")
        print(f"  Model:  {MODEL}")
        print(f"{'='*60}")

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=TREND_ANALYST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_response = message.content[0].text
            self.log("Received trend analysis from Claude")

            # Parse JSON from response — handle markdown code fences
            json_text = raw_response.strip()
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                # Remove first line (```json) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                json_text = "\n".join(lines)

            trends = json.loads(json_text)
            self.log(f"Parsed trends for {len(trends.get('niches', {}))} niches")
            return trends

        except json.JSONDecodeError as e:
            self.log(f"Failed to parse Claude response as JSON: {e}", "error")
            self.log("Raw response saved for debugging", "error")
            # Return a minimal structure so the pipeline can continue
            return {
                "research_date": datetime.now().strftime("%Y-%m-%d"),
                "niches": {},
                "_raw_response": raw_response,
                "_parse_error": str(e),
            }
        except Exception as e:
            self.log(f"Trend research failed: {e}", "error")
            raise

    def generate_content_brief(self, trends: dict, niches: list[str]) -> str:
        """Generate a markdown content brief from trend research data.

        Args:
            trends: Trend data dictionary from research_pinterest_trends().
            niches: List of niches that were researched.

        Returns:
            Formatted markdown string ready to save as a brief.
        """
        self.log("Generating content brief from trend data")

        # Build board mapping context for the prompt
        board_mapping = "\n".join(
            f"  - {niche} -> {PINTEREST_BOARDS[NICHE_TO_BOARD[niche]]['name']}"
            for niche in niches
            if niche in NICHE_TO_BOARD
        )
        tracks_list = "\n".join(
            f"  - {mood}: \"{track['title']}\" ({track['use_for']})"
            for mood, track in EBRIL_TRACKS.items()
        )
        base_tags = ", ".join(BASE_HASHTAGS)
        niche_tags = "\n".join(
            f"  - {niche}: {', '.join(tags)}"
            for niche, tags in NICHE_HASHTAGS.items()
            if niche in niches
        )

        user_message = f"""\
Using the trend research data below, generate a complete weekly content brief \
for Ebril's Pinterest strategy.

**Trend Research Data:**
```json
{json.dumps(trends, indent=2)}
```

**Niche-to-Board Mapping:**
{board_mapping}

**Ebril's Track Catalog:**
{tracks_list}

**Base Hashtags (always include):** {base_tags}

**Niche-specific Hashtags:**
{niche_tags}

**Brief Requirements:**
Write the brief in clean markdown with these sections:

1. **Executive Summary** — 2-3 sentence overview of this week's trend landscape

2. **Trending Keywords** — table with columns: Keyword | Niche | Trend Direction | Priority
   Include 15-20 keywords across all niches, sorted by priority.

3. **Rising Content Themes** — for each theme, explain why it matters and how Ebril can \
leverage it authentically.

4. **Content Ideas** (10-15 ideas) — each idea must include:
   - **Title**: working title for the pin
   - **Niche**: which niche it targets
   - **Board**: which Pinterest board to pin to
   - **Mood Tag**: one of ({', '.join(VALID_MOODS)})
   - **Track Pairing**: which Ebril track to pair with it
   - **Format**: idea pin, static pin, video pin, or carousel
   - **Hashtags**: 5-8 relevant hashtags (mix of base + niche)
   - **Creative Direction**: 1-2 sentences describing the visual/content approach

5. **Hashtag Recommendations** — any NEW hashtags to test beyond our existing sets, \
with estimated reach.

6. **Competitive Landscape** — what similar creators/brands are doing well on Pinterest \
right now and what Ebril can learn from it (without copying).

7. **Weekly Content Calendar** — a simple Mon-Sun grid suggesting which content ideas \
to post on which days, considering optimal posting times.

Start the document with:
# Pinterest Trend Brief — {datetime.now().strftime("%B %d, %Y")}
**Prepared for:** Ebril / Florra
**Niches:** {', '.join(niches)}

Make every recommendation specific and actionable. No generic advice.\
"""

        print(f"\n{'─'*50}")
        print(f"  Generating content brief")
        print(f"  Model:  {MODEL}")
        print(f"{'─'*50}")

        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=CONTENT_BRIEF_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            brief = message.content[0].text
            self.log(f"Content brief generated ({len(brief)} chars)")
            return brief

        except Exception as e:
            self.log(f"Brief generation failed: {e}", "error")
            raise

    def save_brief(self, brief: str, output_dir: Path) -> Path:
        """Save the content brief as a dated markdown file.

        Args:
            brief: Markdown content brief string.
            output_dir: Directory to save the brief in.

        Returns:
            Path to the saved file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        date_stamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"trend-brief-{date_stamp}.md"
        filepath = output_dir / filename

        filepath.write_text(brief, encoding="utf-8")
        self.log(f"Brief saved to {filepath}")
        return filepath


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NeuroForge OS — Pinterest Trend Researcher"
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help='Output directory for briefs (default: "output/pinterest")',
    )
    parser.add_argument(
        "--niches",
        default=",".join(VALID_NICHES),
        help=(
            "Comma-separated niches to research "
            f'(default: all — {",".join(VALID_NICHES)})'
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print brief to stdout instead of saving to file",
    )

    args = parser.parse_args()

    # Validate niches
    niches = [n.strip() for n in args.niches.split(",") if n.strip()]
    invalid = [n for n in niches if n not in VALID_NICHES]
    if invalid:
        print(f"\nError: Invalid niches: {', '.join(invalid)}")
        print(f"Valid niches: {', '.join(VALID_NICHES)}")
        sys.exit(1)

    # Check authentication
    if not os.environ.get("ANTHROPIC_API_KEY") and not SESSION_TOKEN_FILE.exists():
        print("\nError: No authentication found.")
        print("Set ANTHROPIC_API_KEY or ensure session token is available.")
        sys.exit(1)

    output_dir = Path(args.output_dir)

    print(f"\n{'='*60}")
    print(f"  NEUROFORGE OS — PINTEREST TREND RESEARCHER")
    print(f"  Date:    {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Niches:  {', '.join(niches)}")
    print(f"  Output:  {output_dir}")
    print(f"  Dry run: {args.dry_run}")
    print(f"{'='*60}")

    # Initialize
    client = _init_anthropic_client()
    researcher = TrendResearcher(output_dir=output_dir, anthropic_client=client)

    # Step 1: Research trends
    researcher.log("Starting trend research")
    trends = researcher.research_pinterest_trends(niches)

    if not trends.get("niches"):
        print("\nError: Trend research returned no usable data.")
        if trends.get("_raw_response"):
            print("Raw response from Claude (for debugging):")
            print(trends["_raw_response"][:500])
        sys.exit(1)

    # Step 2: Generate content brief
    brief = researcher.generate_content_brief(trends, niches)

    # Step 3: Output
    if args.dry_run:
        print(f"\n{'='*60}")
        print("  DRY RUN — Brief printed to stdout")
        print(f"{'='*60}\n")
        print(brief)
    else:
        filepath = researcher.save_brief(brief, output_dir)
        print(f"\n{'='*60}")
        print(f"  Brief saved: {filepath}")
        print(f"{'='*60}")

    researcher.log("Done")


if __name__ == "__main__":
    main()
