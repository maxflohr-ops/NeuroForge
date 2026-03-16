#!/usr/bin/env python3
"""
NeuroForge OS — Airtable Sync
================================
Pushes all NeuroForge project data into the Florra Airtable base.

Creates (or updates) a "NeuroForge Projects" table with one row per book,
plus a linked "Pipeline Runs" table logging every agent output.

Prerequisites:
    export AIRTABLE_API_KEY="patXXX..."
    export AIRTABLE_BASE_ID="applXXX..."

Usage:
    python airtable_sync.py               # sync all topics
    python airtable_sync.py --dry-run     # print records without writing
    python airtable_sync.py --topic "Stop Overthinking"   # one topic only

Output:
    Prints created/updated record IDs per table.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

AIRTABLE_API = "https://api.airtable.com/v0"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _creds() -> tuple[str, str]:
    key = os.environ.get("AIRTABLE_API_KEY")
    base = os.environ.get("AIRTABLE_BASE_ID")
    if not key or not base:
        print("Error: AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set.")
        sys.exit(1)
    return key, base


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _get(key: str, base: str, path: str) -> dict:
    r = requests.get(f"{AIRTABLE_API}/{path}", headers=_headers(key), timeout=15)
    r.raise_for_status()
    return r.json()


def _post(key: str, base: str, table: str, records: list, dry_run: bool) -> list:
    """Create records in batches of 10 (Airtable limit)."""
    if dry_run:
        for rec in records:
            print(f"    [DRY RUN] Would create: {json.dumps(rec['fields'], ensure_ascii=False)[:120]}")
        return []

    created = []
    for i in range(0, len(records), 10):
        batch = records[i:i + 10]
        r = requests.post(
            f"{AIRTABLE_API}/{base}/{_encode(table)}",
            headers=_headers(key),
            json={"records": batch},
            timeout=20,
        )
        if not r.ok:
            print(f"  Error creating records: {r.status_code} {r.text[:300]}")
            r.raise_for_status()
        created.extend(r.json().get("records", []))
        time.sleep(0.25)  # stay under 5 req/s rate limit
    return created


def _patch(key: str, base: str, table: str, record_id: str, fields: dict, dry_run: bool):
    """Update a single record."""
    if dry_run:
        print(f"    [DRY RUN] Would update {record_id}: {str(fields)[:100]}")
        return
    r = requests.patch(
        f"{AIRTABLE_API}/{base}/{_encode(table)}/{record_id}",
        headers=_headers(key),
        json={"fields": fields},
        timeout=15,
    )
    r.raise_for_status()


def _encode(name: str) -> str:
    """URL-encode a table name."""
    from urllib.parse import quote
    return quote(name, safe="")


def _list_tables(key: str, base: str) -> dict[str, str]:
    """Returns {table_name: table_id}."""
    data = _get(key, base, f"meta/bases/{base}/tables")
    return {t["name"]: t["id"] for t in data.get("tables", [])}


def _list_records(key: str, base: str, table: str) -> list[dict]:
    """Fetch all records from a table."""
    records = []
    params = {}
    while True:
        r = requests.get(
            f"{AIRTABLE_API}/{base}/{_encode(table)}",
            headers=_headers(key),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
        time.sleep(0.25)
    return records


def _create_table(key: str, base: str, name: str, fields: list) -> str:
    """Create a new table. Returns table_id."""
    r = requests.post(
        f"{AIRTABLE_API}/meta/bases/{base}/tables",
        headers=_headers(key),
        json={"name": name, "fields": fields},
        timeout=15,
    )
    if not r.ok:
        print(f"  Error creating table '{name}': {r.status_code} {r.text[:400]}")
        r.raise_for_status()
    return r.json()["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Data builders
# ─────────────────────────────────────────────────────────────────────────────

# Agent label → friendly stage name
AGENT_STAGE = {
    "Research Agent":       "Research",
    "Book Architect Agent": "Blueprint",
    "Manuscript Agent Ch1": "Chapter 1",
    "Shorts Script Agent":  "Shorts Scripts",
    "Funnel Agent":         "Funnel Copy",
}

STAGE_ORDER = ["Research", "Blueprint", "Chapter 1", "Shorts Scripts", "Funnel Copy"]


def _load_db() -> list[dict]:
    db_path = PROJECT_DIR / "neuroforge_db.json"
    return json.loads(db_path.read_text(encoding="utf-8"))


def _project_records(db: list[dict], filter_topic: str | None) -> list[dict]:
    """
    One record per topic for the Projects table.
    """
    by_topic: dict[str, dict] = {}

    for entry in db:
        topic = entry["topic"]
        if filter_topic and topic != filter_topic:
            continue

        if topic not in by_topic:
            safe = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
            scripts_dir = OUTPUT_DIR / safe / "scripts_parsed"
            script_count = len(list(scripts_dir.glob("script_*.json"))) if scripts_dir.exists() else 0

            by_topic[topic] = {
                "topic": topic,
                "stages_done": [],
                "qa_scores": [],
                "script_count": script_count,
                "last_run": entry["timestamp"],
            }

        stage = AGENT_STAGE.get(entry["agent"], entry["agent"])
        by_topic[topic]["stages_done"].append(stage)

        if entry.get("qa_score") is not None:
            by_topic[topic]["qa_scores"].append(entry["qa_score"])

        if entry["timestamp"] > by_topic[topic]["last_run"]:
            by_topic[topic]["last_run"] = entry["timestamp"]

    records = []
    for topic, data in by_topic.items():
        stages_done = data["stages_done"]
        all_stages_complete = all(s in stages_done for s in STAGE_ORDER)
        avg_qa = round(sum(data["qa_scores"]) / len(data["qa_scores"]), 1) if data["qa_scores"] else None

        # Determine status
        if all_stages_complete:
            status = "Ready for Production"
        elif "Chapter 1" in stages_done:
            status = "In Progress"
        else:
            status = "Research Phase"

        fields: dict = {
            "Project Name":     topic,
            "Status":           status,
            "Stages Complete":  ", ".join(s for s in STAGE_ORDER if s in stages_done),
            "Shorts Scripts":   data["script_count"],
            "Last Run":         data["last_run"][:10],  # date only
        }
        if avg_qa is not None:
            fields["Avg QA Score"] = avg_qa

        records.append({"fields": fields})

    return records


def _pipeline_run_records(db: list[dict], filter_topic: str | None,
                           project_id_map: dict[str, str]) -> list[dict]:
    """
    One record per agent run for the Pipeline Runs table.
    Links back to the Projects table via record ID.
    """
    records = []
    for entry in db:
        topic = entry["topic"]
        if filter_topic and topic != filter_topic:
            continue

        fields: dict = {
            "Topic":      topic,
            "Agent":      entry["agent"],
            "Stage":      AGENT_STAGE.get(entry["agent"], entry["agent"]),
            "Timestamp":  entry["timestamp"][:10],
            "Output File": Path(entry["output_file"]).name,
        }
        if entry.get("qa_score") is not None:
            fields["QA Score"] = entry["qa_score"]

        # Link to project record if we have the ID
        if topic in project_id_map:
            fields["Project"] = [project_id_map[topic]]

        records.append({"fields": fields})

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Table schema definitions
# ─────────────────────────────────────────────────────────────────────────────

PROJECTS_FIELDS = [
    {"name": "Project Name",    "type": "singleLineText"},
    {"name": "Status",          "type": "singleSelect",
     "options": {"choices": [
         {"name": "Research Phase",        "color": "yellowLight2"},
         {"name": "In Progress",           "color": "blueLight2"},
         {"name": "Ready for Production",  "color": "greenLight2"},
         {"name": "Live",                  "color": "greenBright"},
     ]}},
    {"name": "Stages Complete",  "type": "singleLineText"},
    {"name": "Shorts Scripts",   "type": "number",    "options": {"precision": 0}},
    {"name": "Avg QA Score",     "type": "number",    "options": {"precision": 1}},
    {"name": "Last Run",         "type": "date",      "options": {"dateFormat": {"name": "iso"}}},
]

PIPELINE_RUNS_FIELDS = [
    {"name": "Topic",       "type": "singleLineText"},
    {"name": "Agent",       "type": "singleLineText"},
    {"name": "Stage",       "type": "singleSelect",
     "options": {"choices": [
         {"name": s, "color": c} for s, c in zip(
             STAGE_ORDER,
             ["yellowLight2", "blueLight2", "purpleLight2", "pinkLight2", "orangeLight2"]
         )
     ]}},
    {"name": "QA Score",    "type": "number",    "options": {"precision": 0}},
    {"name": "Timestamp",   "type": "date",      "options": {"dateFormat": {"name": "iso"}}},
    {"name": "Output File", "type": "singleLineText"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Main sync logic
# ─────────────────────────────────────────────────────────────────────────────

def sync(dry_run: bool, filter_topic: str | None):
    key, base = _creds()

    print(f"\n{'='*60}")
    print(f"  AIRTABLE SYNC — Florra")
    print(f"  Base:  {base}")
    print(f"  Mode:  {'DRY RUN' if dry_run else 'LIVE'}")
    if filter_topic:
        print(f"  Topic: {filter_topic}")
    print(f"{'='*60}\n")

    # ── Discover existing tables ──────────────────────────────────
    print("[ Checking existing tables ]")
    tables = _list_tables(key, base)
    print(f"  Found tables: {', '.join(tables.keys()) or '(none)'}")

    # ── Ensure Projects table exists ─────────────────────────────
    projects_table = "NeuroForge Projects"
    if projects_table not in tables:
        print(f"\n  Creating table: {projects_table}")
        if not dry_run:
            _create_table(key, base, projects_table, PROJECTS_FIELDS)
            tables = _list_tables(key, base)  # refresh
        else:
            print(f"  [DRY RUN] Would create table: {projects_table}")
    else:
        print(f"  Table exists: {projects_table}")

    # ── Ensure Pipeline Runs table exists ────────────────────────
    runs_table = "Pipeline Runs"
    if runs_table not in tables:
        print(f"\n  Creating table: {runs_table}")
        if not dry_run:
            _create_table(key, base, runs_table, PIPELINE_RUNS_FIELDS)
            tables = _list_tables(key, base)
        else:
            print(f"  [DRY RUN] Would create table: {runs_table}")
    else:
        print(f"  Table exists: {runs_table}")

    # ── Load data ─────────────────────────────────────────────────
    db = _load_db()
    project_records = _project_records(db, filter_topic)

    # ── Check for existing project records (avoid duplicates) ────
    print(f"\n[ Syncing {projects_table} ]")
    existing_projects = {} if dry_run else {
        rec["fields"].get("Project Name"): rec["id"]
        for rec in _list_records(key, base, projects_table)
        if rec.get("fields", {}).get("Project Name")
    }

    project_id_map: dict[str, str] = {}
    to_create = []
    to_update = []

    for rec in project_records:
        name = rec["fields"]["Project Name"]
        if name in existing_projects:
            to_update.append((existing_projects[name], rec["fields"]))
        else:
            to_create.append(rec)

    if to_create:
        print(f"  Creating {len(to_create)} project(s)...")
        created = _post(key, base, projects_table, to_create, dry_run)
        for c in created:
            project_id_map[c["fields"]["Project Name"]] = c["id"]
            print(f"  ✓ Created: {c['fields']['Project Name']} ({c['id']})")

    if to_update:
        print(f"  Updating {len(to_update)} project(s)...")
        for rec_id, fields in to_update:
            if not dry_run:
                _patch(key, base, projects_table, rec_id, fields, dry_run)
            # recover project name → id mapping for linking
            name = fields["Project Name"]
            project_id_map[name] = rec_id
            print(f"  ✓ Updated: {name} ({rec_id})")

    # also carry over any existing IDs not updated
    project_id_map.update({k: v for k, v in existing_projects.items() if k not in project_id_map})

    # ── Pipeline Runs ─────────────────────────────────────────────
    print(f"\n[ Syncing {runs_table} ]")
    existing_runs = set() if dry_run else {
        (rec["fields"].get("Topic", ""), rec["fields"].get("Output File", ""))
        for rec in _list_records(key, base, runs_table)
    }

    run_records = _pipeline_run_records(db, filter_topic, project_id_map)
    new_runs = [
        r for r in run_records
        if (r["fields"]["Topic"], r["fields"]["Output File"]) not in existing_runs
    ]

    if new_runs:
        print(f"  Creating {len(new_runs)} run record(s)...")
        created_runs = _post(key, base, runs_table, new_runs, dry_run)
        print(f"  ✓ {len(created_runs)} run records created.")
    else:
        print(f"  All run records already synced.")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SYNC COMPLETE")
    print(f"  Projects:  {len(to_create)} created, {len(to_update)} updated")
    print(f"  Runs:      {len(new_runs)} new records")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Sync NeuroForge data to Airtable Florra base")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--topic", default="", help="Sync a single topic only")
    args = parser.parse_args()

    sync(dry_run=args.dry_run, filter_topic=args.topic or None)


if __name__ == "__main__":
    main()
