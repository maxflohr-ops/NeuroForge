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

"""Florra UGC agent.

ADK port of the Florra OS workflow (see neuroforge-os/FLORRA_AIRTABLE.md):
TikTok sound research -> creator scoring -> outreach -> content -> Spark Ads.
Unlike the NeuroForge content pipeline (a sequential text pipeline), Florra's
work is tool-shaped: deterministic scoring and Airtable reads/writes live in
``app/tools.py``; the LLM handles judgment — outreach copy and ad strategy —
via two specialist sub-agents.
"""

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import (
    add_creator,
    add_spark_code,
    add_to_ugc_pipeline,
    get_pipeline_by_status,
    score_creator,
    update_pipeline_status,
)


MODEL = "gemini-3.7-flash"

_BRAND_CONTEXT = (
    "Florra is a UGC music-marketing operation. It finds TikTok creators "
    "already using a target sound (via Chartex sound lookup), scores them, "
    "runs outreach, collects content, and turns the best posts into native "
    "ads — TikTok Spark Ads first, then Meta lookalike audiences, sound "
    "retargeting, and hashtag interest targeting. The pipeline stages are: "
    "Identified -> Outreach -> Contract -> Content -> Paid. Everything is "
    "tracked in the Florra Airtable base (People, UGC Pipeline, Content "
    "Library, Spark Codes, Campaigns)."
)

outreach_agent = Agent(
    name="outreach_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    description=(
        "Writes personalized creator DM scripts and per-creator briefs for "
        "Florra campaigns."
    ),
    instruction=(
        f"{_BRAND_CONTEXT}\n\n"
        "You write Florra's creator outreach. Given a creator (handle, tier, "
        "content style, the sound and campaign), produce:\n"
        "1. A personalized DM script — short, human, references something "
        "specific about their content, states the offer plainly (paid "
        "collaboration using the campaign sound), one clear call to action. "
        "No corporate speak, no walls of text, no fake flattery.\n"
        "2. A per-creator brief — the sound, the format that is working for "
        "this sound, what to keep from their natural style, deliverables, "
        "and how Spark Code authorization works (we run their post as an ad "
        "from their account; it stays native).\n\n"
        "Match tone to the creator's tier: Nano/Micro creators get warmer, "
        "more personal DMs; Macro/Mega creators and their managers get "
        "tighter, more professional ones. Never promise specific payment "
        "amounts unless they were given to you.\n"
        "When done, transfer back to the orchestrator."
    ),
    output_key="outreach_package",
)

ads_strategist_agent = Agent(
    name="ads_strategist_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    description=(
        "Plans the paid amplification for Florra campaigns: Spark Ads, Meta "
        "lookalikes, sound retargeting, hashtag interest targeting."
    ),
    instruction=(
        f"{_BRAND_CONTEXT}\n\n"
        "You plan paid amplification for a Florra campaign. Given the "
        "campaign, its creators, content performance, and budget, produce an "
        "ad strategy across the four Florra plays:\n"
        "1. TikTok Spark Ads — which creator posts to authorize and run, "
        "and why those posts.\n"
        "2. Meta custom + lookalike audiences — built from the campaign's "
        "creator list; where the ads should point (Spotify/Apple Music).\n"
        "3. TikTok sound retargeting — audiences of users who engaged with "
        "the campaign sound.\n"
        "4. Hashtag interest targeting — cold audiences mapped from the "
        "hashtags on the campaign's content.\n\n"
        "For each play: recommended budget split, the audience, the "
        "creative, and the metric that decides scale-or-kill. Be concrete "
        "and ruthless about sequencing — Spark Ads on proven organic posts "
        "come before cold audiences. When done, transfer back to the "
        "orchestrator."
    ),
    output_key="ad_strategy",
)

root_agent = Agent(
    name="florra_orchestrator",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Runs Florra's UGC workflow: scores creators, tracks the pipeline in "
        "Airtable, and dispatches outreach writing and ad strategy."
    ),
    instruction=(
        f"{_BRAND_CONTEXT}\n\n"
        "You are the Florra Orchestrator. Route work like this:\n"
        "- Scoring a creator: call score_creator with their numbers, report "
        "the score, tier, and recommendation. If they qualify (score 45+ or "
        "the user says so), offer to add them to Airtable with add_creator "
        "and add_to_ugc_pipeline at status 'Identified'.\n"
        "- Pipeline questions ('who is in Outreach?'): call "
        "get_pipeline_by_status.\n"
        "- Stage changes ('mark rec123 as Contract'): call "
        "update_pipeline_status.\n"
        "- Spark Code received: call add_spark_code.\n"
        "- DM scripts or creator briefs: transfer to outreach_agent with "
        "the creator context.\n"
        "- Ad strategy or budget planning: transfer to ads_strategist_agent "
        "with the campaign context.\n\n"
        "Confirm before any Airtable write, and echo the record ID after. "
        "If an Airtable tool reports a missing API key, relay that to the "
        "user instead of retrying. Never invent creator stats — score only "
        "with numbers the user or a tool gave you."
    ),
    tools=[
        score_creator,
        add_creator,
        add_to_ugc_pipeline,
        update_pipeline_status,
        get_pipeline_by_status,
        add_spark_code,
    ],
    sub_agents=[outreach_agent, ads_strategist_agent],
)

app = App(
    root_agent=root_agent,
    name="app",
)
