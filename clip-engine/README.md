# Florra OS — Clip Engine

The behind-the-scenes clipping machine for the Florra marketing stack.

It ingests podcast/source audio, turns it into platform-ready short clips, logs
every clip to the Opus Airtable tables, and schedules the finished MP4s to
**TikTok / Instagram / YouTube** via Postiz. It is the "clip" layer of the
Florra OS marketing firepower: NeuroForge writes the books and scripts, Florra
finds the creators, and the Clip Engine keeps the clip pipeline fed and
published.

```
Podcast (Auto Clip = Yes)
  → ingest clip (local file or URL)
  → logged to Airtable (Opus Clips)
  → scheduled via Postiz (TikTok / IG / YouTube, Mon/Wed/Fri)
  → performance can be logged back to Airtable
```

## Layout

```
clip-engine/
  clip_engine.py    ← the engine (ingest + schedule)
  clips/            ← downloaded/generated MP4s (gitignored)
  manifest.json     ← local log of clips (gitignored)
```

## Usage

```bash
# 1. Ingest a clip (local file or URL)
python3 clip_engine.py --mode ingest \
  --source "/path/to/episode.mp3" \
  --title "The 3-minute rule that stops overthinking" \
  --project "Overthinking Podcast"

# 2. Preview what would be scheduled (no API calls)
python3 clip_engine.py --mode schedule --dry-run

# 3. Schedule for real
python3 clip_engine.py --mode schedule \
  --platforms tiktok,instagram,youtube \
  --start-date 2026-09-07 \
  --interval-days 2
```

## Env

| Variable | Required | Purpose |
|----------|----------|---------|
| `POSTIZ_API_KEY` | yes (to post) | Postiz API key (Settings → API keys) |
| `POSTIZ_BASE_URL` | no | `https://api.postiz.com/public/v1` (default) or your self-hosted URL |
| `POSTIZ_INTEGRATION_IDS` | no | JSON `{"tiktok": "...", "youtube": "..."}` to pin channels |
| `AIRTABLE_API_KEY` | optional | Logs clips to the Opus Airtable tables |

Copy these from `../neuroforge-os/.env.example`.

## Merging into a project

The `merge-clip-engine.sh` script at the repo root lands this engine anywhere:

```bash
bash merge-clip-engine.sh          # → ./clip-engine/
bash merge-clip-engine.sh --root   # → repo root/clip-engine/
```

Idempotent — safe to re-run.

## Notes

- Clips are scheduled on **Mon / Wed / Fri** (the video days used across the
  NeuroForge marketing calendar).
- TikTok posts are labeled `video_made_with_ai: true` — honest AI labeling is
  non-negotiable (see NeuroForge's Non-Negotiables).
- All generated media and the manifest are gitignored; only the engine code is
  committed.
