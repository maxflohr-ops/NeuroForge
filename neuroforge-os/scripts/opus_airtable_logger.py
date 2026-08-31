#!/usr/bin/env python3
"""
Opus → Airtable Logger
Logs clipping projects, clips, scheduling, and performance
"""

import os
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional

class OpusAirtableLogger:
    def __init__(self):
        self.api_key = os.getenv("AIRTABLE_API_KEY", "AIRTABLE_API_KEY")
        self.base_id = os.getenv("AIRTABLE_BASE_ID", "applXEAjh6k3Xmybl")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.api_base = "https://api.airtable.com/v0"
        
        # Table IDs
        self.tables = {
            "projects": "tblvMbbfjYrOuPqwS",
            "clips": "tblW3n5Fjr9lBgJph",
            "scheduling": "tblKYGRy5jU89q66Z",
            "podcasts": "tblT4R7RtjEpDcwi3",
            "performance": "tblSOYD7BfyIY77e6"
        }

    def create_project(self, project_name: str, source_url: str, source_type: str = "Podcast", notes: str = ""):
        """Create a new Opus project"""
        record = {
            "fields": {
                "Project Name": project_name,
                "Source URL": source_url,
                "Source Type": source_type,
                "Status": "Processing",
                "Processing Started": datetime.now().isoformat(),
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['projects']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to create project: {response.text}")
            return None

    def log_clip(self, project: str, clip_number: int, title: str, duration_sec: int = 0,
                 start_time: str = "", end_time: str = "", thumbnail_url: str = "",
                 video_url: str = "", download_path: str = "", speakers: str = "",
                 topics: str = "", keywords: str = "", quality_score: int = 0, notes: str = ""):
        """Log a generated clip"""
        record = {
            "fields": {
                "Project": project,
                "Clip Title": title,
                "Start Time": start_time,
                "End Time": end_time,
                "Thumbnail URL": thumbnail_url,
                "Video URL": video_url,
                "Download Path": download_path,
                "Speakers": speakers,
                "Topics": topics,
                "Keywords": keywords,
                "Engagement Predicted": "Pending",
                "Platform Ready": "Yes",
                "Posted To": "",
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['clips']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to log clip: {response.text}")
            return None

    def schedule_clip(self, clip: str, platform: str, scheduled_date: str, 
                     caption: str = "", hashtags: str = "", campaign: str = "", notes: str = ""):
        """Schedule a clip for posting"""
        record = {
            "fields": {
                "Clip": clip,
                "Platform": platform,
                "Scheduled Date": scheduled_date,
                "Scheduled Time": datetime.now().strftime("%H:%M"),
                "Post Status": "Scheduled",
                "Caption": caption,
                "Hashtags": hashtags,
                "Campaign": campaign,
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['scheduling']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to schedule clip: {response.text}")
            return None

    def add_podcast(self, podcast_name: str, host: str, rss_feed_url: str = "", 
                   auto_clip_enabled: bool = True, notes: str = ""):
        """Add podcast for auto-clipping"""
        record = {
            "fields": {
                "Podcast Name": podcast_name,
                "Host": host,
                "RSS Feed URL": rss_feed_url,
                "Auto Clip Enabled": "Yes" if auto_clip_enabled else "No",
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['podcasts']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to add podcast: {response.text}")
            return None

    def log_performance(self, clip_id: str, platform: str, views: int = 0, likes: int = 0,
                       shares: int = 0, comments: int = 0, engagement_rate: float = 0.0, posted_date: str = ""):
        """Log clip performance metrics"""
        record = {
            "fields": {
                "Clip ID": clip_id,
                "Platform": platform,
                "Posted Date": posted_date or datetime.now().isoformat(),
                "Data Updated": datetime.now().isoformat(),
                "Notes": f"Views: {views}, Likes: {likes}, Shares: {shares}, Comments: {comments}"
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['performance']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to log performance: {response.text}")
            return None

    def update_project_status(self, record_id: str, status: str, clips_generated: int = 0):
        """Update project status"""
        fields = {
            "Status": status,
            "Processing Completed": datetime.now().isoformat() if status == "Completed" else ""
        }
        
        if clips_generated > 0:
            fields["Clips Generated"] = clips_generated
        
        response = requests.patch(
            f"{self.api_base}/{self.base_id}/{self.tables['projects']}/{record_id}",
            headers=self.headers,
            json={"fields": fields}
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to update project: {response.text}")
            return None

    def mark_clip_posted(self, clip_record_id: str, platform: str):
        """Mark clip as posted"""
        response = requests.patch(
            f"{self.api_base}/{self.base_id}/{self.tables['clips']}/{clip_record_id}",
            headers=self.headers,
            json={"fields": {"Posted To": platform}}
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to mark clip as posted: {response.text}")
            return None

    def get_scheduled_clips(self) -> List[Dict]:
        """Get all scheduled clips"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['scheduling']}?filterByFormula={{Post Status}}='Scheduled'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def get_project_clips(self, project_name: str) -> List[Dict]:
        """Get all clips for a project"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['clips']}?filterByFormula={{Project}}='{project_name}'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def get_auto_clip_podcasts(self) -> List[Dict]:
        """Get all podcasts with auto-clipping enabled"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['podcasts']}?filterByFormula={{Auto Clip Enabled}}='Yes'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []


# Example usage
if __name__ == "__main__":
    logger = OpusAirtableLogger()
    
    print("✓ Opus Airtable Logger initialized")
    print("\nAvailable methods:")
    print("  - create_project(project_name, source_url, source_type)")
    print("  - log_clip(project, clip_number, title, ...)")
    print("  - schedule_clip(clip, platform, scheduled_date, ...)")
    print("  - add_podcast(podcast_name, host, rss_feed_url, ...)")
    print("  - log_performance(clip_id, platform, views, likes, ...)")
    print("  - update_project_status(record_id, status, clips_generated)")
    print("  - mark_clip_posted(clip_record_id, platform)")
    print("  - get_scheduled_clips()")
    print("  - get_project_clips(project_name)")
    print("  - get_auto_clip_podcasts()")
