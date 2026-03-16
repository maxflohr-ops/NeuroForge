#!/usr/bin/env python3
"""
NeuroForge OS — DB Score Migration
====================================
Rescales legacy QA scores in neuroforge_db.json from /50 to /60.

Background:
    QA scoring was updated from 5 dimensions (/50) to 6 dimensions (/60)
    when the Entertainment & Readability dimension was added (v2.0 agents).
    Scores stored before this change are on the /50 scale and will look
    artificially low when the optimizer compares them against /60 thresholds.

What this script does:
    Finds all records in neuroforge_db.json with a qa_score, applies a
    proportional rescale (score * 60/50 = score * 1.2), rounds to the
    nearest integer, and writes the updated database back to disk.
    A backup of the original is saved before any changes are made.

Usage:
    python migrate_db_scores.py             # preview — shows what would change
    python migrate_db_scores.py --apply     # apply the rescaling

Notes:
    - Only run this ONCE. The script tags migrated records to prevent
      double-scaling if run again.
    - After migration, Entertainment & Readability will not have been
      independently scored on legacy runs. The rescaled scores should
      be treated as estimates. Run the optimizer with --threshold 50
      after migration to force a fresh optimisation pass.
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent.parent / "neuroforge_db.json"


def load_db():
    if not DB_FILE.exists():
        print("No database found. Nothing to migrate.")
        return None
    with open(DB_FILE) as f:
        return json.load(f)


def rescale(score: int) -> int:
    """Rescale a /50 score to /60 proportionally."""
    return round(score * 60 / 50)


def main():
    parser = argparse.ArgumentParser(description="Migrate neuroforge_db.json scores from /50 to /60")
    parser.add_argument("--apply", action="store_true",
                        help="Apply the rescaling (default: preview only)")
    args = parser.parse_args()

    db = load_db()
    if db is None:
        return

    to_migrate = [r for r in db if r.get("qa_score") is not None and not r.get("score_migrated")]
    already_migrated = [r for r in db if r.get("score_migrated")]
    no_score = [r for r in db if r.get("qa_score") is None]

    print(f"\nDatabase: {DB_FILE}")
    print(f"Total records:     {len(db)}")
    print(f"To migrate:        {len(to_migrate)}")
    print(f"Already migrated:  {len(already_migrated)}")
    print(f"No score (skip):   {len(no_score)}")

    if not to_migrate:
        print("\n✅ Nothing to migrate.")
        return

    print("\nPreview of changes:")
    print(f"  {'Topic':<35} {'Agent':<30} {'Old':>5} {'New':>5}")
    print("  " + "─" * 75)
    for record in to_migrate:
        old = record["qa_score"]
        new = rescale(old)
        topic = record.get("topic", "unknown")[:34]
        agent = record.get("agent", "unknown")[:29]
        print(f"  {topic:<35} {agent:<30} {old:>5} {new:>5}")

    if not args.apply:
        print(f"\nPreview only. Run with --apply to rescale {len(to_migrate)} records.")
        return

    # Backup before writing
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_FILE.with_name(f"neuroforge_db_pre_migration_{timestamp}.json")
    shutil.copy(DB_FILE, backup)
    print(f"\n✓ Backup saved to: {backup.name}")

    # Apply migration
    for record in db:
        if record.get("qa_score") is not None and not record.get("score_migrated"):
            record["qa_score"] = rescale(record["qa_score"])
            record["score_migrated"] = True

    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

    print(f"✓ Migrated {len(to_migrate)} records in {DB_FILE.name}")
    print("\n⚠️  Note: Legacy scores are proportional estimates — the Entertainment &")
    print("   Readability dimension was not independently scored on these runs.")
    print("   Run: python optimize_prompts.py --threshold 50 --apply")
    print("   to force a fresh optimisation pass using the migrated data.")


if __name__ == "__main__":
    main()
