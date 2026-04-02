#!/usr/bin/env python3
"""
TikTok Ads API Integration
Sound retargeting, hashtag targeting, campaign creation
"""

import os
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime


class TikTokAdsIntegration:
    def __init__(self):
        self.access_token = os.getenv("TIKTOK_ADS_ACCESS_TOKEN", "")
        self.advertiser_id = os.getenv("TIKTOK_ADVERTISER_ID", "")
        self.api_version = "v1.4"
        
        self.base_url = f"https://business-api.tiktok.com/open_api/{self.api_version}"
        self.headers = {
            "Access-Token": self.access_token,
            "Content-Type": "application/json"
        }

    def log(self, message: str, prefix: str = "ℹ️"):
        print(f"{prefix} {message}")

    def create_sound_retargeting_audience(self, sound_id: str, audience_name: str) -> Optional[str]:
        """Create audience targeting users who engaged with specific sound"""
        self.log(f"Creating sound retargeting audience for sound {sound_id}...", "🎵")
        
        payload = {
            "advertiser_id": self.advertiser_id,
            "audience_name": audience_name,
            "audience_type": "SOUND",
            "sound_id": sound_id
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/audience/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                audience_id = data.get("audience_id")
                if audience_id:
                    self.log(f"Sound retargeting audience created: {audience_id}", "✓")
                    return audience_id
            
            self.log(f"Failed to create audience: {response.text}", "❌")
            return None
        except Exception as e:
            self.log(f"Error creating audience: {str(e)}", "❌")
            return None

    def create_hashtag_audience(self, hashtags: List[str], audience_name: str) -> Optional[str]:
        """Create audience targeting specific hashtags"""
        self.log(f"Creating hashtag audience for {len(hashtags)} hashtags...", "🏷️")
        
        # Map hashtags to TikTok category IDs
        # This is simplified - in practice you'd need TikTok's interest mapping
        hashtag_ids = [f"ht_{h.replace('#', '').lower()}" for h in hashtags]
        
        payload = {
            "advertiser_id": self.advertiser_id,
            "audience_name": audience_name,
            "audience_type": "HASHTAG",
            "interest_ids": hashtag_ids
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/audience/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                audience_id = data.get("audience_id")
                if audience_id:
                    self.log(f"Hashtag audience created: {audience_id}", "✓")
                    return audience_id
            
            self.log(f"Failed to create audience: {response.text}", "❌")
            return None
        except Exception as e:
            self.log(f"Error creating audience: {str(e)}", "❌")
            return None

    def create_campaign(self, campaign_name: str, budget: float = 1000,
                       objective: str = "TRAFFIC") -> Optional[str]:
        """Create TikTok ads campaign"""
        self.log(f"Creating campaign '{campaign_name}' with ${budget} budget...", "📢")
        
        payload = {
            "advertiser_id": self.advertiser_id,
            "campaign_name": campaign_name,
            "objective_type": objective,
            "budget": int(budget),
            "budget_mode": "DAILY",
            "status": "DISABLE"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/campaign/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                campaign_id = data.get("campaign_id")
                if campaign_id:
                    self.log(f"Campaign created: {campaign_id}", "✓")
                    return campaign_id
            
            self.log(f"Failed to create campaign: {response.text}", "❌")
            return None
        except Exception as e:
            self.log(f"Error creating campaign: {str(e)}", "❌")
            return None

    def create_adgroup(self, campaign_id: str, adgroup_name: str, audience_id: str,
                      daily_budget: float = 50, targeting: Dict = None) -> Optional[str]:
        """Create ad group with audience targeting"""
        self.log(f"Creating ad group '{adgroup_name}'...", "🎯")
        
        if not targeting:
            targeting = {
                "age": ["18-24", "25-34", "35-44", "45-54", "55-64"],
                "gender": "UNLIMITED"
            }
        
        payload = {
            "advertiser_id": self.advertiser_id,
            "campaign_id": campaign_id,
            "adgroup_name": adgroup_name,
            "daily_budget": int(daily_budget * 100),
            "audience_id": audience_id,
            "targeting": targeting,
            "status": "DISABLE"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/adgroup/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                adgroup_id = data.get("adgroup_id")
                if adgroup_id:
                    self.log(f"Ad group created: {adgroup_id}", "✓")
                    return adgroup_id
            
            self.log(f"Failed to create ad group: {response.text}", "❌")
            return None
        except Exception as e:
            self.log(f"Error creating ad group: {str(e)}", "❌")
            return None

    def create_ad(self, adgroup_id: str, creative_id: str, ad_name: str) -> Optional[str]:
        """Create individual ad"""
        self.log(f"Creating ad '{ad_name}'...", "📍")
        
        payload = {
            "advertiser_id": self.advertiser_id,
            "adgroup_id": adgroup_id,
            "creative_id": creative_id,
            "ad_name": ad_name,
            "status": "DISABLE"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/ad/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                ad_id = data.get("ad_id")
                if ad_id:
                    self.log(f"Ad created: {ad_id}", "✓")
                    return ad_id
            
            self.log(f"Failed to create ad: {response.text}", "❌")
            return None
        except Exception as e:
            self.log(f"Error creating ad: {str(e)}", "❌")
            return None

    def get_campaign_insights(self, campaign_id: str) -> Optional[Dict]:
        """Get campaign performance metrics"""
        self.log(f"Fetching insights for campaign {campaign_id}...", "📊")
        
        try:
            response = requests.get(
                f"{self.base_url}/campaign/get",
                headers=self.headers,
                params={
                    "advertiser_id": self.advertiser_id,
                    "campaign_id": campaign_id,
                    "fields": "campaign_id,campaign_name,status,budget,impressions,clicks,spend"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json().get("data", {})
                if data:
                    self.log(f"Retrieved insights for {campaign_id}", "✓")
                    return data
            else:
                self.log(f"Failed to get insights: {response.text}", "❌")
        except Exception as e:
            self.log(f"Error fetching insights: {str(e)}", "❌")
        
        return None


# Example usage
if __name__ == "__main__":
    tiktok = TikTokAdsIntegration()
    
    print("✓ TikTok Ads Integration initialized")
    print("\nAvailable methods:")
    print("  - create_sound_retargeting_audience(sound_id, audience_name)")
    print("  - create_hashtag_audience(hashtags, audience_name)")
    print("  - create_campaign(campaign_name, budget, objective)")
    print("  - create_adgroup(campaign_id, adgroup_name, audience_id, daily_budget)")
    print("  - create_ad(adgroup_id, creative_id, ad_name)")
    print("  - get_campaign_insights(campaign_id)")
