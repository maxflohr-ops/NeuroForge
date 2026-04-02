#!/usr/bin/env python3
"""
OpenClaw → Airtable Logger
Logs agent interactions, performance, and generates improvement suggestions
"""

import os
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional

class OpenClawAirtableLogger:
    def __init__(self):
        self.api_key = os.getenv("AIRTABLE_API_KEY", "AIRTABLE_API_KEY
        self.base_id = os.getenv("AIRTABLE_BASE_ID", "applXEAjh6k3Xmybl")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.api_base = "https://api.airtable.com/v0"
        
        # Table IDs
        self.tables = {
            "interactions": "tblxjo12st1GoOuUM",
            "performance": "tbl2F024MIEMh26ng",
            "suggestions": "tblKhnROIh8ssTqiE",
            "telegram": "tblQ3Df9ck45HTnfC",
            "leads": "tblfCsmmbtUpOPhtX",
            "optimization": "tbluLfkFPyv3ugssf"
        }

    def log_interaction(self, user_query: str, response: str, search_used: Optional[str] = None, 
                       response_time_ms: int = 0, satisfaction: Optional[str] = None, tags: Optional[str] = None):
        """Log an agent interaction"""
        record = {
            "fields": {
                "User Query": user_query[:1000],
                "Agent Response": response[:10000],
                "Search Used": search_used or "",
                "Model": "OpenClaw",
                "User Satisfaction": satisfaction or "pending",
                "Timestamp": datetime.now().isoformat(),
                "Tags": tags or ""
            }
        }
        
        response_obj = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['interactions']}",
            headers=self.headers,
            json=record
        )
        
        if response_obj.status_code in [200, 201]:
            return response_obj.json()
        else:
            print(f"❌ Failed to log interaction: {response_obj.text}")
            return None

    def log_telegram_message(self, user_id: str, message: str, bot_response: str, success: bool = True, error_log: Optional[str] = None):
        """Log Telegram bot message"""
        record = {
            "fields": {
                "User ID": user_id,
                "Message": message[:5000],
                "Bot Response": bot_response[:5000],
                "Success": "Yes" if success else "No",
                "Error Log": error_log or "",
                "Timestamp": datetime.now().isoformat()
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['telegram']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Failed to log Telegram message: {response.text}")

    def log_lead(self, name: str, telegram_id: str, interest_level: str = "Medium", status: str = "New"):
        """Log or update a lead"""
        record = {
            "fields": {
                "Contact Name": name,
                "Telegram ID": telegram_id,
                "Interaction Count": 1,
                "Last Interaction": datetime.now().isoformat(),
                "Interest Level": interest_level,
                "Status": status,
                "Notes": f"Added {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['leads']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Failed to log lead: {response.text}")

    def log_performance_metric(self, metric_name: str, value: float, category: str = "General", notes: Optional[str] = None):
        """Log performance metrics"""
        record = {
            "fields": {
                "Metric": metric_name,
                "Date": datetime.now().isoformat(),
                "Category": category,
                "Notes": notes or ""
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['performance']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Failed to log performance metric: {response.text}")

    def suggest_improvement(self, issue: str, suggested_fix: str, priority: str = "Medium"):
        """Log improvement suggestion"""
        record = {
            "fields": {
                "Issue": issue,
                "Suggested Fix": suggested_fix,
                "Priority": priority,
                "Status": "Pending",
                "Date Suggested": datetime.now().isoformat()
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['suggestions']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            print(f"❌ Failed to log improvement suggestion: {response.text}")
            return None

    def log_optimization(self, prompt_version: str, description: str, status: str = "Testing"):
        """Log model optimization"""
        record = {
            "fields": {
                "Prompt Version": prompt_version,
                "Change Description": description,
                "Date Changed": datetime.now().isoformat(),
                "Status": status
            }
        }
        
        response = requests.post(
            f"{self.api_base}/{self.base_id}/{self.tables['optimization']}",
            headers=self.headers,
            json=record
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Failed to log optimization: {response.text}")

    def get_low_performance_queries(self) -> List[Dict]:
        """Get all interactions with low satisfaction"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['interactions']}?filterByFormula={{User Satisfaction}}='Low'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []

    def get_pending_improvements(self) -> List[Dict]:
        """Get improvement suggestions pending implementation"""
        response = requests.get(
            f"{self.api_base}/{self.base_id}/{self.tables['suggestions']}?filterByFormula={{Status}}='Pending'",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("records", [])
        return []


# Example usage
if __name__ == "__main__":
    logger = OpenClawAirtableLogger()
    
    print("✓ OpenClaw Airtable Logger initialized")
    print("\nAvailable methods:")
    print("  - log_interaction(query, response, ...)")
    print("  - log_telegram_message(user_id, message, ...)")
    print("  - log_lead(name, telegram_id, ...)")
    print("  - log_performance_metric(name, value, ...)")
    print("  - suggest_improvement(issue, fix, ...)")
    print("  - log_optimization(version, description, ...)")
    print("  - get_low_performance_queries()")
    print("  - get_pending_improvements()")
    
    # Test log
    logger.log_interaction(
        user_query="What's the best strategy for music marketing?",
        response="Here are the top strategies: social media, collaborations, streaming optimization...",
        search_used="Brave Search",
        satisfaction="High",
        tags="music,marketing,ebril"
    )
    print("\n✓ Test interaction logged to Airtable")
