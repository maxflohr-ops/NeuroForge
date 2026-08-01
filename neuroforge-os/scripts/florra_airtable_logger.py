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
        self.api_key = os.getenv("AIRTABLE_API_KEY", "")
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
            "campaign_access": os.getenv("FLORRA_CAMPAIGN_ACCESS_TABLE", "Campaign Access"),
            "metadata": "tbleJMnUc8u59V72L"
        }

    # ------------------------------------------------------------------
    # Campaigns — visibility + bounty access
    # ------------------------------------------------------------------

    CAMPAIGN_VISIBILITIES = ["Public", "Private"]
    CAMPAIGN_ACCESS_MODES = ["Invite", "Apply"]

    def create_campaign(self, name: str, brief: str = "", bounty_amount: float = 0,
                        visibility: str = "Public", access_mode: str = "",
                        dm_script: str = "", notes: str = ""):
        """Create a campaign.

        Public campaigns are open to all creators. Private campaigns must set
        access_mode to control how creators receive the bounty:
          - "Invite": only creators you invite are eligible
          - "Apply":  creators apply and must be approved before they're eligible
        """
        if visibility not in self.CAMPAIGN_VISIBILITIES:
            print(f"❌ Invalid visibility '{visibility}' — use one of {self.CAMPAIGN_VISIBILITIES}")
            return None
        if visibility == "Private":
            if access_mode not in self.CAMPAIGN_ACCESS_MODES:
                print(f"❌ Private campaigns need access_mode set to one of {self.CAMPAIGN_ACCESS_MODES}")
                return None
        else:
            access_mode = ""

        record = {
            "fields": {
                "Name": name,
                "Brief": brief,
                "Bounty Amount": bounty_amount,
                "Visibility": visibility,
                "Access Mode": access_mode,
                "DM Script": dm_script,
                "Created Date": datetime.now().isoformat(),
                "Notes": notes
            }
        }

        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['campaigns']}",
            headers=self.headers,
            json=record
        )

        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to create campaign: {response.text}")
            return None

    def get_campaign(self, name: str) -> Optional[Dict]:
        """Get a campaign by name"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['campaigns']}?filterByFormula={{Name}}='{name}'",
            headers=self.headers
        )

        if response.status_code == 200:
            records = response.json().get("records", [])
            return records[0] if records else None
        return None

    def invite_creator(self, campaign: str, creator: str, notes: str = ""):
        """Invite a creator to a private invite-only campaign"""
        camp = self.get_campaign(campaign)
        if camp and camp["fields"].get("Visibility") == "Private" and \
                camp["fields"].get("Access Mode") != "Invite":
            print(f"❌ '{campaign}' is not invite-based — creators must apply instead")
            return None

        record = {
            "fields": {
                "Campaign": campaign,
                "Creator": creator,
                "Status": "Invited",
                "Requested Date": datetime.now().isoformat(),
                "Notes": notes
            }
        }

        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['campaign_access']}",
            headers=self.headers,
            json=record
        )

        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to invite creator: {response.text}")
            return None

    def apply_to_campaign(self, campaign: str, creator: str, message: str = ""):
        """Submit a creator's application to a private apply-based campaign"""
        camp = self.get_campaign(campaign)
        if camp and camp["fields"].get("Visibility") == "Private" and \
                camp["fields"].get("Access Mode") != "Apply":
            print(f"❌ '{campaign}' is invite-only — applications are not accepted")
            return None

        record = {
            "fields": {
                "Campaign": campaign,
                "Creator": creator,
                "Status": "Applied",
                "Requested Date": datetime.now().isoformat(),
                "Message": message
            }
        }

        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['campaign_access']}",
            headers=self.headers,
            json=record
        )

        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to submit application: {response.text}")
            return None

    def review_application(self, record_id: str, approve: bool, notes: str = ""):
        """Approve or reject a creator's application to a campaign"""
        fields = {
            "Status": "Approved" if approve else "Rejected",
            "Decision Date": datetime.now().isoformat()
        }
        if notes:
            fields["Notes"] = notes

        response = requests.patch(
            f"{self.api_base}/{self.base_id}/{self.tables['campaign_access']}/{record_id}",
            headers=self.headers,
            json={"fields": fields}
        )

        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to review application: {response.text}")
            return None

    def get_campaign_access(self, campaign: str, creator: str) -> Optional[Dict]:
        """Get a creator's access record for a campaign"""
        formula = f"AND({{Campaign}}='{campaign}',{{Creator}}='{creator}')"
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['campaign_access']}",
            headers=self.headers,
            params={"filterByFormula": formula}
        )

        if response.status_code == 200:
            records = response.json().get("records", [])
            return records[0] if records else None
        return None

    def get_campaign_applications(self, campaign: str, status: str = "Applied") -> List[Dict]:
        """List access records for a campaign, filtered by status (default: pending applications)"""
        formula = f"AND({{Campaign}}='{campaign}',{{Status}}='{status}')"
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['campaign_access']}",
            headers=self.headers,
            params={"filterByFormula": formula}
        )

        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def is_eligible_for_bounty(self, creator: str, campaign: str) -> bool:
        """Check whether a creator can receive a campaign's bounty.

        Public campaigns: everyone is eligible.
        Private + Invite: creator must have an Invited/Accepted access record.
        Private + Apply:  creator's application must be Approved.
        """
        camp = self.get_campaign(campaign)
        if not camp or camp["fields"].get("Visibility") != "Private":
            return True

        access = self.get_campaign_access(campaign, creator)
        if not access:
            return False

        status = access["fields"].get("Status", "")
        if camp["fields"].get("Access Mode") == "Invite":
            return status in ["Invited", "Accepted"]
        return status == "Approved"

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
        """Update UGC Pipeline status.

        Moving to "Paid" is blocked for private campaigns unless the creator
        has access (invited, or application approved).
        """
        if status == "Paid":
            entry = requests.get(
                f"{self.api_base}/{self.base_id}/{self.tables['ugc_pipeline']}/{record_id}",
                headers=self.headers
            )
            if entry.status_code == 200:
                fields = entry.json().get("fields", {})
                creator = fields.get("Creator", "")
                campaign = fields.get("Campaign", "")
                if campaign and not self.is_eligible_for_bounty(creator, campaign):
                    print(f"❌ '{creator}' is not eligible for the '{campaign}' bounty — "
                          f"private campaign requires an invite or approved application")
                    return None

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
    print("  - create_campaign(name, brief, bounty_amount, visibility, access_mode)")
    print("  - invite_creator(campaign, creator)")
    print("  - apply_to_campaign(campaign, creator, message)")
    print("  - review_application(record_id, approve)")
    print("  - get_campaign_applications(campaign)")
    print("  - is_eligible_for_bounty(creator, campaign)")
