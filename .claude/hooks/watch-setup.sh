#!/usr/bin/env bash
# SessionStart: make the /watch skill (.claude/skills/watch) usable in every session.
# Installs ffmpeg + yt-dlp when missing and points watch at Gemini when a
# GEMINI_API_KEY is present in the environment. The key itself is never written
# to disk here — set it as an environment secret and watch reads it from the env.
set -u

log() { echo "[watch-setup] $*" >&2; }

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    log "installing ffmpeg"
    apt-get install -y -qq ffmpeg >/dev/null 2>&1 \
      || { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq ffmpeg >/dev/null 2>&1; } \
      || log "ffmpeg install failed"
  else
    log "ffmpeg missing; install it with your package manager (brew install ffmpeg)"
  fi
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  log "installing yt-dlp"
  python3 -m pip install -q -U yt-dlp >/dev/null 2>&1 || log "yt-dlp install failed"
fi

CONFIG_DIR="$HOME/.config/watch"
CONFIG="$CONFIG_DIR/.env"
if [ ! -f "$CONFIG" ]; then
  mkdir -p "$CONFIG_DIR"
  if [ -n "${GEMINI_API_KEY:-}" ]; then engine=gemini; else engine=local; fi
  umask 077
  cat >"$CONFIG" <<EOF
# /watch configuration (written by NeuroForge .claude/hooks/watch-setup.sh).
# GEMINI_API_KEY comes from the environment; do not paste keys into this repo.
WATCH_ENGINE="$engine"
WATCH_DETAIL="balanced"
WATCH_WHISPER_BACKEND="none"
EOF
  log "watch configured (engine: $engine)"
fi

exit 0
