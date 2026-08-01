# Master Airtable Integration — All Systems

Single Airtable base (`applXEAjh6k3Xmybl`) powers 4 interconnected systems.

---

## Systems Overview

### 1. **NeuroForge** — AI Content Generation
Generates educational books, scripts, funnels for topics.

**Tables:**
- `NeuroForge Projects` — Topic, Faculty, Generated content files
- `Pipeline Runs` — Execution logs, QA scores, timestamps

**Logger:** `scripts/airtable_sync.py`

**Usage:**
```bash
cd neuroforge-os
docker compose run --rm airtable-sync --topic "Stop Overthinking"
```

---

### 2. **OpenClaw** — AI Agent + Self-Improvement
Telegram bot, web search, continuously improves prompts.

**Tables:**
- `OpenClaw Interactions` — User queries, responses, satisfaction scores
- `Agent Performance` — Metrics over time
- `Improvement Suggestions` — Auto-generated prompt improvements
- `Telegram Messages` — All bot activity
- `Lead Tracking` — User engagement
- `Model Optimization Log` — Prompt version history

**Logger:** `scripts/openclaw_airtable_logger.py`

**Usage:**
```python
from scripts.openclaw_airtable_logger import OpenClawAirtableLogger

logger = OpenClawAirtableLogger()
logger.log_interaction(
    user_query="What's trending in music?",
    response="Here are the top trends...",
    satisfaction="High"
)
```

---

### 3. **Florra** — UGC Research → Creator Discovery → Content Library → Ads
End-to-end UGC workflow from sound research to paid ads.

**Tables:**
- `People` — Creators (handles, followers, scores)
- `UGC Pipeline` — Status workflow (Identified → Outreach → Contract → Content → Paid)
- `Content Library` — Downloaded videos with metadata
- `Spark Codes` — TikTok native ad codes
- `Campaigns` — Campaign briefs, DM scripts, performance, visibility + bounty settings
- `Campaign Access` — Invites and applications for private campaigns
- `Metadata` — Integration config

**Private campaigns:** A campaign's `Visibility` is `Public` or `Private`. Private campaigns set an `Access Mode`:
- `Invite` — only creators you invite can receive the bounty
- `Apply` — creators apply and must be approved before receiving the bounty

Bounty payouts are enforced: `update_pipeline_status(..., "Paid")` refuses to mark a creator Paid on a private campaign unless they hold an invite or an approved application in `Campaign Access`.

**Logger:** `scripts/florra_airtable_logger.py`

**Workflow:**
1. Paste TikTok URL → finds creators using that sound
2. Download content via Cobalt → auto-logs to library
3. Generate creator briefs with personalized DM scripts
4. Track Spark Codes for native ads
5. Export to Meta/TikTok for paid campaigns

**Usage:**
```python
from scripts.florra_airtable_logger import FlorraAirtableLogger

logger = FlorraAirtableLogger()
logger.add_creator(
    name="Creator Name",
    tiktok_handle="@handle",
    tiktok_followers=250000,
    overall_score=92
)

logger.add_to_ugc_pipeline(
    creator="Creator Name",
    campaign="Spring Launch",
    sound="Summer Vibes",
    sound_id="sound_123"
)

# Private campaign with bounty — invite-only
logger.create_campaign(
    name="Spring Launch",
    brief="UGC videos using the Spring sound",
    bounty_amount=250,
    visibility="Private",
    access_mode="Invite"
)
logger.invite_creator(campaign="Spring Launch", creator="Creator Name")

# Or apply-based: creators request access, you approve
logger.create_campaign(
    name="Summer Push",
    bounty_amount=150,
    visibility="Private",
    access_mode="Apply"
)
logger.apply_to_campaign(campaign="Summer Push", creator="Creator Name",
                         message="200k followers, 8% ER")
for app in logger.get_campaign_applications("Summer Push"):
    logger.review_application(app["id"], approve=True)
```

---

### 4. **Opus** — Podcast Clipping → Scheduling → Performance
Auto-clip podcasts, schedule to platforms, track engagement.

**Tables:**
- `Opus Projects` — Clipping projects
- `Opus Clips` — Generated clips with metadata
- `Opus Scheduling` — Scheduled posts to platforms
- `Opus Podcasts` — Auto-clip podcast sources
- `Opus Performance` — Engagement tracking (views, likes, shares)

**Logger:** `scripts/opus_airtable_logger.py`

**Usage:**
```python
from scripts.opus_airtable_logger import OpusAirtableLogger

logger = OpusAirtableLogger()

# Create project
logger.create_project(
    project_name="My Clips",
    source_url="https://podcast.com/feed"
)

# Log clip
logger.log_clip(
    project="My Clips",
    clip_number=1,
    title="Best Advice",
    speakers="Host Name"
)

# Schedule
logger.schedule_clip(
    clip="Best Advice",
    platform="TikTok",
    scheduled_date="2025-03-25",
    caption="The best advice 🎙️"
)

# Track performance
logger.log_performance(
    clip_id="best-advice",
    platform="TikTok",
    views=50000,
    likes=8500
)
```

---

## Integration Points

### NeuroForge → Florra
- Use NeuroForge-generated captions → Florra Content Library → Spark Ads
- Track performance in Opus + report back to NeuroForge

### Florra ↔ Opus
- Opus clips → Florra Content Library
- Sync engagement metrics both ways
- Coordinate multi-platform campaigns

### OpenClaw ← All Systems
- Monitor engagement across all platforms
- Suggest improvements to captions/briefs
- Auto-optimize prompts based on performance patterns

### Opus → OpenClaw
- Send top-performing clip captions to OpenClaw
- Bot learns what resonates, suggests patterns

---

## Airtable Base

**Base ID:** `applXEAjh6k3Xmybl`

**All Tables (18 total):**

NeuroForge (2):
- tblkslL7m7mORCHkR — NeuroForge Projects
- tblxxJIc9VXjZwQMT — Pipeline Runs

OpenClaw (6):
- tblxjo12st1GoOuUM — OpenClaw Interactions
- tbl2F024MIEMh26ng — Agent Performance
- tblKhnROIh8ssTqiE — Improvement Suggestions
- tblQ3Df9ck45HTnfC — Telegram Messages
- tblfCsmmbtUpOPhtX — Lead Tracking
- tbluLfkFPyv3ugssf — Model Optimization Log

Florra (7):
- tblYqPt2BYVjMaXFk — People
- tblqTn9O3rIMMecbT — UGC Pipeline
- tblmKJcNNOeEUaI79 — Content Library
- tblqRpE6Ou9vXImey — Spark Codes
- tblMUfJKvYiOEARy3 — Campaigns
- Campaign Access — create in Airtable, then set `FLORRA_CAMPAIGN_ACCESS_TABLE` to its table ID
- tbleJMnUc8u59V72L — Metadata

**Campaign Access fields:** Campaign (text), Creator (text), Status (single select: Invited, Accepted, Applied, Approved, Rejected), Requested Date (date), Decision Date (date), Message (long text), Notes (long text)

**New Campaigns fields:** Visibility (single select: Public, Private), Access Mode (single select: Invite, Apply), Bounty Amount (currency), Brief (long text), DM Script (long text), Created Date (date)

Opus (5):
- tblvMbbfjYrOuPqwS — Opus Projects
- tblW3n5Fjr9lBgJph — Opus Clips
- tblKYGRy5jU89q66Z — Opus Scheduling
- tblT4R7RtjEpDcwi3 — Opus Podcasts
- tblSOYD7BfyIY77e6 — Opus Performance

---

## Environment Variables

```
AIRTABLE_API_KEY=AIRTABLE_API_KEY
AIRTABLE_BASE_ID=applXEAjh6k3Xmybl
COBALT_URL=http://localhost:9000
FLORRA_CAMPAIGN_ACCESS_TABLE=tblXXXXXXXXXXXXXX  # Campaign Access table ID
```

---

## Quick Reference

| System | Purpose | Logger |
|--------|---------|--------|
| NeuroForge | Generate educational content | `airtable_sync.py` |
| OpenClaw | AI agent + self-improvement | `openclaw_airtable_logger.py` |
| Florra | UGC research & ads | `florra_airtable_logger.py` |
| Opus | Podcast clipping & scheduling | `opus_airtable_logger.py` |

---

## Next Steps

1. **Connect APIs:**
   - Opus API → auto-log clips
   - Florra sound-lookup → auto-add creators
   - OpenClaw interactions → auto-log Telegram

2. **Build Dashboards:**
   - NeuroForge: Content generation velocity
   - Florra: Creator discovery + spend tracking
   - Opus: Clip performance over time
   - OpenClaw: Agent improvement metrics

3. **Cross-System Automations:**
   - NeuroForge output → Florra campaigns
   - Opus top clips → OpenClaw learns captions
   - Florra engagement → NeuroForge refines topics

4. **Add Flowstage Webhook:**
   - Opus scheduled clips → auto-post via Flowstage
   - Florra content → coordinate posting

---

**View base:** https://airtable.com/applXEAjh6k3Xmybl
