# SocialAppFarm — Distribution Playbook

SocialAppFarm (SAF, https://socialappfarm.com/app/dashboard) is now the
distribution layer for the NeuroForge / Florra clip pipeline. It replaces
the API schedulers (Postiz, Later, Meta Business Suite) with cloud Android
devices that post, like, comment and follow through the real app UI.

This doc is the repeatable run-book. Source: SAF's own how-to blog posts
(the app itself is a JS single-page app with no public API docs). Anything
marked **[verify in dashboard]** was not confirmable from outside a login.

```
Clip Engine (MP4 + caption)  →  SAF Content Queue  →  Campaign schedule "Create Post"
                                  ↑ approve first            ↑ per faculty / per device
```

---

## 1. Mental model (learn this once)

| SAF object | What it is | Our equivalent |
|---|---|---|
| **Device** | A cloud Android phone with its own fingerprint. Primary account + up to 25 extra accounts via add-on. | One faculty brand (or one mother + its child accounts) |
| **Proxy** | HTTP/SOCKS5 proxy, tagged. 1 proxy per 1–3 accounts, max 4. | Buy 4G/5G mobile first, ISP/residential second |
| **Project** | Top-level container. Only the *active* project (green checkmark) receives new campaigns. | One project per brand: NeuroForge, Florra, Opus |
| **Campaign** | Platform-specific (TikTok / Instagram / YouTube / Reddit). Binds a device + accounts + a Content Queue + a Schedule. | One campaign per faculty account per platform |
| **Content Queue** | Typed bucket (Video / Image / Audio / Text) that "Create Post" pulls from. Can require approval before use. | Where clip-engine output lands |
| **Niche Targeting** | Keywords, usernames, and AI prompts that steer likes/comments. Assigned per account. | The faculty's topic lane (see MARKETING_OPS.md) |
| **Schedule** | Hour-by-day grid of activities (View FYP, Search Tags, Create Post, …) with action counts. | Priming week, then Normal week |
| **Editor Pipeline** | Filter chain (noise, zoom, HSV shift, overlay text/video, stack, vintage…) applied to queue items on the way out. | Per-platform variants + CTA overlay |
| **Text Style** | Caption look (position, color, Karaoke highlight, box/full background). | Match our clip caption style |
| **Streams & Comments** | Watch keywords/users/FYP, AI-draft comments, approve, auto-post from accounts. | Comment marketing on competitor + niche posts |

Rule of thumb from SAF: **leave at least 10 × (accounts on the device) minutes
between schedule blocks.** 10 accounts → 100 min gaps.

---

## 2. First-time setup (once per brand)

Menu paths are verbatim from SAF.

1. **Storage** — `Technical → Data Backup → Connect Google Drive` (or
   Cloudflare R2 / iDrive E2 / S3). Required so multiple accounts can share one device.
2. **Proxies** — `Proxy → Proxy → Add New` (Host, Port, Username, Password,
   Tag, Proxy Type, optional Proxy Change URL) or `Import` a `.txt`:
   ```
   username:password:IP:port:tag
   ```
   Use one tag per brand (e.g. `neuroforge`, `florra`).
3. **Project** — `Projects → Projects → Add New` → Name, Description → Save →
   click the green checkmark to activate. **Only one project is active at a
   time; activate the right one before creating campaigns.**
4. **Device** — `Devices → Build New Device` → pick platform → Generate Device.
   Add-ons seen in SAF's own guide: "TikTok & Instagram Full Automation + Post
   Scheduler" and "Manage up to 25 Extra Accounts". **[verify in dashboard]**
   current add-on names and prices under `My Account → Subscription Plans`.
5. **Campaign** — `TikTok → Campaign → Add New` (same for Instagram / YouTube):
   Name, Share Device, Content Queue → Save.
6. **Accounts** — from the campaign: `View Accounts → Import`, CSV/TXT:
   ```
   username:password:email:emailpassword:biolink:bio:2fakey
   ```
   Only `username` is mandatory; password enables auto-login; `2fakey` is the
   TOTP secret. Then `Accounts → Auto Assign by Proxy Tag` → enter the tag.
7. **Log in** — from the **campaign page** (not the device list) click
   `Connect Device` → `Start App` → log in. Cycle accounts with
   `"+" icon → User Menu → Switch Device Campaign Account`.
8. **Niche** — `Projects → Niche Targeting → Add New`: Name, Content Queue,
   Keywords (comma-separated), Usernames, ✅ Use AI to Determine Interaction +
   prompt, ✅ Use AI to Generate Comment + prompt. Assign with
   `Campaign → View Accounts → select → Action → Update Account → Set Niche`.

---

## 3. Content in (the part we automate)

1. `Content Queue → Add New` → Name (e.g. `NF_Dr_Reyes_Videos`), type Video,
   ✅ **Approve Content Before Use**, optional Editor Pipeline → Save.
2. Upload: `View → View Content → + Upload`. Each item has a name and a
   description; on Reddit these become title and body, so treat **name = hook /
   title, description = caption + hashtags** on the video platforms.
   **[verify in dashboard]** whether TikTok/IG captions come from the item
   description or a campaign-level template, and whether the scheduler picks
   oldest-first or random and retires used items.
3. Approve items in `Content Queue → [queue] → View Content` before the
   evening "Create Post" slot.

Ways to get clips in without hand-uploading (no public API exists):
- **Chrome extension** "SocialAppFarm TikTok and Instagram Downloader" adds a
  Save button on TikTok/IG that uploads straight into your SAF account.
- **Scraper** `Scraper → Scraper (Headless) → Scrape Content` pulls a user's
  latest posts into a queue (TikTok / Instagram / YouTube). Point it at our
  own mother account to fan out clips to child accounts.
- **Bulk upload from the clip-engine output folder** is the honest default:
  `clip-engine/clips/` → drag into the queue once per posting day.

Editor Pipelines worth one per platform (`Content Editor → Editor Pipelines → New`):
- `nf_tiktok`: Zooming (1–3%), Noise Addition, HSV Shift, Overlay Text
  ("Full book in bio 👇", #000000, size 13, Bottom Center).
- `nf_reels`: same, plus Join Video with a 2-second faculty bumper.
- `nf_shorts`: Stack Video / Overlay Image with channel watermark.
Distinct pipelines keep the three uploads from being byte-identical.

---

## 4. Schedules (copy these)

`Campaign → View Schedule → click a time slot`. Build once, then
`Clear Schedule → Load Normal Schedule` after priming.

**Priming — first 5–7 days on any new or moved account**

| Time | Activity | Action |
|---|---|---|
| 8 AM | Search Tags | Like 5–10 |
| 12 PM | Search Video | Comment 1–3 |
| 4 PM | View Profile Stats | sync |
| 8 PM | View FYP | Like 5–10, Comment 2–5 |
| 1 AM | View FYP | Like 5–10 |

**Normal — faculty (mother) account**

| Time | Activity | Action |
|---|---|---|
| 8 AM | View FYP | Like 15–20, Follow 5–10 |
| 12 PM | Create Post | from queue |
| 4 PM | View Profile Stats | sync |
| 8 PM | Create Post | from queue |
| 1 AM | View FYP | Comment 5–10 |

**Aggressive — child accounts only** (set "Run Schedule For Only Niche Account"
to the child niche)

| Time | Activity | Action |
|---|---|---|
| 7 AM | Search Tags | Like 10 |
| 11 AM | Search Users | Follow 10–15 |
| 2 PM | Create Post | 1 reposted clip |
| 4 PM | Search Tags | Comment 2–4 |
| 7 PM | Search Users | Unfollow 10–20 |
| 9 PM | Search Account | Like latest 3 of @mother |
| 10 PM | Update Profile Stats | sync |

Caps SAF publishes: Follow 30–60/day, Unfollow 20–30/day.
Structure SAF recommends: TikTok 10 child → 1 main; Instagram 5–20 child → 1 mother.

---

## 5. The run (what "doing it again" looks like)

Day 0
- [ ] Right project active. Device + proxies healthy (`Proxy` page shows no failures).
- [ ] Queues exist per faculty, approval on, pipeline attached.
- [ ] Accounts logged in from the campaign page; niche set on every account.

Every posting day (Mon / Wed / Fri per MARKETING_OPS.md)
- [ ] Run `clip_engine.py --mode ingest` → clips in `clip-engine/clips/`.
- [ ] Upload the day's clips to each faculty queue; name = hook, description = caption + tags.
- [ ] Approve before the 12 PM and 8 PM Create Post slots.
- [ ] Log performance back to Airtable (Opus Clips) after the 4 PM stats sync.

Weekly
- [ ] `Update Profile Stats` numbers → Airtable. Kill the bottom clip format, double the top.
- [ ] Any account that fails on a proxy twice → replace the proxy, not the account.
- [ ] New accounts → priming schedule for 5–7 days before they touch Create Post.

Non-negotiable: TikTok posts still carry the AI-made label. SAF's pipelines
disguise duplication, not authorship.

---

## 6. Open questions to close inside the dashboard

1. Exact plan and add-on pricing (`My Account → Subscription Plans`).
2. YouTube campaign specifics: Shorts vs long, title field, whether the same
   queue can feed all three platforms or needs one queue per platform.
3. Caption source for TikTok/IG (item description vs campaign template) and
   queue pick order / reuse behavior.
4. Whether `Technical → Data Backup` S3 storage can be used for content ingest
   or only account backup. If ingest works, the clip engine can write to S3 and
   skip manual uploads.
5. Analytics export: is there a CSV under Profile Stats we can feed Airtable?

Sources: SAF blog posts "How To Setup And Create Your Social Media Automation
Project & Campaign", "Advanced Large Scale: Building And Automating Your
TikTok And Instagram Account With AI Support Running On Device Farm", "Quick
Traffic … Using Instagram & TikTok Reuploads", "How to Build and Automate an
Influencer Brand Account", "Creating Caption Styles & Effect".
