#!/usr/bin/env python3
"""
Delete deprecated Airtable tables from the Florra base.

Tables to delete:
  - NeuroForge Projects  (tblkslL7m7mORCHkR)
  - Pipeline Runs         (tblxxJIc9VXjZwQMT)
  - Agent Performance     (tbl2F024MIEMh26ng)
  - Improvement Suggestions (tblKhnROIh8ssTqiE)

Prerequisites:
    export AIRTABLE_API_KEY="patXXX..."

Usage:
    python delete_old_tables.py               # delete all 4 tables
    python delete_old_tables.py --dry-run     # preview without deleting
"""

import os
import sys
import time

import requests

AIRTABLE_API = "https://api.airtable.com/v0"
BASE_ID = "applXEAjh6k3Xmybl"

TABLES_TO_DELETE = [
    ("tblkslL7m7mORCHkR", "NeuroForge Projects"),
    ("tblxxJIc9VXjZwQMT", "Pipeline Runs"),
    ("tbl2F024MIEMh26ng", "Agent Performance"),
    ("tblKhnROIh8ssTqiE", "Improvement Suggestions"),
]


def main():
    dry_run = "--dry-run" in sys.argv

    key = os.environ.get("AIRTABLE_API_KEY")
    if not key:
        print("Error: AIRTABLE_API_KEY must be set.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {key}"}

    # Verify tables exist first
    print("Verifying tables...")
    r = requests.get(
        f"{AIRTABLE_API}/meta/bases/{BASE_ID}/tables",
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    existing = {t["id"]: t["name"] for t in r.json().get("tables", [])}

    for table_id, expected_name in TABLES_TO_DELETE:
        actual_name = existing.get(table_id)
        if actual_name is None:
            print(f"  SKIP: {expected_name} ({table_id}) — not found (already deleted?)")
            continue
        if actual_name != expected_name:
            print(f"  WARNING: {table_id} is '{actual_name}', not '{expected_name}' — skipping for safety")
            continue

        if dry_run:
            print(f"  [DRY RUN] Would delete: {actual_name} ({table_id})")
            continue

        print(f"  Deleting: {actual_name} ({table_id})...", end=" ")
        resp = requests.delete(
            f"{AIRTABLE_API}/meta/bases/{BASE_ID}/tables/{table_id}",
            headers=headers,
            timeout=15,
        )
        if resp.ok:
            print("done")
        else:
            print(f"FAILED ({resp.status_code}: {resp.text[:200]})")
        time.sleep(0.3)

    print("\nFinished.")


if __name__ == "__main__":
    main()
