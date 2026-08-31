# neuroforge-agent — architecture and extension guide

ADK port of the NeuroForge OS six-stage content pipeline
(`neuroforge-os/scripts/neuroforge_pipeline.py` reimagined as a multi-agent
system). Lives in `neuroforge-agent/`.

## Agent tree

```
neuroforge_orchestrator (LlmAgent, gemini-3.7-flash)
├── tool: get_faculty_roster()          # the 5 faculty profiles
└── neuroforge_pipeline (SequentialAgent)
    ├── research_agent        → output_key: research_brief
    ├── book_architect_agent  → output_key: book_blueprint
    ├── manuscript_agent      → output_key: manuscript_chapter  (Chapter 1 by default)
    ├── shorts_script_agent   → output_key: shorts_scripts
    ├── funnel_agent          → output_key: funnel_copy
    └── qa_agent              → output_key: qa_report
```

Flow: user brings a topic → orchestrator calls `get_faculty_roster`, assigns
faculty + pillar (honoring any user choice), states the assignment, then
transfers to the pipeline. Each stage reads the topic assignment and all
upstream outputs from conversation history (SequentialAgent gives every
stage the full transcript; `output_key` additionally mirrors each result
into session state).

## Where things live

- `app/agent.py` — all agents. `FACULTY_PROFILES` dict is the roster
  (mirrors `neuroforge-os/scripts/neuroforge_pipeline.py`); keep the two in
  sync if faculty change.
- `app/prompts/*.md` — the six production prompts, copied verbatim from
  `neuroforge-os/prompts/`. **Edit brand voice there, not in agent.py.**
  `_load_prompt()` appends a short "PIPELINE CONTEXT" addendum telling each
  stage to read inputs from history and produce only its own output.
- `tests/eval/datasets/basic-dataset.json` — three cases: capabilities,
  faculty assignment (with reference answer: Kai Ren for procrastination),
  full pipeline dispatch. The pipeline case is expensive (7+ model calls).

## Extending

- **New faculty member**: add to `FACULTY_PROFILES` (and the source-of-truth
  copy in neuroforge-os); the prompts describe faculty in their FACULTY
  CONTEXT sections — update those too.
- **New stage** (e.g. a HeyGen video-script stage): add a prompt file, an
  `Agent` with an `output_key`, insert into `neuroforge_pipeline.sub_agents`
  in order, and extend the QA addendum's list of outputs to score.
- **Single-stage runs** ("just give me shorts scripts"): a sub-agent can
  belong to only one parent in ADK. Don't re-parent pipeline stages onto the
  orchestrator; instead wrap a stage in `AgentTool` or create a sibling
  agent instance from the same prompt file.
- **Prompt tuning**: prefer `agents-cli eval optimize` over hand-tweaking
  once eval cases exist.

## Known constraints

- The prompt files contain no `{` braces — safe as plain instructions. If a
  future prompt adds literal braces, ADK will treat `{word}` as a state
  injection and error; switch that agent's `instruction` to a callable
  (instruction provider) to bypass templating.
- "Hart" (Luna Hart) is in the codespell ignore list in `pyproject.toml`.
- Integration tests and eval need Gemini auth; without it only
  imports/lint/unit tests are verifiable.
