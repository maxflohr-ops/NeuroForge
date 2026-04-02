# Florra × Airtable Integration

Complete UGC workflow automation — from TikTok sound lookup to creator scoring to content library to ads.

## Tables

1. **People** — Creator database
   - Name, TikTok/Instagram/YouTube handles, followers, country
   - Engagement rate, follower tier, sound trend score, overall score
   - Profile URL, content quality, notes

2. **UGC Pipeline** — Workflow tracking
   - Creator, Campaign, Sound, Status (Identified → Outreach → Contract → Content → Paid)
   - Spark Code, Video URL, Engagement, Views
   - Dates for each stage

3. **Content Library** — Downloaded content archive
   - Creator, Platform, Filename, File Path
   - Hashtags, Sound Used, Quality Score
   - Campaign Tags, Usable for Ads flag

4. **Spark Codes** — TikTok Spark Ad tracking
   - Creator, Handle, Code, Video URL
   - Status, Campaign, Expiry, Activated Date
   - Ad Performance tracking

5. **Campaigns** — Campaign management
   - Campaign Name, Status, Sound ID, Sound Name
   - Target metrics, Budget, Views, Engagement
   - Brief, DM Script, Performance Report

6. **Metadata** — System configuration
   - Key-value pairs, type, last updated
   - Stores integration IDs and settings

## Setup

### Environment Variables
```
AIRTABLE_API_KEY=AIRTABLE_API_KEY
AIRTABLE_BASE_ID=applXEAjh6k3Xmybl
COBALT_URL=http://localhost:9000
```

### Cobalt Docker Setup
```bash
docker run -d -e API_URL=http://localhost:9000 -p 9000:9000 --name cobalt ghcr.io/imputnet/cobalt:latest
```

## Workflow

### 1. Sound Research → Creator Discovery
```bash
npm run research:sound -- https://vt.tiktok.com/ZS9R27PmQHbMY-4lI9C/
```
- Follows short link, parses TikTok URL
- Looks up sound on Chartex (all creators using it)
- Scores creators (followers, posts, trend, influence)
- Auto-adds qualified creators to People table
- Queues for profile review

### 2. Profile Review → Content Download
```bash
npm run cobalt:add https://www.tiktok.com/@creator/video/123456789
npm run cobalt:process  # Downloads queued content
```
- Review creator profiles, find best post
- Queue for download via Cobalt
- Downloaded content → Content Library
- JSON sidecar with metadata

### 3. Content Library → Creator Brief
```bash
npm run cobalt:brief @creator_handle
```
- Generates per-creator brief with:
  - DM script (personalized based on content downloaded)
  - Sound format report
  - Campaign portfolio

### 4. UGC Pipeline → Ads
Content flows through stages:
- **Identified** — Found via sound research
- **Outreach** — DM sent
- **Contract** — Agreed
- **Content** — Video received + added to library
- **Paid** — Running as ad (Spark Ad, Meta, or retargeting)

### 5. Ad Strategies

**TikTok Spark Ads:**
- Creator posts with your sound (organic)
- Get Spark Code authorization
- Run their post as paid ad from their account
- Looks completely native
- Track in Spark Codes table

**Meta Custom Audience:**
- Export creator list (handles, countries, tiers) from People table
- Meta builds lookalike of their followers
- Ads point to Spotify/Apple Music

**TikTok Sound Retargeting:**
- Target users who engaged with specific sounds
- Already have sound IDs from Chartex
- Auto-create audience + ad set

**Hashtag Interest Targeting:**
- Extract hashtags from downloaded content
- Map to Meta/TikTok interest category IDs
- Cold audience campaigns

## Logger Usage

```python
from scripts.florra_airtable_logger import FlorraAirtableLogger

logger = FlorraAirtableLogger()

# Add discovered creator
logger.add_creator(
    name="John Creator",
    tiktok_handle="@johncreator",
    tiktok_followers=250000,
    country="US",
    engagement_rate=8.5,
    follower_tier="Macro",
    overall_score=92
)

# Add to pipeline
logger.add_to_ugc_pipeline(
    creator="John Creator",
    campaign="Spring Music Launch",
    sound="Summer Vibes",
    sound_id="sound_12345",
    status="Identified"
)

# Log downloaded content
logger.add_to_content_library(
    creator="John Creator",
    platform="TikTok",
    filename="john_creator_01.mp4",
    file_path="content-library/tiktok/john_creator/01.mp4",
    hashtags="#musicvideo #trending",
    sound_used="Summer Vibes",
    quality_score=95,
    usable_for_ads="Yes"
)

# Track Spark Code
logger.add_spark_code(
    creator="John Creator",
    tiktok_handle="@johncreator",
    spark_code="SPARK_ABC123XYZ",
    video_url="https://www.tiktok.com/@johncreator/video/123456789",
    campaign="Spring Music Launch",
    code_expiry="2025-04-15"
)

# Update pipeline status
logger.update_pipeline_status(
    record_id="rec123abc",
    status="Contract"
)

# Query helpers
identified = logger.get_pipeline_by_status("Identified")
creator_content = logger.get_content_by_creator("John Creator")
macro_creators = logger.get_creators_by_tier("Macro")
```

## Airtable Base

Base ID: `applXEAjh6k3Xmybl`

View at: https://airtable.com/applXEAjh6k3Xmybl

## Next Steps

1. **Integrate sound-lookup.js** → auto-populate People + UGC Pipeline
2. **Wire Cobalt client** → auto-queue and process downloads
3. **Build brief generator** → auto-create DM scripts
4. **Add Spark Code tracking** → manage TikTok native ads
5. **Connect Meta Ads API** → custom + lookalike audiences
6. **Connect TikTok Ads API** → sound retargeting + hashtag campaigns
7. **Build campaign dashboard** — track performance across all strategies
