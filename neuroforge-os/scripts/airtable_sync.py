#!/usr/bin/env python3
"""
NeuroForge Airtable Sync — syncs generated content to Airtable
Supports dry-run preview and auto-creates tables if they don't exist.
"""

import os
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

# Airtable API
AIRTABLE_API_BASE = "https://api.airtable.com/v0"
PROJECTS_TABLE = "NeuroForge Projects"
PIPELINE_RUNS_TABLE = "Pipeline Runs"


class AirtableSync:
    def __init__(self, api_key: str, base_id: str, dry_run: bool = False):
        self.api_key = api_key
        self.base_id = base_id
        self.dry_run = dry_run
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.output_dir = Path(os.getenv("NEUROFORGE_OUTPUT_DIR", Path(__file__).resolve().parent.parent / "output"))
        self.db_file = Path(os.getenv("NEUROFORGE_DB_FILE", Path(__file__).resolve().parent.parent / "neuroforge_db.json"))

    def log(self, message: str, prefix: str = "ℹ️ "):
        print(f"{prefix} {message}")

    def error(self, message: str):
        print(f"❌ {message}")

    def success(self, message: str):
        print(f"✓ {message}")

    def ensure_tables_exist(self):
        """Create tables if they don't exist."""
        self.log("Checking Airtable tables...", "🔍")
        
        # Get existing tables
        response = requests.get(
            f"{AIRTABLE_API_BASE}/meta/bases/{self.base_id}/tables",
            headers=self.headers
        )
        
        if response.status_code != 200:
            self.error(f"Failed to fetch tables: {response.text}")
            return False
        
        existing_tables = {t["name"] for t in response.json().get("tables", [])}
        
        # Create Projects table if missing
        if PROJECTS_TABLE not in existing_tables:
            self.log(f"Creating '{PROJECTS_TABLE}' table...", "📝")
            self._create_projects_table()
        
        # Create Pipeline Runs table if missing
        if PIPELINE_RUNS_TABLE not in existing_tables:
            self.log(f"Creating '{PIPELINE_RUNS_TABLE}' table...", "📝")
            self._create_pipeline_runs_table()
        
        self.success("Tables ready")
        return True

    def _create_projects_table(self):
        """Create NeuroForge Projects table."""
        data = {
            "fields": [
                {"name": "Topic", "type": "singleLineText"},
                {"name": "Faculty", "type": "singleLineText"},
                {"name": "Status", "type": "singleSelect", "options": [
                    {"name": "Draft"},
                    {"name": "Generated"},
                    {"name": "QA Review"},
                    {"name": "Published"}
                ]},
                {"name": "Research Brief", "type": "singleLineText"},
                {"name": "Book Blueprint", "type": "singleLineText"},
                {"name": "Manuscript", "type": "singleLineText"},
                {"name": "Short Scripts", "type": "singleLineText"},
                {"name": "Funnel Copy", "type": "singleLineText"},
                {"name": "QA Notes", "type": "multilineText"}
            ]
        }
        
        response = requests.post(
            f"{AIRTABLE_API_BASE}/meta/bases/{self.base_id}/tables",
            headers=self.headers,
            json=data
        )
        
        if response.status_code not in [200, 201]:
            self.error(f"Failed to create Projects table: {response.text}")
        else:
            self.success(f"Created '{PROJECTS_TABLE}' table")

    def _create_pipeline_runs_table(self):
        """Create Pipeline Runs table."""
        data = {
            "fields": [
                {"name": "Topic", "type": "singleLineText"},
                {"name": "Faculty", "type": "singleLineText"},
                {"name": "Timestamp", "type": "singleLineText"},
                {"name": "Duration (sec)", "type": "number"},
                {"name": "Status", "type": "singleSelect", "options": [
                    {"name": "Success"},
                    {"name": "Failed"},
                    {"name": "In Progress"}
                ]},
                {"name": "Mode", "type": "singleLineText"},
                {"name": "QA Score", "type": "number"},
                {"name": "Error Log", "type": "multilineText"}
            ]
        }
        
        response = requests.post(
            f"{AIRTABLE_API_BASE}/meta/bases/{self.base_id}/tables",
            headers=self.headers,
            json=data
        )
        
        if response.status_code not in [200, 201]:
            self.error(f"Failed to create Pipeline Runs table: {response.text}")
        else:
            self.success(f"Created '{PIPELINE_RUNS_TABLE}' table")

    def get_file_url(self, filepath: Path) -> Optional[str]:
        """Convert local file path to a URL-like reference."""
        if filepath.exists():
            return f"file://{filepath.absolute()}"
        return None

    def sync_projects(self, topic: Optional[str] = None):
        """Sync generated projects to Airtable."""
        self.log("Syncing projects to Airtable...", "📤")
        
        topics = []
        if topic:
            topics = [topic]
        else:
            # Find all topics in output dir
            if self.output_dir.exists():
                topics = [d.name for d in self.output_dir.iterdir() if d.is_dir()]
        
        if not topics:
            self.log("No topics found to sync", "⚠️ ")
            return
        
        for topic_name in sorted(topics):
            topic_dir = self.output_dir / topic_name
            if not topic_dir.exists():
                continue
            
            # Find the latest files for this topic
            research = self._find_latest_file(topic_dir, "01_research_brief")
            blueprint = self._find_latest_file(topic_dir, "02_book_blueprint")
            manuscript = self._find_latest_file(topic_dir, "03_chapter_01")
            scripts = self._find_latest_file(topic_dir, "04_shorts_scripts")
            funnel = self._find_latest_file(topic_dir, "05_funnel_copy")
            
            # Extract faculty from research brief
            faculty = self._extract_faculty(research) if research else "Unknown"
            
            record = {
                "fields": {
                    "Topic": topic_name.replace("_", " ").title(),
                    "Faculty": faculty,
                    
                    "Research Brief": str(research) if research else "",
                    "Book Blueprint": str(blueprint) if blueprint else "",
                    "Manuscript": str(manuscript) if manuscript else "",
                    "Short Scripts": str(scripts) if scripts else "",
                    "Funnel Copy": str(funnel) if funnel else "",
                }
            }
            
            if self.dry_run:
                self.log(f"[DRY-RUN] Would sync: {topic_name}", "🔄")
                print(json.dumps(record, indent=2))
            else:
                # Post to Airtable
                response = requests.post(
                    f"{AIRTABLE_API_BASE}/{self.base_id}/{PROJECTS_TABLE}",
                    headers=self.headers,
                    json=record
                )
                
                if response.status_code in [200, 201]:
                    self.success(f"Synced: {topic_name}")
                else:
                    self.error(f"Failed to sync {topic_name}: {response.text}")

    def _find_latest_file(self, directory: Path, prefix: str) -> Optional[Path]:
        """Find the latest file with given prefix."""
        files = list(directory.glob(f"{prefix}*.md"))
        if files:
            return sorted(files)[-1]
        return None

    def _extract_faculty(self, filepath: Path) -> str:
        """Extract faculty name from markdown file."""
        try:
            with open(filepath, "r") as f:
                content = f.read()
                if "**Faculty:**" in content:
                    line = [l for l in content.split("\n") if "**Faculty:**" in l][0]
                    return line.split("**Faculty:**")[-1].strip()
        except (OSError, ValueError):
            pass
        return "Unknown"

    def sync_pipeline_runs(self, topic: Optional[str] = None):
        """Sync pipeline run logs to Airtable."""
        self.log("Syncing pipeline runs...", "📊")
        
        if not self.db_file.exists():
            self.log("No pipeline database found", "⚠️ ")
            return
        
        try:
            with open(self.db_file, "r") as f:
                db = json.load(f)
        except (OSError, ValueError) as e:
            self.error(f"Failed to read pipeline database: {e}")
            return
        
        # Handle both list and dict formats
        if isinstance(db, list):
            runs = db
        else:
            runs = db.get("runs", [])
        
        if topic:
            runs = [r for r in runs if r.get("topic", "").lower() == topic.lower()]
        
        if not runs:
            self.log("No pipeline runs to sync", "⚠️ ")
            return
        
        for run in runs:
            record = {
                "fields": {
                    "Topic": run.get("topic", ""),
                    "Faculty": run.get("faculty", ""),
                    "Timestamp": run.get("timestamp", ""),
                    
                    
                    "Mode": run.get("mode", ""),
                    
                }
            }
            
            if self.dry_run:
                self.log(f"[DRY-RUN] Would sync run: {run.get('topic')}", "🔄")
                print(json.dumps(record, indent=2))
            else:
                response = requests.post(
                    f"{AIRTABLE_API_BASE}/{self.base_id}/{PIPELINE_RUNS_TABLE}",
                    headers=self.headers,
                    json=record
                )
                
                if response.status_code in [200, 201]:
                    self.success(f"Synced run: {run.get('topic')}")
                else:
                    self.error(f"Failed to sync run: {response.text}")


def main():
    parser = argparse.ArgumentParser(
        description="NeuroForge Airtable Sync"
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Sync specific topic only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sync without writing to Airtable"
    )
    
    args = parser.parse_args()
    
    # Get credentials from env
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    
    if not api_key or not base_id:
        print("❌ Missing AIRTABLE_API_KEY or AIRTABLE_BASE_ID in .env")
        exit(1)
    
    sync = AirtableSync(api_key, base_id, dry_run=args.dry_run)
    
    # Ensure tables exist
    if not sync.ensure_tables_exist():
        exit(1)
    
    print("\n" + "="*60)
    if args.dry_run:
        print("  DRY-RUN MODE — No changes will be written")
    else:
        print("  LIVE SYNC — Writing to Airtable")
    print("="*60 + "\n")
    
    # Sync projects
    sync.sync_projects(topic=args.topic)
    
    print()
    
    # Sync pipeline runs
    sync.sync_pipeline_runs(topic=args.topic)
    
    print("\n" + "="*60)
    print("  Sync complete!")
    print("="*60)


if __name__ == "__main__":
    main()
