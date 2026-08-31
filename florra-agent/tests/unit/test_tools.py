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

from app.tools import PIPELINE_STAGES, add_to_ugc_pipeline, score_creator


def test_score_creator_strong_candidate():
    result = score_creator(
        followers=250_000,
        engagement_rate=8.5,
        posts_with_sound=4,
        avg_views=500_000,
    )
    assert result["follower_tier"] == "Mid"
    assert 0 <= result["overall_score"] <= 100
    assert result["overall_score"] >= 70
    assert result["recommendation"] == "strong outreach candidate"


def test_score_creator_tiers():
    assert score_creator(5_000, 5, 1, 10_000)["follower_tier"] == "Nano"
    assert score_creator(50_000, 5, 1, 10_000)["follower_tier"] == "Micro"
    assert score_creator(750_000, 5, 1, 10_000)["follower_tier"] == "Macro"
    assert score_creator(2_000_000, 5, 1, 10_000)["follower_tier"] == "Mega"


def test_score_creator_zero_followers_no_crash():
    result = score_creator(0, 0, 0, 0)
    assert result["overall_score"] == 0
    assert result["follower_tier"] == "Nano"


def test_pipeline_rejects_unknown_stage():
    result = add_to_ugc_pipeline("A", "B", "C", "D", "NotAStage")
    assert result["status"] == "error"
    assert "Identified" in str(PIPELINE_STAGES)
