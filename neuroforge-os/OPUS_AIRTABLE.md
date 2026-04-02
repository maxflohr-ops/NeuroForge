# Opus × Airtable Integration

Complete podcast clipping workflow — from source to clips to scheduling to performance tracking.

## Tables

1. **Opus Projects** — Clipping projects
   - Project Name, Source URL, Source Type
   - Status (Processing, Completed), Total/Generated Clips
   - Processing Started/Completed dates

2. **Opus Clips** — Generated clips
   - Project, Clip Number, Title, Duration
   - Start/End Time, Thumbnail, Video URL, Download Path
   - Quality Score, Speakers, Topics, Keywords
   - Engagement Predicted, Platform Ready flag, Posted To

3. **Opus Scheduling** — Clip scheduling for posting
   - Clip, Platform, Scheduled Date/Time
   - Post Status (Scheduled, Posted, Failed)
   - Posted Date, Caption, Hashtags, Campaign

4. **Opus Podcasts** — Podcast sources for auto-clipping
   - Podcast Name, Host, RSS Feed URL
   - Total Episodes, Episodes Clipped
   - Auto Clip Enabled flag, Last Auto Clip Date
   - Avg Clips Per Episode

5. **Opus Performance** — Clip engagement tracking
   - Clip ID, Platform, Views, Likes, Shares, Comments
   - Engagement Rate, Posted Date, Data Updated

## Workflow

### 1. Create Project
```python
from scripts.opus_airtable_logger import OpusAirtableLogger

logger = OpusAirtableLogger()

# Create a clipping project
project = logger.create_project(
    project_name="My Podcast Clips",
    source_url="https://podcasts.example.com/my-podcast",
    source_type="Podcast",
    notes="Auto-clip all new episodes"
)
```

### 2. Log Clips
```python
# As Opus generates clips
clip = logger.log_clip(
    project="My Podcast Clips",
    clip_number=1,
    title="Why You Should Start a Podcast",
    duration_sec=45,
    start_time="00:12:30",
    end_time="00:13:15",
    thumbnail_url="https://opus.pro/thumbs/clip_001.jpg",
    video_url="https://opus.pro/clips/clip_001.mp4",
    download_path="opus-clips/my-podcast/clip_001.mp4",
    speakers="John Doe",
    topics="Podcasting, Content Creation",
    keywords="podcast,growth,monetization",
    quality_score=95
)
```

### 3. Schedule for Posting
```python
# Schedule to platforms
logger.schedule_clip(
    clip="Why You Should Start a Podcast",
    platform="TikTok",
    scheduled_date="2025-03-20",
    caption="Best advice for starting your podcast 🎙️",
    hashtags="#podcasting #contentcreator #motivation",
    campaign="Spring Growth"
)

logger.schedule_clip(
    clip="Why You Should Start a Podcast",
    platform="Instagram Reels",
    scheduled_date="2025-03-20",
    caption="The secret to podcast success... 🎙️"
)
```

### 4. Track Performance
```python
# Log engagement after posting
logger.log_performance(
    clip_id="clip_001",
    platform="TikTok",
    views=15000,
    likes=2300,
    shares=450,
    comments=380,
    engagement_rate=18.5,
    posted_date="2025-03-20"
)
```

### 5. Auto-Clip from Podcasts
```python
# Add podcast for auto-clipping
logger.add_podcast(
    podcast_name="The Smart Creator",
    host="Jane Smith",
    rss_feed_url="https://example.com/rss/smartcreator",
    auto_clip_enabled=True
)

# Get all auto-clip podcasts
auto_podcasts = logger.get_auto_clip_podcasts()
```

## Integration Points

**With Florra:**
- Download Opus clips → add to Florra Content Library
- Sync scheduled Opus clips → Florra Campaigns for ad spend tracking

**With NeuroForge:**
- Use NeuroForge-generated captions → Opus clip scheduling
- Track NeuroForge content performance in Opus Performance table

**With OpenClaw:**
- OpenClaw bot monitors Opus Performance
- Auto-suggests improvements to captions based on engagement

## Airtable Base

Base ID: `applXEAjh6k3Xmybl`

Tables:
- Opus Projects: `tblvMbbfjYrOuPqwS`
- Opus Clips: `tblW3n5Fjr9lBgJph`
- Opus Scheduling: `tblKYGRy5jU89q66Z`
- Opus Podcasts: `tblT4R7RtjEpDcwi3`
- Opus Performance: `tblSOYD7BfyIY77e6`

## Logger Usage Examples

```python
from scripts.opus_airtable_logger import OpusAirtableLogger

logger = OpusAirtableLogger()

# Create project
project_response = logger.create_project(
    project_name="Q1 Clips",
    source_url="https://podcastfeed.com/show",
    source_type="Podcast"
)
project_id = project_response['id']

# Log clip
clip_response = logger.log_clip(
    project="Q1 Clips",
    clip_number=1,
    title="The Future of Content",
    duration_sec=60,
    speakers="Host Name",
    topics="Content Strategy, AI",
    keywords="AI,content,marketing"
)
clip_id = clip_response['id']

# Schedule to multiple platforms
for platform in ["TikTok", "Instagram Reels", "YouTube Shorts"]:
    logger.schedule_clip(
        clip="The Future of Content",
        platform=platform,
        scheduled_date="2025-03-25",
        caption="The future of content is here 🚀"
    )

# Get scheduled clips
scheduled = logger.get_scheduled_clips()
print(f"Scheduled clips: {len(scheduled)}")

# Update project when done
logger.update_project_status(
    record_id=project_id,
    status="Completed",
    clips_generated=42
)

# Track performance
logger.log_performance(
    clip_id="the-future-clip",
    platform="TikTok",
    views=50000,
    likes=8500,
    shares=1200,
    comments=650,
    engagement_rate=21.3
)
```

## Next Steps

1. Connect Opus API → auto-log clips as they're generated
2. Set up Flowstage webhook → auto-post scheduled clips
3. Build performance dashboard in Airtable
4. Sync with Florra for cross-platform ad campaigns
5. Integrate with OpenClaw for engagement optimization
