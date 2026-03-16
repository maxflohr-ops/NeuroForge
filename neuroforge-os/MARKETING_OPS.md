# NeuroForge — Marketing Operations Plan

## The Model

Each faculty member is an **AI-powered influencer** — a HeyGen avatar with their own social media presence, audience, and monetization funnel. The pipeline generates content; HeyGen turns it into video; social media distributes it; link-in-bio sells the books.

```
Pipeline (content)  →  HeyGen (video)  →  Social (distribution)  →  Funnel (monetization)
     ↓                     ↓                     ↓                       ↓
  Scripts + Books      AI Avatars          TikTok/Reels/Shorts      Link-in-bio → Book
```

---

## Faculty Accounts — Social Media Structure

Each faculty member operates as an independent creator brand with multiple platform accounts:

### Dr. Nova Vale — @dr.novavale
**Niche:** Anxiety, overthinking, emotional regulation
**Audience:** Women 22–38, high-achievers who can't turn their brain off
**Avatar Style:** Professional but warm — think therapist on camera, soft lighting, neutral tones
**Posting Voice:** Calm, measured, slightly clinical — like she's explaining your brain to you

| Platform | Handle | Content Type |
|----------|--------|-------------|
| TikTok | @dr.novavale | 30–60s talking head scripts |
| Instagram Reels | @dr.novavale | Same scripts + carousel posts |
| YouTube Shorts | @DrNovaVale | Same scripts (repurposed) |
| Instagram Main | @dr.novavale | Carousels, quote graphics, book promos |

**Topics:** Stop Overthinking, Stop Negative Thoughts, Beat Anxiety Fast, The Rebirth Blueprint

---

### Kai Ren — @kairenofficial
**Niche:** Focus, dopamine, habits, productivity
**Audience:** Men 20–35, ambitious but scattered, doom-scrollers who want to fix it
**Avatar Style:** Clean, minimalist — dark background, sharp lighting, no clutter
**Posting Voice:** Fast, direct, no filler — like a performance coach who doesn't waste your time

| Platform | Handle | Content Type |
|----------|--------|-------------|
| TikTok | @kairenofficial | 30–60s talking head scripts |
| Instagram Reels | @kairenofficial | Same scripts + carousel posts |
| YouTube Shorts | @KaiRen | Same scripts (repurposed) |
| Instagram Main | @kairenofficial | Carousels, quote graphics, book promos |

**Topics:** Dopamine Detox, Stop Procrastinating, Beat Phone Addiction

---

### Marcus Voss — @marcusvoss
**Niche:** Discipline, stoicism, self-respect, mental toughness
**Audience:** Men 25–45, want structure and standards, tired of soft advice
**Avatar Style:** Strong, still presence — minimal movement, eye contact, no performance
**Posting Voice:** Low energy, high weight — every word matters, no hedging

| Platform | Handle | Content Type |
|----------|--------|-------------|
| TikTok | @marcusvoss | 30–60s talking head scripts |
| Instagram Reels | @marcusvoss | Same scripts + carousel posts |
| YouTube Shorts | @MarcusVoss | Same scripts (repurposed) |
| Instagram Main | @marcusvoss | Carousels, quote graphics, book promos |

**Topics:** The Discipline Blueprint

---

### Luna Hart — @lunahart
**Niche:** Relationships, attachment, boundaries, communication
**Audience:** Women 22–40, navigating modern relationships, pattern-aware
**Avatar Style:** Warm, natural — soft lighting, conversational setting, approachable
**Posting Voice:** Like a wise friend who sees the pattern you can't — warm but direct

| Platform | Handle | Content Type |
|----------|--------|-------------|
| TikTok | @lunahart | 30–60s talking head scripts |
| Instagram Reels | @lunahart | Same scripts + carousel posts |
| YouTube Shorts | @LunaHart | Same scripts (repurposed) |
| Instagram Main | @lunahart | Carousels, quote graphics, book promos |

**Topics:** The Confidence Code, How to Read People, The Charisma Blueprint

---

### Dr. Orion Hale — @dr.orionhale
**Niche:** Neuroscience, sleep, brain optimization, mental performance
**Audience:** Mixed 25–45, biohacker-curious, want science not hype
**Avatar Style:** Lab-casual — think science communicator, clean background, graphics-friendly
**Posting Voice:** Precise and explanatory — like a scientist who's also a great teacher

| Platform | Handle | Content Type |
|----------|--------|-------------|
| TikTok | @dr.orionhale | 30–60s talking head scripts |
| Instagram Reels | @dr.orionhale | Same scripts + carousel posts |
| YouTube Shorts | @DrOrionHale | Same scripts (repurposed) |
| Instagram Main | @dr.orionhale | Carousels, quote graphics, book promos |

**Topics:** Optimize Your Sleep, Clear Brain Fog, The Attention Protocol

---

## HeyGen Integration — Video Production Workflow

### Step 1: Create Avatars (One-Time Setup)

Each faculty member needs a HeyGen avatar:

| Faculty | Avatar Type | Look | Voice Style |
|---------|------------|------|-------------|
| Dr. Nova Vale | Photo Avatar or Studio Avatar | Professional woman, 30s, warm | Calm, measured, slightly clinical |
| Kai Ren | Photo Avatar or Studio Avatar | Sharp-looking man, late 20s, clean | Fast, confident, direct |
| Marcus Voss | Photo Avatar or Studio Avatar | Strong man, 35–40, commanding | Low, deliberate, no rush |
| Luna Hart | Photo Avatar or Studio Avatar | Approachable woman, late 20s | Warm, conversational, knowing |
| Dr. Orion Hale | Photo Avatar or Studio Avatar | Professional man, 40s, scholarly | Precise, curious, grounded |

**Recommended:** Use HeyGen's **Instant Avatar** (upload a photo + clone voice) or **Studio Avatar** (higher quality, filmed reference video).

### Step 2: Script-to-Video Pipeline

```
Pipeline outputs scripts (04_shorts_scripts_*.md)
        ↓
Parse individual scripts from batch file
        ↓
Feed each script into HeyGen API
        ↓
   - Set avatar (faculty-specific)
   - Set voice (faculty-specific)
   - Add text overlays (from VISUAL DIRECTION notes)
   - Set background (faculty-specific)
        ↓
Export MP4 files (720x1280 vertical)
        ↓
Add captions via CapCut / HeyGen built-in
        ↓
Upload to TikTok / Reels / Shorts
```

### Step 3: HeyGen API Integration (Future Script)

```python
# Future: scripts/heygen_producer.py
# Reads parsed scripts, sends to HeyGen API, downloads videos

# HeyGen API endpoints:
# POST /v2/video/generate  — create video from script + avatar
# GET  /v1/video_status.get — check generation status
# GET  /v1/video/download  — download finished video

# Input: scripts/output/{topic}/04_shorts_scripts_*.md
# Output: videos/{topic}/script_01.mp4 ... script_20.mp4
```

### Batch Video Production Per Topic

Each topic produces **20 scripts** → **20 videos** → posted across **3 platforms** = **60 posts per topic**

For 11 topics: **660 total video posts** across all faculty accounts.

---

## Link-in-Bio Funnel — Per Faculty Member

Each faculty member has ONE link-in-bio page (Linktree, Stan Store, or custom) that houses ALL their topic funnels.

### Structure

```
@dr.novavale link in bio
    ↓
[Nova Vale's Hub Page]
    ├── Free: "The Overthinking Pattern Decoder" (lead magnet)
    ├── Free: "The Anxiety Response Toolkit" (lead magnet)
    ├── Free: "The Rebirth Starter Kit" (lead magnet)
    ├── $17: "Stop Overthinking" (book)
    ├── $17: "Stop Negative Thoughts" (book)
    ├── $17: "Beat Anxiety Fast" (book)
    └── $17: "The Rebirth Blueprint" (book)
```

### Funnel Flow Per Topic

```
TikTok/Reel/Short (30–60s video)
    ↓ "Link in bio"
Landing Page (lead magnet opt-in)
    ↓ Email captured
Thank You Page (immediate book offer — $17)
    ↓ Buy or skip
5-Email Welcome Sequence
    ↓ Email 3–4 introduces book
Book Purchase ($7–$27)
    ↓ Future upsells
Course / Coaching (higher ticket — future)
```

### Revenue Model Per Faculty Member

| Stage | Product | Price | Conv. Rate (est.) |
|-------|---------|-------|-------------------|
| Lead Magnet | Free guide/checklist | $0 | 15–25% of viewers |
| Book | Digital book | $7–$27 | 3–8% of leads |
| Course (future) | Full course | $47–$197 | 2–5% of book buyers |
| Coaching (future) | Group/1:1 | $497+ | 1–2% of course buyers |

---

## Content Calendar — Posting Strategy

### Per Faculty Account: Daily Posting Cadence

| Day | Content Type | Source |
|-----|-------------|--------|
| Mon | Hook-led script (video) | Scripts 1–5 from batch |
| Tue | Quote graphic (image) | Quote graphics from batch |
| Wed | Mechanism-led script (video) | Scripts 6–10 from batch |
| Thu | Carousel post (image) | Carousel concepts from batch |
| Fri | Counterintuitive-led script (video) | Scripts 11–15 from batch |
| Sat | Tool-led script (video) | Scripts 16–20 from batch |
| Sun | Repost best performer / story engagement | Analytics-driven |

### Content Rotation Per Topic

Each topic generates **20 videos + 10 quote graphics + 5 carousels = 35 pieces of content**

At 1 video/day, each topic provides **~5 weeks of daily content** per platform.

With 3–4 topics per faculty member: **15–20 weeks of content** = ~4–5 months before needing new topics.

### Cross-Platform Repurposing

Every video is posted to all 3 platforms (TikTok, Reels, Shorts) with:
- Same video file (720x1280)
- Platform-specific caption (hook + hashtags)
- Same CTA ("link in bio")

**Total content per faculty member per topic:**
- 20 videos × 3 platforms = 60 video posts
- 10 quote graphics × 2 platforms (IG + TikTok) = 20 image posts
- 5 carousels × 1 platform (IG) = 5 carousel posts
- **= 85 pieces of content per topic**

---

## Google Ads — Parallel Acquisition Channel

Each topic's funnel copy includes Google Ads (generated by Funnel Agent).

### Structure Per Faculty
- **Search Ads** — target topic keywords ("how to stop overthinking", "dopamine detox guide")
- **Display Ads** — retarget landing page visitors who didn't opt in
- **Budget:** Start at $10–$20/day per topic, scale winners

### Ad → Funnel Flow
```
Google Search Ad
    ↓
Landing Page (same as link-in-bio funnel)
    ↓
Lead Magnet → Email Sequence → Book Offer
```

---

## Production Workflow — End to End

### Per Topic (Weekly Cycle)

```
MONDAY
  └── Run NeuroForge pipeline (--mode full)
      └── Generates: research brief, blueprint, chapter 1, 20 scripts, funnel copy

TUESDAY
  └── Review QA scores
      └── If any agent < 42/60: fix and re-run that stage
      └── If all > 42: proceed

WEDNESDAY
  └── Feed 20 scripts to HeyGen
      └── Generate 20 videos with faculty avatar
      └── Add captions (CapCut or HeyGen)

THURSDAY
  └── Set up funnel
      └── Landing page (lead magnet)
      └── Thank you page (book offer)
      └── Email sequence (5 emails in ESP)
      └── Link-in-bio update

FRIDAY
  └── Schedule 3 weeks of posts
      └── TikTok: schedule via TikTok Studio or Later
      └── Instagram: schedule via Meta Business Suite
      └── YouTube: schedule via YouTube Studio

WEEKEND
  └── Launch Google Ads for the topic
  └── Monitor first 48h of social posts
```

### Monthly Cadence (4 Topics/Month)

| Week | Topic | Faculty | Videos | Funnel |
|------|-------|---------|--------|--------|
| 1 | Topic A | Faculty X | 20 | Live |
| 2 | Topic B | Faculty Y | 20 | Live |
| 3 | Topic C | Faculty Z | 20 | Live |
| 4 | Topic D | Faculty W | 20 | Live |
| — | Run optimizer | All | — | — |

---

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Content Generation | NeuroForge OS (Claude API) | Scripts, books, funnels |
| Video Production | HeyGen | AI avatar videos |
| Captions | CapCut / HeyGen | Auto-caption for social |
| Social Scheduling | Later / Meta Business Suite / TikTok Studio | Cross-platform posting |
| Link-in-Bio | Stan Store / Linktree / Beacons | Hub for all offers |
| Email | ConvertKit / Beehiiv / MailerLite | Welcome sequences |
| Landing Pages | Carrd / Stan Store / Systeme.io | Lead magnet + book offer |
| Book Delivery | Gumroad / Payhip / Stan Store | Digital book sales |
| Ads | Google Ads + Meta Ads | Paid acquisition |
| Analytics | TikTok Analytics + IG Insights + GA4 | Performance tracking |

---

## KPIs to Track

### Per Faculty Account (Monthly)

| Metric | Target |
|--------|--------|
| Followers growth | +5,000/month minimum |
| Avg views per video | 10,000+ |
| Link-in-bio clicks | 3–5% of views |
| Email opt-in rate | 15–25% of clicks |
| Book purchase rate | 3–8% of leads |
| Revenue per topic/month | $500–$2,000 |

### Per Topic (Lifetime)

| Metric | Target |
|--------|--------|
| Total video views | 500,000+ |
| Email list adds | 2,000–5,000 |
| Book sales | 200–500 |
| Revenue | $3,000–$10,000 |

---

## Launch Order — Recommended

### Phase 1: Proof of Concept (Week 1–2)
1. Set up Dr. Nova Vale avatar in HeyGen
2. Create TikTok + IG accounts for @dr.novavale
3. Produce 20 videos from "Stop Overthinking" scripts
4. Set up landing page + email sequence + book offer
5. Post 2x/day for 2 weeks, measure results

### Phase 2: Scale to 3 Faculty (Week 3–6)
1. Set up Kai Ren + Luna Hart avatars
2. Create accounts for both
3. Run their first topics through video production
4. Launch 3 faculty posting simultaneously

### Phase 3: Full Fleet (Week 7–10)
1. Add Marcus Voss + Dr. Orion Hale
2. All 5 faculty posting daily
3. Launch Google Ads on best-performing topics
4. Run prompt optimizer based on QA data

### Phase 4: Scale (Month 3+)
1. Generate new topics beyond first 10
2. Produce full books (all chapters, not just Ch1)
3. Launch courses as upsells
4. A/B test funnels and ad creative
5. Scale ad spend on winning combos

---

## Immediate Next Steps

1. **Create HeyGen account** — sign up at heygen.com
2. **Build 5 avatars** — one per faculty member
3. **Register social accounts** — TikTok + IG for each faculty
4. **Set up Stan Store or Linktree** — one per faculty
5. **Set up email platform** — ConvertKit or Beehiiv
6. **Produce first 20 videos** — Dr. Nova Vale × Stop Overthinking
7. **Start posting** — 2x/day across TikTok + Reels + Shorts
