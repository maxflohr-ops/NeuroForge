# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tools for the Florra UGC agent.

Deterministic work (creator scoring, tier math, Airtable reads/writes) lives
here as plain functions so the LLM spends its judgment on outreach copy and
campaign strategy, not arithmetic. The Airtable schema mirrors
``neuroforge-os/scripts/florra_airtable_logger.py`` and FLORRA_AIRTABLE.md.
"""

import os
from datetime import datetime

import requests

_API_BASE = "https://api.airtable.com/v0"

# Table IDs from the Florra Airtable base (see FLORRA_AIRTABLE.md).
_TABLES = {
    "people": "tblYqPt2BYVjMaXFk",
    "ugc_pipeline": "tblqTn9O3rIMMecbT",
    "content_library": "tblmKJcNNOeEUaI79",
    "spark_codes": "tblqRpE6Ou9vXImey",
    "campaigns": "tblMUfJKvYiOEARy3",
    "metadata": "tbleJMnUc8u59V72L",
}

PIPELINE_STAGES = ["Identified", "Outreach", "Contract", "Content", "Paid"]


def _airtable_config() -> tuple[str, str, dict] | None:
    api_key = os.getenv("AIRTABLE_API_KEY", "")
    base_id = os.getenv("AIRTABLE_BASE_ID", "applXEAjh6k3Xmybl")
    if not api_key:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return api_key, base_id, headers


_NO_KEY_ERROR = {
    "status": "error",
    "message": (
        "AIRTABLE_API_KEY is not set. Ask the user to export it (the Florra "
        "base is applXEAjh6k3Xmybl) before using Airtable tools."
    ),
}


def score_creator(
    followers: int,
    engagement_rate: float,
    posts_with_sound: int,
    avg_views: int,
) -> dict:
    """Score a creator for UGC campaign fit and assign a follower tier.

    Deterministic scoring so every creator is ranked on the same scale.
    Weights: engagement rate 40%, sound trend activity 25%, reach 20%,
    view efficiency 15%. Tune the weights here, not in prompts.

    Args:
        followers: TikTok follower count.
        engagement_rate: Average engagement rate as a percentage (e.g. 8.5).
        posts_with_sound: Number of posts the creator made using the target
            sound (from Chartex sound lookup).
        avg_views: Average views per post.

    Returns:
        A dict with overall_score (0-100), follower_tier (Nano/Micro/Mid/
        Macro/Mega), and the component scores.
    """
    if followers < 10_000:
        tier = "Nano"
    elif followers < 100_000:
        tier = "Micro"
    elif followers < 500_000:
        tier = "Mid"
    elif followers < 1_000_000:
        tier = "Macro"
    else:
        tier = "Mega"

    # Engagement: 8%+ is elite for TikTok; scale toward that.
    engagement_score = min(engagement_rate / 8.0, 1.0) * 40
    # Sound activity: repeated use of the sound signals genuine trend fit.
    trend_score = min(posts_with_sound / 5.0, 1.0) * 25
    # Reach: log-ish bands rather than raw followers so Micro can compete.
    reach_score = min(followers / 500_000, 1.0) * 20
    # View efficiency: views relative to follower count (viral reach).
    efficiency = (avg_views / followers) if followers else 0.0
    efficiency_score = min(efficiency / 2.0, 1.0) * 15

    overall = round(engagement_score + trend_score + reach_score + efficiency_score, 1)
    return {
        "overall_score": overall,
        "follower_tier": tier,
        "components": {
            "engagement": round(engagement_score, 1),
            "sound_trend": round(trend_score, 1),
            "reach": round(reach_score, 1),
            "view_efficiency": round(efficiency_score, 1),
        },
        "recommendation": (
            "strong outreach candidate"
            if overall >= 70
            else "worth a look"
            if overall >= 45
            else "skip unless strategic"
        ),
    }


def add_creator(
    name: str,
    tiktok_handle: str,
    tiktok_followers: int,
    country: str,
    engagement_rate: float,
    follower_tier: str,
    overall_score: float,
    profile_url: str,
    notes: str,
) -> dict:
    """Add a discovered creator to the Florra People table in Airtable.

    Call score_creator first and pass its follower_tier and overall_score
    here so the database stays on one scoring scale.

    Args:
        name: Creator's display name.
        tiktok_handle: Handle including @.
        tiktok_followers: Follower count.
        country: Two-letter or full country name.
        engagement_rate: Engagement rate percentage.
        follower_tier: Tier from score_creator (Nano/Micro/Mid/Macro/Mega).
        overall_score: Score from score_creator (0-100).
        profile_url: Link to the creator's profile.
        notes: Anything the team should know (content style, best post, etc.).

    Returns:
        The created Airtable record, or an error dict if the API key is
        missing or the request fails.
    """
    config = _airtable_config()
    if config is None:
        return _NO_KEY_ERROR
    _, base_id, headers = config
    record = {
        "fields": {
            "Name": name,
            "TikTok Handle": tiktok_handle,
            "TikTok Followers": tiktok_followers,
            "Country": country,
            "Engagement Rate": engagement_rate,
            "Follower Tier": follower_tier,
            "Overall Score": overall_score,
            "Profile URL": profile_url,
            "Added Date": datetime.now().isoformat(),
            "Notes": notes,
        }
    }
    response = requests.post(
        f"{_API_BASE}/{base_id}/{_TABLES['people']}",
        headers=headers,
        json=record,
        timeout=30,
    )
    if response.status_code in (200, 201):
        return {"status": "ok", "record": response.json()}
    return {"status": "error", "message": response.text[:500]}


def add_to_ugc_pipeline(
    creator: str, campaign: str, sound: str, sound_id: str, status: str
) -> dict:
    """Add a creator to the Florra UGC Pipeline table.

    Args:
        creator: Creator name as stored in the People table.
        campaign: Campaign name.
        sound: Sound name.
        sound_id: TikTok/Chartex sound ID.
        status: Pipeline stage — one of Identified, Outreach, Contract,
            Content, Paid.

    Returns:
        The created record, or an error dict.
    """
    if status not in PIPELINE_STAGES:
        return {
            "status": "error",
            "message": f"status must be one of {PIPELINE_STAGES}",
        }
    config = _airtable_config()
    if config is None:
        return _NO_KEY_ERROR
    _, base_id, headers = config
    record = {
        "fields": {
            "Creator": creator,
            "Campaign": campaign,
            "Sound": sound,
            "Sound ID": sound_id,
            "Status": status,
            "Identified Date": datetime.now().isoformat(),
        }
    }
    response = requests.post(
        f"{_API_BASE}/{base_id}/{_TABLES['ugc_pipeline']}",
        headers=headers,
        json=record,
        timeout=30,
    )
    if response.status_code in (200, 201):
        return {"status": "ok", "record": response.json()}
    return {"status": "error", "message": response.text[:500]}


def update_pipeline_status(record_id: str, status: str) -> dict:
    """Move a UGC Pipeline record to a new stage.

    Args:
        record_id: The Airtable record ID (rec...).
        status: New stage — one of Identified, Outreach, Contract, Content,
            Paid.

    Returns:
        The updated record, or an error dict.
    """
    if status not in PIPELINE_STAGES:
        return {
            "status": "error",
            "message": f"status must be one of {PIPELINE_STAGES}",
        }
    config = _airtable_config()
    if config is None:
        return _NO_KEY_ERROR
    _, base_id, headers = config
    response = requests.patch(
        f"{_API_BASE}/{base_id}/{_TABLES['ugc_pipeline']}/{record_id}",
        headers=headers,
        json={
            "fields": {"Status": status, f"{status} Date": datetime.now().isoformat()}
        },
        timeout=30,
    )
    if response.status_code == 200:
        return {"status": "ok", "record": response.json()}
    return {"status": "error", "message": response.text[:500]}


def get_pipeline_by_status(status: str) -> dict:
    """List UGC Pipeline records at a given stage.

    Args:
        status: Stage to filter by — one of Identified, Outreach, Contract,
            Content, Paid.

    Returns:
        A dict with the matching records, or an error dict.
    """
    config = _airtable_config()
    if config is None:
        return _NO_KEY_ERROR
    _, base_id, headers = config
    response = requests.get(
        f"{_API_BASE}/{base_id}/{_TABLES['ugc_pipeline']}",
        headers=headers,
        params={"filterByFormula": f"{{Status}} = '{status}'"},
        timeout=30,
    )
    if response.status_code == 200:
        return {"status": "ok", "records": response.json().get("records", [])}
    return {"status": "error", "message": response.text[:500]}


def add_spark_code(
    creator: str,
    tiktok_handle: str,
    spark_code: str,
    video_url: str,
    campaign: str,
    code_expiry: str,
) -> dict:
    """Track a TikTok Spark Ad authorization code in the Spark Codes table.

    Args:
        creator: Creator name.
        tiktok_handle: Handle including @.
        spark_code: The Spark Ad authorization code.
        video_url: URL of the authorized video.
        campaign: Campaign the code belongs to.
        code_expiry: Expiry date (YYYY-MM-DD).

    Returns:
        The created record, or an error dict.
    """
    config = _airtable_config()
    if config is None:
        return _NO_KEY_ERROR
    _, base_id, headers = config
    record = {
        "fields": {
            "Creator": creator,
            "TikTok Handle": tiktok_handle,
            "Code": spark_code,
            "Video URL": video_url,
            "Campaign": campaign,
            "Expiry": code_expiry,
            "Status": "Active",
            "Activated Date": datetime.now().isoformat(),
        }
    }
    response = requests.post(
        f"{_API_BASE}/{base_id}/{_TABLES['spark_codes']}",
        headers=headers,
        json=record,
        timeout=30,
    )
    if response.status_code in (200, 201):
        return {"status": "ok", "record": response.json()}
    return {"status": "error", "message": response.text[:500]}
