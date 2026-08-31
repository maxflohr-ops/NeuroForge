# Ridge Club YouTube Archiver

Automated agent pipeline that mirrors the **Ridge Club house YouTube channel** into a
shared **Google Drive** for the clipping community, pushes every video through
**OpusClip** so the auto-generated clips land in Drive too, and posts the top clips
to **Instagram + Snapchat** via **Ayrshare**.

```
┌──────────────────┐     ┌──────────────┐     ┌───────────────────┐
│ Channel Watcher   │ ──▶ │  Downloader  │ ──▶ │  Drive Agent      │
│ (finds every      │     │  (yt-dlp,    │     │  01 Full Videos/  │
│  video, old + new)│     │  best quality)│    └───────┬───────────┘
└──────────────────┘     └──────────────┘             │
                                                       ▼
                                              ┌───────────────────┐
                                              │  Opus Agent       │
                                              │  submit → poll →  │
                                              │  download clips   │
                                              └───────┬───────────┘
                                                      ▼
                             ┌───────────────────┐   ┌───────────────────┐
                             │ Social Publisher  │ ◀─│  Drive Agent      │
                             │ (Ayrshare → IG +  │   │  02 Opus Clips/   │
                             │  Snapchat)        │   │    <video title>/ │
                             └───────────────────┘   └───────────────────┘
```

Every step is checkpointed in a local SQLite state DB (`state/archive.db`), so the
pipeline is safe to re-run at any time — it only ever does the work that hasn't been
done yet.

## Drive folder layout

Inside the shared "Ridge Club YouTube" Drive folder (the one shared with the clipping
community), the pipeline maintains:

```
Ridge Club YouTube/            ← you create + share this once, put its ID in .env
├── 01 Full Videos/            ← every full upload from the channel
│   └── 2026-08-10 - <video title> [<video id>].mp4
└── 02 Opus Clips/
    └── <video title> [<video id>]/
        ├── clip_01 - <clip title>.mp4
        ├── clip_02 - <clip title>.mp4
        └── ...
```

## Setup

### 1. Install dependencies

```bash
cd ridge-club-archiver
pip install -r requirements.txt
```

`ffmpeg` must be on PATH (yt-dlp uses it to merge audio+video):
`sudo apt install ffmpeg` or `brew install ffmpeg`.

### 2. Google Drive credentials (service account)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and
   enable the **Google Drive API**.
2. Create a **service account**, then create a JSON key for it and save it as
   `credentials/service_account.json`.
3. Share the "Ridge Club YouTube" Drive folder with the service account's email
   (`...@...iam.gserviceaccount.com`) as **Editor** — the same way you shared it with
   the clipping community.
4. Copy the folder ID from its URL (`https://drive.google.com/drive/folders/<THIS_PART>`)
   into `.env`.

> **Tip:** a folder on a **Shared Drive** is strongly recommended over My Drive.
> Service accounts have no storage quota of their own; on My Drive the uploads count
> against the folder owner's quota and can hit per-account limits. On a Shared Drive
> everything just works (the pipeline passes `supportsAllDrives` everywhere).

### 3. OpusClip API

The Opus agent uses the [OpusClip API](https://docs.opus.pro/). Grab an API key from
your OpusClip workspace (API access requires an eligible plan) and put it in `.env`.

If you don't have API access, run with `OPUS_ENABLED=false` — full videos still get
archived to Drive, and you can clip manually in the Opus UI. Since the pipeline records
each video's YouTube URL in the state DB, wiring Opus in later picks up where it left off.

### 4. Ayrshare (Instagram + Snapchat auto-posting)

The Ayrshare account already has IG and Snapchat linked, so the pipeline just needs the
API key: grab it from [Ayrshare → API Key](https://app.ayrshare.com/api-key) and set
`AYRSHARE_API_KEY` in `.env`. Posting turns on automatically once the key is present.

After each video's Opus clips are archived to Drive, the Social Publisher posts the
**top 3 clips** (Opus returns them ranked) to `instagram,snapchat` with the clip title
as caption. Tune with `AYRSHARE_MAX_CLIPS_PER_VIDEO` (0 = post every clip — careful
during a big backfill), `AYRSHARE_PLATFORMS`, and `AYRSHARE_CAPTION_SUFFIX`.

**X (Twitter) too:** X posting through Ayrshare is bring-your-own-keys. Grab the
**API Key (Consumer Key)** and **API Secret** from your X developer app ("Keys and
tokens" in the [X developer portal](https://developer.x.com)), put them in `.env` as
`X_TWITTER_OAUTH1_API_KEY` / `X_TWITTER_OAUTH1_API_SECRET`, and link the X account
once in the Ayrshare dashboard (Social Accounts → X, using those same keys). With the
keys set, `twitter` is automatically added to the default platform list — Ayrshare
never stores the keys; the pipeline sends them as headers on each request targeting X.

This repo also enables the [Ayrshare Claude plugin](https://github.com/ayrshare/ayrshare-social-media-api-claude-plugin)
(`.claude/settings.json`), so in Claude Code sessions you can manage posts, analytics,
comments, and scheduling conversationally with the same key — run `/ayrshare:setup` once.

**Community member onboarding (Business plan):** the Ayrshare Business integration
package provides a domain (`id-4-GaO`) and a private key for SSO. Drop the key at
`credentials/ayrshare-private.key`, set `AYRSHARE_DOMAIN` in `.env`, then:

```bash
python run.py profiles create --title "Jay - Clipper"   # prints their Profile Key (save it!)
python run.py profiles sso --profile-key <key>          # prints a social-linking URL
python run.py profiles list
```

Send the SSO link to the member (it expires in ~5 minutes — generate it when they're
ready). They connect their own IG/TikTok/etc. on the branded Ayrshare page, no passwords
shared.

**Fan-out distribution:** to turn the community into a distribution network, list the
profiles in `AYRSHARE_PROFILE_KEYS` — every clip then goes out through *each* profile's
accounts. `primary` means the house accounts:

```bash
AYRSHARE_PROFILE_KEYS=primary,MEMBER1-PROFILE-KEY,MEMBER2-PROFILE-KEY
```

Each clip is uploaded once and posted per profile, restricted to the platforms that
profile actually linked (a member who only connected IG won't error on Snapchat).
One member's failure doesn't block the others. `AYRSHARE_PROFILE_KEY` (singular)
still works for posting via exactly one profile.

### 5. Configure

```bash
cp .env.example .env
# edit .env — channel URL, Drive folder ID, Opus key
```

## Running

```bash
# One-time historical backfill: archive EVERY video ever uploaded to the channel
python run.py backfill

# Continuous mode: poll for new uploads every 15 min and process them end-to-end
python run.py watch

# Process a single video (re-runs are safe — completed steps are skipped)
python run.py process --url https://www.youtube.com/watch?v=VIDEO_ID

# Show pipeline status for all known videos
python run.py status
```

### Keeping it running

Cron (every 15 minutes, one pass per invocation):

```cron
*/15 * * * * cd /path/to/ridge-club-archiver && /usr/bin/python3 run.py watch --once >> logs/archiver.log 2>&1
```

Or Docker:

```bash
docker build -t ridge-club-archiver .
docker run -d --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials \
  -v $(pwd)/state:/app/state \
  ridge-club-archiver
```

## Configuration reference (.env)

| Variable | Required | Description |
|---|---|---|
| `YOUTUBE_CHANNEL_URL` | ✅ | Ridge Club channel URL (`https://www.youtube.com/@RidgeClub`) |
| `DRIVE_ROOT_FOLDER_ID` | ✅ | ID of the shared "Ridge Club YouTube" Drive folder |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | | Path to the service-account JSON key (default `credentials/service_account.json`) |
| `OPUS_ENABLED` | | `true`/`false` — toggle the OpusClip stage (default `true`) |
| `OPUS_API_KEY` | if Opus on | OpusClip API key |
| `OPUS_API_BASE` | | Override the OpusClip API base URL (default `https://api.opus.pro/api`) |
| `AYRSHARE_API_KEY` | for posting | Ayrshare API key (IG + Snapchat linked account) |
| `AYRSHARE_ENABLED` | | Defaults to `true` when the key is set; `false` pauses posting |
| `AYRSHARE_PLATFORMS` | | Comma list of platforms (default `instagram,snapchat`, `+twitter` when X keys set) |
| `X_TWITTER_OAUTH1_API_KEY` | for X | Consumer Key from your X developer app |
| `X_TWITTER_OAUTH1_API_SECRET` | for X | Consumer Secret from your X developer app |
| `AYRSHARE_MAX_CLIPS_PER_VIDEO` | | Top N clips posted per video, `0` = all (default `3`) |
| `AYRSHARE_CAPTION_SUFFIX` | | Text appended to every caption, e.g. `#RidgeClub` |
| `AYRSHARE_PROFILE_KEY` | | Post via a specific member profile instead of the primary |
| `AYRSHARE_PROFILE_KEYS` | | Fan-out list of profiles to post through (`primary` = house) |
| `AYRSHARE_DOMAIN` | for SSO | Business SSO domain from the integration package (`id-4-GaO`) |
| `AYRSHARE_PRIVATE_KEY_FILE` | | Path to the Business private key (default `credentials/ayrshare-private.key`) |
| `DOWNLOAD_DIR` | | Local scratch dir for downloads (default `downloads/`, cleaned after upload) |
| `WATCH_INTERVAL_MINUTES` | | Poll interval in `watch` mode (default `15`) |
| `MAX_VIDEO_HEIGHT` | | Cap download resolution, e.g. `1080` (default: best available) |
| `KEEP_LOCAL_FILES` | | `true` to keep local copies after upload (default `false`) |

## Notes

- **Idempotent by design.** The state DB tracks each video through
  `discovered → downloaded → uploaded → clipping → clips_uploaded → done`. Crash or
  kill it at any point and the next run resumes exactly where it stopped.
- **Members-only / private videos**: yt-dlp can only fetch what the account it runs as
  can see. For members-only content, export cookies from a logged-in browser session and
  set `YTDLP_COOKIES_FILE` in `.env`.
- **"Sign in to confirm you're not a bot"**: YouTube challenges downloads from many
  datacenter/cloud IPs (channel scanning still works; only the media download is
  blocked). Fix: export YouTube cookies from a logged-in browser
  ([how-to](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies))
  and set `YTDLP_COOKIES_FILE=credentials/cookies.txt`. Residential/home IPs usually
  don't hit this.
- This is built for archiving **Ridge Club's own channel** for its own clipping
  community — keep it pointed at content you have the rights to redistribute.
