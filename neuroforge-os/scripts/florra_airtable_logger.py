#!/usr/bin/env python3
"""
Florra → Airtable Logger
Logs creator research, UGC pipeline progress, and content library
"""

import os
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional

class FlorraAirtableLogger:
    def __init__(self):
        self.api_key = os.getenv("AIRTABLE_API_KEY", "AIRTABLE_API_KEY
        self.base_id = os.getenv("AIRTABLE_BASE_ID", "applXEAjh6k3Xmybl")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.api_base = "https://api.airtable.com/v0"
        
        # Table IDs from Florra setup
        self.tables = {
            "people": "tblYqPt2BYVjMaXFk",  # Existing People table
            "ugc_pipeline": "tblqTn9O3rIMMecbT",
            "content_library": "tblmKJcNNOeEUaI79",
            "spark_codes": "tblqRpE6Ou9vXImey",
            "campaigns": "tblMUfJKvYiOEARy3",  # Existing Campaigns table
            "metadata": "tbleJMnUc8u59V72L"
        }

    def add_creator(self, name: str, tiktok_handle: str = "", instagram_handle: str = "", 
                   tiktok_followers: int = 0, country: str = "", engagement_rate: float = 0,
                   follower_tier: str = "", overall_score: float = 0, profile_url: str = "", notes: str = ""):
        """Add a creator to People table"""
        record = {
            "fields": {
                "Name": name,
                "TikTok Handle": tiktok_handle,
                "Instagram Handle": instagram_handle,
                "TikTok Followers": tiktok_followers,
                "Country": country,
                "Engagement Rate": engagement_rate,
                "Follower Tier": follower_tier,
                "Overall Score": overall_score,
                "Profile URL": profile_url,
                "Added Date": datetime.now().isoformat(),
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['people']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to add creator: {response.text}")
            return None

    def add_to_ugc_pipeline(self, creator: str, campaign: str, sound: str, sound_id: str, 
                           status: str = "Identified", video_url: str = "", spark_code: str = "", notes: str = ""):
        """Add creator to UGC Pipeline"""
        record = {
            "fields": {
                "Creator": creator,
                "Campaign": campaign,
                "Sound": sound,
                "Sound ID": sound_id,
                "Status": status,
                "Video URL": video_url,
                "Spark Code": spark_code,
                "Identified Date": datetime.now().isoformat(),
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['ugc_pipeline']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to add to pipeline: {response.text}")
            return None

    def add_to_content_library(self, creator: str, platform: str, filename: str, file_path: str,
                              hashtags: str = "", sound_used: str = "", quality_score: int = 0,
                              original_url: str = "", campaign_tags: str = "", usable_for_ads: str = "Yes", notes: str = ""):
        """Add downloaded content to library"""
        record = {
            "fields": {
                "Creator": creator,
                "Platform": platform,
                "Filename": filename,
                "File Path": file_path,
                "Hashtags": hashtags,
                "Sound Used": sound_used,
                "Quality Score": quality_score,
                "Original URL": original_url,
                "Downloaded Date": datetime.now().isoformat(),
                "Campaign Tags": campaign_tags,
                "Usable for Ads": usable_for_ads,
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['content_library']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to add to content library: {response.text}")
            return None

    def add_spark_code(self, creator: str, tiktok_handle: str, spark_code: str, video_url: str,
                      campaign: str = "", status: str = "Active", code_expiry: str = "", notes: str = ""):
        """Track TikTok Spark Ad codes"""
        record = {
            "fields": {
                "Creator": creator,
                "TikTok Handle": tiktok_handle,
                "Spark Code": spark_code,
                "Video URL": video_url,
                "Campaign": campaign,
                "Status": status,
                "Code Expiry": code_expiry,
                "Activated Date": datetime.now().isoformat(),
                "Notes": notes
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['spark_codes']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to add spark code: {response.text}")
            return None

    def update_pipeline_status(self, record_id: str, status: str, stage_date: str = ""):
        """Update UGC Pipeline status"""
        # Map status to date field
        date_field = {
            "Identified": "Identified Date",
            "Outreach": "Outreach Date",
            "Contract": "Contract Date",
            "Content": "Content Received Date",
            "Paid": "Paid Date"
        }.get(status, "")
        
        fields = {"Status": status}
        if date_field and stage_date == "":
            fields[date_field] = datetime.now().isoformat()
        
        response = requests.patch(
            f"{self.api_base}/{self.base_id}/{self.tables['ugc_pipeline']}/{record_id}",
            headers=self.headers,
            json={"fields": fields}
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to update pipeline status: {response.text}")
            return None

    def get_creators_by_tier(self, tier: str) -> List[Dict]:
        """Get all creators in a follower tier"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['people']}?filterByFormula={{Follower Tier}}='{tier}'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def get_pipeline_by_status(self, status: str) -> List[Dict]:
        """Get all pipeline entries with given status"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['ugc_pipeline']}?filterByFormula={{Status}}='{status}'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def get_content_by_creator(self, creator: str) -> List[Dict]:
        """Get all content for a creator"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['content_library']}?filterByFormula={{Creator}}='{creator}'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []


# Example usage
if __name__ == "__main__":
    logger = FlorraAirtableLogger()
    
    print("✓ Florra Airtable Logger initialized")
    print("\nAvailable methods:")
    print("  - add_creator(name, tiktok_handle, ...)")
    print("  - add_to_ugc_pipeline(creator, campaign, sound, sound_id, ...)")
    print("  - add_to_content_library(creator, platform, filename, ...)")
    print("  - add_spark_code(creator, tiktok_handle, spark_code, ...)")
    print("  - update_pipeline_status(record_id, status)")
    print("  - get_creators_by_tier(tier)")
    print("  - get_pipeline_by_status(status)")
    print("  - get_content_by_creator(creator)")
