#!/usr/bin/env python3
"""
Flowstage Webhook Integration
Auto-posts Opus clips and Florra content to social platforms
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, Optional


class FlowstageIntegration:
    def __init__(self):
        self.flowstage_url = os.getenv("FLOWSTAGE_WEBHOOK_URL", "https://api.flowstage.io/webhooks")
        self.flowstage_token = os.getenv("FLOWSTAGE_API_TOKEN", "")
        
        self.headers = {
            "Authorization": f"Bearer {self.flowstage_token}",
            "Content-Type": "application/json"
        }

    def log(self, message: str, prefix: str = "ℹ️"):
        print(f"{prefix} {message}")

    def schedule_tiktok_post(self, caption: str, video_url: str, scheduled_date: str, 
                             hashtags: str = "", campaign: str = "") -> bool:
        """Schedule a TikTok post via Flowstage"""
        self.log(f"Scheduling TikTok post for {scheduled_date}...", "📱")
        
        payload = {
            "platform": "tiktok",
            "content": {
                "caption": caption,
                "video_url": video_url,
                "hashtags": hashtags.split(",") if hashtags else []
            },
            "scheduling": {
                "scheduled_date": scheduled_date,
                "auto_publish": True
            },
            "metadata": {
                "campaign": campaign,
                "source": "Master Orchestrator"
            }
        }
        
        try:
            response = requests.post(
                f"{self.flowstage_url}/tiktok/schedule",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.log(f"TikTok post scheduled: {response.json().get('id', 'unknown')}", "✓")
                return True
            else:
                self.log(f"Failed to schedule TikTok: {response.text}", "❌")
                return False
        except Exception as e:
            self.log(f"Error scheduling TikTok: {str(e)}", "❌")
            return False

    def schedule_instagram_post(self, caption: str, image_url: str, scheduled_date: str,
                               hashtags: str = "", campaign: str = "") -> bool:
        """Schedule an Instagram post via Flowstage"""
        self.log(f"Scheduling Instagram post for {scheduled_date}...", "📸")
        
        payload = {
            "platform": "instagram",
            "content": {
                "caption": caption,
                "image_url": image_url,
                "hashtags": hashtags.split(",") if hashtags else []
            },
            "scheduling": {
                "scheduled_date": scheduled_date,
                "auto_publish": True
            },
            "metadata": {
                "campaign": campaign,
                "source": "Master Orchestrator"
            }
        }
        
        try:
            response = requests.post(
                f"{self.flowstage_url}/instagram/schedule",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.log(f"Instagram post scheduled: {response.json().get('id', 'unknown')}", "✓")
                return True
            else:
                self.log(f"Failed to schedule Instagram: {response.text}", "❌")
                return False
        except Exception as e:
            self.log(f"Error scheduling Instagram: {str(e)}", "❌")
            return False

    def schedule_youtube_post(self, title: str, description: str, video_url: str, 
                             scheduled_date: str, tags: str = "", campaign: str = "") -> bool:
        """Schedule a YouTube post via Flowstage"""
        self.log(f"Scheduling YouTube post for {scheduled_date}...", "📹")
        
        payload = {
            "platform": "youtube",
            "content": {
                "title": title,
                "description": description,
                "video_url": video_url,
                "tags": tags.split(",") if tags else [],
                "visibility": "public"
            },
            "scheduling": {
                "scheduled_date": scheduled_date,
                "auto_publish": True
            },
            "metadata": {
                "campaign": campaign,
                "source": "Master Orchestrator"
            }
        }
        
        try:
            response = requests.post(
                f"{self.flowstage_url}/youtube/schedule",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.log(f"YouTube post scheduled: {response.json().get('id', 'unknown')}", "✓")
                return True
            else:
                self.log(f"Failed to schedule YouTube: {response.text}", "❌")
                return False
        except Exception as e:
            self.log(f"Error scheduling YouTube: {str(e)}", "❌")
            return False

    def batch_schedule_opus_clips(self, clips: list, platforms: list = ["tiktok", "instagram"]) -> Dict:
        """Batch schedule Opus clips to multiple platforms"""
        self.log(f"Batch scheduling {len(clips)} clips to {len(platforms)} platforms...", "📡")
        
        results = {
            "scheduled": 0,
            "failed": 0,
            "clips": []
        }
        
        for clip in clips:
            fields = clip.get("fields", {})
            
            for platform in platforms:
                success = False
                
                if platform.lower() == "tiktok":
                    success = self.schedule_tiktok_post(
                        caption=f"{fields.get('Clip Title', '')} 🎬",
                        video_url=fields.get("Video URL", ""),
                        scheduled_date=datetime.now().isoformat(),
                        campaign=fields.get("Campaign", "")
                    )
                elif platform.lower() == "instagram":
                    success = self.schedule_instagram_post(
                        caption=f"{fields.get('Clip Title', '')} 🎬",
                        image_url=fields.get("Thumbnail URL", ""),
                        scheduled_date=datetime.now().isoformat(),
                        campaign=fields.get("Campaign", "")
                    )
                
                if success:
                    results["scheduled"] += 1
                else:
                    results["failed"] += 1
            
            results["clips"].append(fields.get("Clip Title", "Unknown"))
        
        self.log(f"Results: {results['scheduled']} scheduled, {results['failed']} failed", "📊")
        return results

    def schedule_spark_ad(self, creator_handle: str, spark_code: str, video_url: str,
                         scheduled_date: str) -> bool:
        """Schedule TikTok Spark Ad"""
        self.log(f"Scheduling Spark Ad for @{creator_handle}...", "⚡")
        
        payload = {
            "platform": "tiktok",
            "ad_type": "spark",
            "creator": {
                "handle": creator_handle,
                "spark_code": spark_code
            },
            "content": {
                "video_url": video_url
            },
            "scheduling": {
                "scheduled_date": scheduled_date
            }
        }
        
        try:
            response = requests.post(
                f"{self.flowstage_url}/tiktok/spark-ad",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.log(f"Spark Ad scheduled for @{creator_handle}", "✓")
                return True
            else:
                self.log(f"Failed to schedule Spark Ad: {response.text}", "❌")
                return False
        except Exception as e:
            self.log(f"Error scheduling Spark Ad: {str(e)}", "❌")
            return False


# Example usage
if __name__ == "__main__":
    flowstage = FlowstageIntegration()
    
    print("✓ Flowstage Integration initialized")
    print("\nAvailable methods:")
    print("  - schedule_tiktok_post(caption, video_url, scheduled_date, ...)")
    print("  - schedule_instagram_post(caption, image_url, scheduled_date, ...)")
    print("  - schedule_youtube_post(title, description, video_url, ...)")
    print("  - batch_schedule_opus_clips(clips, platforms)")
    print("  - schedule_spark_ad(creator_handle, spark_code, video_url, ...)")
