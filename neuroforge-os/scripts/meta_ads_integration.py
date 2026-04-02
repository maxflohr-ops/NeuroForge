#!/usr/bin/env python3
"""
Meta Ads API Integration
Custom audiences, lookalike audiences, campaign creation
"""

import os
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime


class MetaAdsIntegration:
    def __init__(self):
        self.access_token = os.getenv("META_ADS_ACCESS_TOKEN", "")
        self.ad_account_id = os.getenv("META_AD_ACCOUNT_ID", "")
        self.api_version = "v18.0"
        
        self.base_url = f"https://graph.instagram.com/{self.api_version}"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def log(self, message: str, prefix: str = "ℹ️"):
        print(f"{prefix} {message}")

    def create_custom_audience(self, audience_name: str, creators: List[Dict]) -> Optional[str]:
        """Create custom audience from creator list"""
        self.log(f"Creating custom audience '{audience_name}' with {len(creators)} creators...", "🎯")
        
        # Extract handles and prepare hashed data for Meta
        handles = [c.get("tiktok_handle") or c.get("instagram_handle") for c in creators]
        
        payload = {
            "name": audience_name,
            "subtype": "EXTERNAL_ID",
            "data": {
                "users": handles
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/act_{self.ad_account_id}/audiences",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                audience_id = response.json().get("id")
                self.log(f"Custom audience created: {audience_id}", "✓")
                return audience_id
            else:
                self.log(f"Failed to create audience: {response.text}", "❌")
                return None
        except Exception as e:
            self.log(f"Error creating audience: {str(e)}", "❌")
            return None

    def create_lookalike_audience(self, source_audience_id: str, country: str = "US",
                                 audience_name: Optional[str] = None) -> Optional[str]:
        """Create lookalike audience from source audience"""
        self.log(f"Creating lookalike audience for {country}...", "🎯")
        
        if not audience_name:
            audience_name = f"Lookalike_{country}_{datetime.now().strftime('%Y%m%d')}"
        
        payload = {
            "name": audience_name,
            "subtype": "LOOKALIKE",
            "source_audience_id": source_audience_id,
            "country": country,
            "ratio": 0.01  # 1% lookalike
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/act_{self.ad_account_id}/audiences",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                audience_id = response.json().get("id")
                self.log(f"Lookalike audience created: {audience_id}", "✓")
                return audience_id
            else:
                self.log(f"Failed to create lookalike: {response.text}", "❌")
                return None
        except Exception as e:
            self.log(f"Error creating lookalike: {str(e)}", "❌")
            return None

    def create_campaign(self, campaign_name: str, objective: str = "CONVERSIONS",
                       budget: float = 1000) -> Optional[str]:
        """Create Meta ads campaign"""
        self.log(f"Creating campaign '{campaign_name}' with ${budget} budget...", "📢")
        
        payload = {
            "name": campaign_name,
            "objective": objective,
            "status": "PAUSED",
            "special_ad_categories": []
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/act_{self.ad_account_id}/campaigns",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                campaign_id = response.json().get("id")
                self.log(f"Campaign created: {campaign_id}", "✓")
                return campaign_id
            else:
                self.log(f"Failed to create campaign: {response.text}", "❌")
                return None
        except Exception as e:
            self.log(f"Error creating campaign: {str(e)}", "❌")
            return None

    def create_adset(self, campaign_id: str, audience_id: str, adset_name: str,
                    daily_budget: float = 50, targeting: Dict = None) -> Optional[str]:
        """Create ad set with audience targeting"""
        self.log(f"Creating ad set '{adset_name}'...", "🎯")
        
        if not targeting:
            targeting = {
                "age_min": 13,
                "age_max": 65,
                "geo_locations": {
                    "regions": [{"key": "US"}]
                }
            }
        
        payload = {
            "name": adset_name,
            "campaign_id": campaign_id,
            "daily_budget": int(daily_budget * 100),  # Convert to cents
            "targeting": {
                **targeting,
                "custom_audiences": [{"id": audience_id}]
            },
            "status": "PAUSED",
            "optimization_goal": "CONVERSIONS"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/act_{self.ad_account_id}/adsets",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                adset_id = response.json().get("id")
                self.log(f"Ad set created: {adset_id}", "✓")
                return adset_id
            else:
                self.log(f"Failed to create ad set: {response.text}", "❌")
                return None
        except Exception as e:
            self.log(f"Error creating ad set: {str(e)}", "❌")
            return None

    def create_ad(self, adset_id: str, creative_id: str, ad_name: str) -> Optional[str]:
        """Create individual ad"""
        self.log(f"Creating ad '{ad_name}'...", "📍")
        
        payload = {
            "name": ad_name,
            "adset_id": adset_id,
            "creative": {"creative_id": creative_id},
            "status": "PAUSED"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/act_{self.ad_account_id}/ads",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                ad_id = response.json().get("id")
                self.log(f"Ad created: {ad_id}", "✓")
                return ad_id
            else:
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
                f"{self.base_url}/{campaign_id}/insights",
                headers=self.headers,
                params={
                    "fields": "impressions,clicks,spend,actions"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    self.log(f"Retrieved insights for {campaign_id}", "✓")
                    return data[0]
            else:
                self.log(f"Failed to get insights: {response.text}", "❌")
        except Exception as e:
            self.log(f"Error fetching insights: {str(e)}", "❌")
        
        return None


# Example usage
if __name__ == "__main__":
    meta = MetaAdsIntegration()
    
    print("✓ Meta Ads Integration initialized")
    print("\nAvailable methods:")
    print("  - create_custom_audience(audience_name, creators)")
    print("  - create_lookalike_audience(source_audience_id, country)")
    print("  - create_campaign(campaign_name, objective, budget)")
    print("  - create_adset(campaign_id, audience_id, adset_name, daily_budget)")
    print("  - create_ad(adset_id, creative_id, ad_name)")
    print("  - get_campaign_insights(campaign_id)")
