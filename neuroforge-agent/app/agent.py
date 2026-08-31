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

"""NeuroForge content agent.

Wraps the NeuroForge OS six-stage content pipeline (research brief -> book
blueprint -> manuscript chapter -> shorts scripts -> funnel copy -> QA report)
as an ADK multi-agent system. Stage instructions are loaded verbatim from the
production prompt files in ``app/prompts/``.
"""

from pathlib import Path

from google.adk.agents import Agent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types


MODEL = "gemini-3.7-flash"

_PROMPTS_DIR = Path(__file__).parent / "prompts"

FACULTY_PROFILES = {
    "Dr. Nova Vale": {
        "domain": "Anxiety, overthinking, intrusive thoughts, emotional regulation",
        "tone": "Calm, intelligent, reassuring, clear",
        "pillar": "Overthinking, anxiety, emotional regulation",
    },
    "Kai Ren": {
        "domain": "Focus, dopamine, habits, productivity",
        "tone": "Sharp, minimalist, tactical",
        "pillar": "Focus, dopamine, productivity",
    },
    "Marcus Voss": {
        "domain": "Discipline, stoicism, self-respect, mental toughness",
        "tone": "Direct, masculine, controlled, no fluff",
        "pillar": "Discipline, identity, life design",
    },
    "Luna Hart": {
        "domain": "Relationships, attachment, boundaries, communication",
        "tone": "Warm, emotionally intelligent, insightful",
        "pillar": "Relationships, attachment, boundaries",
    },
    "Dr. Orion Hale": {
        "domain": "Neuroscience, sleep, brain optimization, mental performance",
        "tone": "Clinical but accessible",
        "pillar": "Focus, dopamine, productivity",
    },
}


def get_faculty_roster() -> dict:
    """Return the NeuroForge faculty roster.

    Each entry maps a faculty member's name to their domain of expertise,
    voice/tone profile, and the content pillar they own. Use this to assign
    the right faculty member to a topic before running the content pipeline.

    Returns:
        A dict of faculty name -> {domain, tone, pillar}.
    """
    return FACULTY_PROFILES


def _load_prompt(filename: str, addendum: str) -> str:
    text = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    return f"{text}\n\n---\n\n## PIPELINE CONTEXT\n{addendum}\n"


_STAGE_ADDENDUM = (
    "You are running as one stage of the NeuroForge ADK content pipeline. "
    "The topic assignment (topic, pillar, faculty, audience notes) and all "
    "upstream agent outputs are available in the conversation history — read "
    "them from there instead of asking for them. Produce ONLY the output "
    "specified above, then stop."
)

research_agent = Agent(
    name="research_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt("01_research_agent.md", _STAGE_ADDENDUM),
    output_key="research_brief",
)

book_architect_agent = Agent(
    name="book_architect_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt("02_book_architect_agent.md", _STAGE_ADDENDUM),
    output_key="book_blueprint",
)

manuscript_agent = Agent(
    name="manuscript_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt(
        "03_manuscript_agent.md",
        _STAGE_ADDENDUM
        + " If no specific chapter was requested, write Chapter 1 from the "
        "book blueprint.",
    ),
    output_key="manuscript_chapter",
)

shorts_script_agent = Agent(
    name="shorts_script_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt("04_shorts_script_agent.md", _STAGE_ADDENDUM),
    output_key="shorts_scripts",
)

funnel_agent = Agent(
    name="funnel_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt("05_funnel_agent.md", _STAGE_ADDENDUM),
    output_key="funnel_copy",
)

qa_agent = Agent(
    name="qa_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction=_load_prompt(
        "06_qa_agent.md",
        _STAGE_ADDENDUM + " Score every upstream output produced in this conversation "
        "(research brief, book blueprint, manuscript chapter, shorts scripts, "
        "funnel copy).",
    ),
    output_key="qa_report",
)

neuroforge_pipeline = SequentialAgent(
    name="neuroforge_pipeline",
    description=(
        "Runs the full NeuroForge content pipeline for an assigned topic: "
        "research brief, book blueprint, manuscript chapter, short-form video "
        "scripts, funnel copy, and a QA report — in that order."
    ),
    sub_agents=[
        research_agent,
        book_architect_agent,
        manuscript_agent,
        shorts_script_agent,
        funnel_agent,
        qa_agent,
    ],
)

root_agent = Agent(
    name="neuroforge_orchestrator",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Front desk of the NeuroForge content studio. Takes a topic, assigns "
        "faculty and pillar, and dispatches the six-stage content pipeline."
    ),
    instruction=(
        "You are the NeuroForge Orchestrator — the front desk of NeuroForge, "
        "a modern brain-performance and psychology media brand. NeuroForge "
        "produces practical, credible self-improvement content: books, "
        "short-form video scripts, and sales funnels. The brand is clean, "
        "intelligent, and never corny; it never makes medical claims, never "
        "fabricates citations, and never uses generic motivational filler.\n\n"
        "Your job:\n"
        "1. When the user brings a topic (e.g. 'Stop Overthinking'), call "
        "get_faculty_roster and assign the faculty member whose domain best "
        "fits the topic, along with their content pillar. If the user names "
        "a faculty member or pillar, honor their choice.\n"
        "2. State the assignment in one short line: topic, pillar, faculty, "
        "plus any audience notes the user gave.\n"
        "3. Transfer to the neuroforge_pipeline agent to produce the full "
        "content package (research brief, book blueprint, Chapter 1, shorts "
        "scripts, funnel copy, QA report).\n\n"
        "If the user only wants to chat about the brand, faculty, or "
        "pipeline, answer directly without dispatching the pipeline. Do not "
        "dispatch the pipeline until you have a concrete topic."
    ),
    tools=[get_faculty_roster],
    sub_agents=[neuroforge_pipeline],
)

app = App(
    root_agent=root_agent,
    name="app",
)
