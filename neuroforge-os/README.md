# NeuroForge OS — Production Pipeline

A self-improving AI content pipeline for the NeuroForge brand.

---

## What This Does

Chains 6 AI agents in sequence to produce a complete content package for any topic:

```
Topic Input
    ↓
[Agent 1] Research Agent        → structured strategy brief
    ↓
[Agent 2] Book Architect Agent  → full book blueprint + title + transformation arc
    ↓
[Agent 3] Manuscript Agent      → book chapters in faculty voice
    ↓
[Agent 4] Shorts Script Agent   → 20–40 short-form video scripts
    ↓
[Agent 5] Funnel Agent          → landing page + email sequence + ad copy
    ↓
[Agent 6] QA Agent              → scores every output, flags issues, logs notes
    ↓
[Optimizer] Prompt Optimizer    → rewrites underperforming prompts based on QA data
```

Every output is saved to disk. Every QA score is logged to a JSON database. The optimizer reads those logs and improves the prompts automatically.

---

## Command Center & Florra Fleet Alpha

There is a control plane for all of this: an agent commander that launches and
supervises every agent in `scripts/`, a real-time console that shows where work
actually is on a live architecture map, and an autopilot that works a mission
book around the clock.

**Florra Fleet Alpha** (`FFA`) is a clone of the NeuroForge fleet: the same
agent architecture, its own identity, budget and cadence. It runs the loop this
pipeline was designed for without anyone driving it — next topic → full mission
→ QA every artifact → prompt optimizer → next topic.

```bash
python -m commander --fleet florra_alpha   # autopilot on, simulated
docker compose up -d florra-alpha          # 24/7, restarts with the host
```

Then open <http://127.0.0.1:8787>.

It ships in **simulate** mode: the whole loop runs end to end, spends nothing
and writes nothing, so you can watch a full day of operation before it costs a
cent. Going live is one setting, and the fleet still stops itself at its budget
ceiling, its daily cap and after repeated failures.

The commander itself runs on the Python standard library. One agent — the
Evidence Agent, a smolagents `CodeAgent` that checks claims against real
sources — adds `smolagents` and `ddgs` to `requirements.txt`; it writes and
executes Python, so it runs in a Docker sandbox and the autopilot never
dispatches it. Full documentation — fleet cloning, the rails, dispatch safety,
containing the code agent, how to add an agent — is in
[`commander/README.md`](commander/README.md).

---

## Setup

### 1. Install Python dependency

```bash
pip install anthropic
```

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY=your_key_here
```

Get your key at: https://console.anthropic.com

### 3. Folder structure

```
neuroforge-os/
  prompts/           ← the 6 agent system prompts
    01_research_agent.md
    02_book_architect_agent.md
    03_manuscript_agent.md
    04_shorts_script_agent.md
    05_funnel_agent.md
    06_qa_agent.md
    versions/        ← old prompt versions (auto-created by optimizer)
  scripts/
    neuroforge_pipeline.py   ← main orchestrator
    optimize_prompts.py      ← self-improvement loop
  commander/         ← agent commander + live command center
    registry.py      ← the fleet: every agent and how it launches
    web/             ← the console UI
  output/            ← all agent outputs (auto-created)
  neuroforge_db.json ← QA score log (auto-created)
```

---

## Usage

### Run the full pipeline on a topic

```bash
cd scripts

python neuroforge_pipeline.py \
  --topic "Stop Overthinking" \
  --faculty "Dr. Nova Vale" \
  --mode full
```

This runs all 6 agents in sequence and saves everything to `./output/stop_overthinking/`.

---

### Run individual stages

```bash
# Research brief only
python neuroforge_pipeline.py --topic "Dopamine Detox" --faculty "Kai Ren" --mode research

# Research + Blueprint
python neuroforge_pipeline.py --topic "Dopamine Detox" --faculty "Kai Ren" --mode blueprint

# Research + Blueprint + Chapter 1
python neuroforge_pipeline.py --topic "Dopamine Detox" --faculty "Kai Ren" --mode manuscript --chapter 1

# Scripts only (runs research first)
python neuroforge_pipeline.py --topic "Dopamine Detox" --faculty "Kai Ren" --mode scripts

# Funnel only (runs research + blueprint first)
python neuroforge_pipeline.py --topic "Dopamine Detox" --faculty "Kai Ren" --mode funnel
```

---

### QA an existing file

```bash
python neuroforge_pipeline.py \
  --topic "Stop Overthinking" \
  --faculty "Dr. Nova Vale" \
  --mode qa \
  --file ./output/stop_overthinking/03_chapter_01_20250101_120000.md \
  --content_type "Manuscript Chapter"
```

---

### Run the prompt optimizer

After running 5+ topics:

```bash
cd scripts

# See performance report and preview rewrites (safe — doesn't change anything)
python optimize_prompts.py

# Optimise a specific agent
python optimize_prompts.py --agent manuscript

# Apply rewrites to live prompts (backs up old versions first)
python optimize_prompts.py --apply

# Lower the threshold to force optimisation on all agents
python optimize_prompts.py --threshold 45 --apply
```

---

## Faculty Members

| Faculty | Domain | Tone |
|---------|--------|------|
| Dr. Nova Vale | Anxiety, overthinking, emotional regulation | Calm, clinical, reassuring |
| Kai Ren | Focus, dopamine, habits, productivity | Sharp, minimalist, tactical |
| Marcus Voss | Discipline, stoicism, identity | Direct, no fluff, masculine |
| Luna Hart | Relationships, attachment, boundaries | Warm, emotionally intelligent |
| Dr. Orion Hale | Neuroscience, sleep, brain optimization | Clinical but accessible |

---

## First 10 Topics (with Faculty)

| # | Topic | Faculty |
|---|-------|---------|
| 1 | Stop Overthinking | Dr. Nova Vale |
| 2 | Dopamine Detox | Kai Ren |
| 3 | Stop Procrastinating | Kai Ren |
| 4 | The Confidence Code | Luna Hart |
| 5 | Beat Phone Addiction | Kai Ren |
| 6 | Stop Negative Thoughts | Dr. Nova Vale |
| 7 | How to Read People | Luna Hart |
| 8 | The Discipline Blueprint | Marcus Voss |
| 9 | The Charisma Blueprint | Luna Hart |
| 10 | Beat Anxiety Fast | Dr. Nova Vale |

---

## The Self-Improving Loop

The system gets better over time through this cycle:

1. **Pipeline runs** → QA Agent scores every output and writes a Prompt Improvement Note
2. **Notes are logged** → stored in `neuroforge_db.json` with the score
3. **Optimizer reads logs** → after 5–10 topics, run `optimize_prompts.py`
4. **Prompts are rewritten** → Claude reads the failure patterns and improves the prompts
5. **Old versions are saved** → in `prompts/versions/` so you can roll back

Run the optimizer every 10 topics. Within 30–40 topics, the prompts will be significantly tighter than the starting versions.

---

## Approximate Costs Per Topic (Full Pipeline)

The pipeline makes approximately 12 API calls per full run (6 agents + 6 QA reviews):

| Agent | Approx tokens | Approx cost |
|-------|--------------|-------------|
| Research Agent | ~3,000 out | ~$0.015 |
| Book Architect | ~4,000 out | ~$0.020 |
| Manuscript Ch1 | ~4,000 out | ~$0.020 |
| Shorts Scripts (20) | ~6,000 out | ~$0.030 |
| Funnel Copy | ~5,000 out | ~$0.025 |
| 6x QA Reviews | ~2,000 out ea | ~$0.060 |
| **Total per topic** | | **~$0.17** |

*Estimates based on claude-sonnet-4 pricing. Actual costs vary with input length.*

At $0.17 per topic, running all 50 topics costs approximately $8–10 total.

---

## Non-Negotiables

These are hardcoded into every agent prompt:
- No fake citations or fabricated studies (the Evidence Agent checks this —
  see [`commander/README.md`](commander/README.md))
- No medical diagnosis claims
- No overclaiming or false promises
- Human QA review before any publishing
- All content brand-checked against the Faculty Bible

---

## Extending the Pipeline

To add a new agent:

1. Write a new system prompt following the same structure (`prompts/07_new_agent.md`)
2. Add a function `run_new_agent()` in `neuroforge_pipeline.py`
3. Add the QA step after it
4. Add it to `AGENT_NAME_MAP` in `optimize_prompts.py`
5. Wire it into `pipeline_full()` at the right stage
6. Add an `AgentSpec` in `commander/registry.py` so it appears on the command
   center — the launcher, the map and the credential checks all read from there

---

## Questions

Built for NeuroForge internal use. All prompts, scripts, and outputs are proprietary.
