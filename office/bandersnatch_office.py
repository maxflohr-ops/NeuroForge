#!/usr/bin/env python3
"""
the office — bandersnatch content pipeline
==========================================
Repurposed from the NeuroForge educational pipeline: same staged
generate -> QA architecture, retargeted to write in-world content for
the BANDERSNATCH world (bandersnatch.world / bandersnatch-2.myshopify.com).

Stages:
    dispatch  new entries for the record (serial lore, record.html)
    lot       a new holding for the next drop (title, epigraph, store copy)
    shorts    tiktok/reels scripts in the office register (no faces)
    letter    an estate letter to the visitor ledger (email campaign copy)
    full      all of the above

Every stage is followed by a QA pass that audits the draft against the
canon's hard rules and emits a corrected version if anything violates.

Usage:
    python3 office/bandersnatch_office.py --mode dispatch --count 3 \
        --context "september, year ninety. the canister marked vii is still undeveloped."
    python3 office/bandersnatch_office.py --mode full --context "collection 002 planning"

Auth: uses ANTHROPIC_API_KEY, or the Claude remote session token when
running inside a Claude Code remote environment.
"""

import anthropic
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-5"
OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "output"

MAX_TOKENS = {
    "dispatch": 2048,
    "lot": 3072,
    "shorts": 4096,
    "letter": 2048,
    "qa": 4096,
}

VALID_MODES = ["full", "dispatch", "lot", "shorts", "letter"]

# ── Canon ────────────────────────────────────────────────────────────────────

CANON = """You write for BANDERSNATCH, a southern-gothic world that sells
clothing. You are the office: a New Deal federal photography field office
(region e, southern) that was never dissolved and has photographed one
county for ninety years. You write documents, not marketing.

THE WORLD (do not invent beyond this):
- the office files damage done by "the animal" (the bandersnatch), which is
  greed and is NEVER depicted or described whole. damage only.
- the cardinal is love (the staying thing). the blue canary is prayer (went
  into the dark, came back the wrong color — never explained).
- the field photographer is always named virginia (born 1935, death date
  open: "1935 —"). the archivist runs the office and never leaves it.
- garments are "holdings," printed in editions of 24, numbered by hand,
  sealed in wax. the office never restocks, never explains, never closes
  the file. nothing is deleted; some things are "UNTITLED."
- when something is not known: "not in the file."
- mottos: "tota vita mea" (virginia's epitaph ONLY) and "parva puella ·
  magna somnia" (the house seal ONLY). credit line: "a house of little
  girl big dreams."

HARD RULES (violations are defects):
1. the animal is never shown or described whole. damage only.
2. no faces, no victims. print the places, not the people.
3. never explain. publish documents.
4. KJV-register prose, lowercase titles, terse clerk voice.
5. no "shop now" voice, no discount language, no urgency, no countdown.
   the office does not sell. it files, and some files can be purchased.
6. epitaph and seal mottos are never used outside their one place each.
"""

# ── Client (NeuroForge pattern, kept) ────────────────────────────────────────

_SESSION_TOKEN_FILE = "/home/claude/.claude/remote/.session_ingress_token"


class OfficeClient:
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
            print(f"\nerror initializing anthropic client: {e}", file=sys.stderr)
            sys.exit(1)

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        try:
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(
                block.text for block in message.content
                if getattr(block, "type", "") == "text"
            )
        except anthropic.AuthenticationError as e:
            print(f"\nauthentication error: {e}", file=sys.stderr)
            sys.exit(1)
        except anthropic.APIError as e:
            print(f"\napi error: {e}", file=sys.stderr)
            sys.exit(1)


# ── Stages ───────────────────────────────────────────────────────────────────

def stage_dispatch(client: OfficeClient, ctx: dict) -> str:
    user = f"""Write {ctx['count']} new entries for the record — the office's
field dispatches page (record.html). Existing entries run 90-014 through
90-041 (year ninety, march–august); the latest is a canister of film left on
the counter overnight, marked vii, not developed.

Context from the operator: {ctx['context'] or 'none given; continue the year.'}

Each entry:
- a dated header line: year ninety · <month> · entry 90-0NN
- 1–3 sentences of document. terse. things observed and filed, never
  explained. damage reports, counts, items left at the counter.
- may cross-reference the file (lots), the bestiary, or the succession.

Existing lots are 001–011 only (009–011 UNTITLED); reference only these
unless the operator names a new one.

After the entries, provide the same content as ready-to-paste HTML using
this structure for each (the class names "dispatch reveal" and
"entry-date" are required site infrastructure, not voice — keep exactly):
<article class="dispatch reveal">
  <p class="entry-date">year ninety · month · entry 90-0NN</p>
  <p>text with optional <a href="file.html">lot NNN</a> links.</p>
</article>"""
    return client.generate(CANON, user, MAX_TOKENS["dispatch"])


def stage_lot(client: OfficeClient, ctx: dict) -> str:
    user = f"""Draft ONE new holding for the next drop. Existing lots 001–008:
the scripture tee, the chapel baby tee, the estate lot, the confession tee,
the porch light, the cardinal, the breakwater (contract 001), the river hymn.
Lots 009–011 are held as UNTITLED.

Context from the operator: {ctx['context'] or 'none given; propose freely.'}

Provide:
1. lot number and lowercase title
2. epigraph (one line, KJV register)
3. class no. (four digits, dot-prefixed, e.g. class .2600) and a neg. no.
   in the series e-33-00NNNN-mN
4. the print described as a document would describe it (what is on the
   shirt; places not people; if the animal is involved, damage only)
5. shopify product description (3–5 sentences, store voice = clerk voice;
   ends with "edition of 24, numbered by hand." no selling language)
6. price in the $32–$48 range consistent with the line"""
    return client.generate(CANON, user, MAX_TOKENS["lot"])


def stage_shorts(client: OfficeClient, ctx: dict) -> str:
    user = f"""Write 3 short-form video scripts (tiktok/reels, 20–40 seconds
each) for the bandersnatch world. These are documents on film, not ads.

Context from the operator: {ctx['context'] or 'none given; draw from the record.'}

Constraints beyond the hard rules:
- NO faces on camera, ever. hands, places, garments, paper, typewriter keys.
- visual language: lamplight, film grain, wax seals, caption cards, the
  ledger, the county. slow. quiet. text on screen in typewriter register.
- each script: a title (lowercase), a shot list with on-screen text,
  ambient sound notes, and a final card. the final card may say
  "the office is open." or "bandersnatch.world" and nothing else.
- no calls to action. no "link in bio" voice. the door is simply shown."""
    return client.generate(CANON, user, MAX_TOKENS["shorts"])


def stage_letter(client: OfficeClient, ctx: dict) -> str:
    user = f"""Write one estate letter — an email to those signed in the
visitor ledger. The estate writes rarely and never sells your name.

Context from the operator: {ctx['context'] or 'none given; write the season.'}

Requirements:
- subject line: lowercase, terse, in-world (a document reference, not a hook)
- 90–160 words. a letter from the office: what has been filed, what is
  printing, one line of the record. no urgency, no discounts, no "don't
  miss out." purchasable things are mentioned the way a ledger mentions
  them, with a plain link line to bandersnatch.world or the store.
- sign-off: "the office is open." then "— the archivist" """
    return client.generate(CANON, user, MAX_TOKENS["letter"])


STAGES = {
    "dispatch": ("01_dispatches", stage_dispatch),
    "lot": ("02_new_lot", stage_lot),
    "shorts": ("03_shorts_scripts", stage_shorts),
    "letter": ("04_estate_letter", stage_letter),
}

# ── QA pass (NeuroForge pattern, retargeted to canon audit) ──────────────────

QA_SYSTEM = CANON + """
You are now the archivist reviewing a clerk's draft before it is filed.
You are exacting. You check every hard rule. HTML/CSS class names and
markup structure (e.g. class="dispatch reveal", "entry-date") are site
infrastructure, exempt from the voice rules — audit only the words a
visitor reads."""


def qa_pass(client: OfficeClient, stage_name: str, draft: str) -> str:
    user = f"""Audit this draft ({stage_name}) against the hard rules.

DRAFT:
---
{draft}
---

Respond with:
1. VERDICT: PASS or FAIL
2. VIOLATIONS: numbered list citing the rule broken and the offending line
   (or "none")
3. If FAIL: CORRECTED VERSION — the full draft rewritten with violations
   repaired and nothing else changed."""
    return client.generate(QA_SYSTEM, user, MAX_TOKENS["qa"])


# ── Runner ───────────────────────────────────────────────────────────────────

def run(ctx: dict) -> None:
    client = OfficeClient()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", (ctx["context"] or "unprompted").lower())[:40].strip("_")
    out_dir = OUTPUT_BASE_DIR / f"{datetime.now().strftime('%Y%m%d')}_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = list(STAGES) if ctx["mode"] == "full" else [ctx["mode"]]
    total = len(modes) * 2
    step = 0

    print("=" * 60)
    print("  the office — bandersnatch content pipeline")
    print("=" * 60)
    print(f"  mode   : {ctx['mode']}")
    print(f"  context: {ctx['context'] or '(none)'}")
    print(f"  output : {out_dir}/")
    print("=" * 60)

    for mode in modes:
        prefix, fn = STAGES[mode]
        step += 1
        print(f"[{step}/{total}] drafting {mode} ...")
        draft = fn(client, ctx)
        draft_path = out_dir / f"{prefix}_{stamp}.md"
        draft_path.write_text(draft)

        step += 1
        print(f"[{step}/{total}] archivist QA on {mode} ...")
        qa = qa_pass(client, mode, draft)
        (out_dir / f"{prefix}_QA_{stamp}.md").write_text(qa)

        verdict = "PASS" if re.search(r"VERDICT[:*\s]+PASS", qa) else "CHECK QA FILE"
        print(f"        filed: {draft_path.name}  [{verdict}]")

    print("\nthe file is not closed.")


def main() -> None:
    ap = argparse.ArgumentParser(description="bandersnatch office content pipeline")
    ap.add_argument("--mode", choices=VALID_MODES, default="full")
    ap.add_argument("--context", default="", help="operator notes for this run (season, drop theme, plot beats)")
    ap.add_argument("--count", type=int, default=3, help="dispatch entries to write (dispatch mode)")
    args = ap.parse_args()
    run({"mode": args.mode, "context": args.context, "count": args.count})


if __name__ == "__main__":
    main()
