#!/usr/bin/env bash
# ytgrab installer — puts `ytgrab` on your PATH and makes sure yt-dlp + ffmpeg
# are present. Safe to re-run; it doubles as an updater.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ytgrab.py"

say()  { printf '\033[36m::\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

MAC=false
[ "$(uname -s)" = "Darwin" ] && MAC=true

if ! command -v python3 >/dev/null; then
  if $MAC; then
    warn "python3 is missing — macOS installs it with the Xcode command line tools:"
    printf '\n    xcode-select --install\n\n'
  else
    warn "python3 is required"
  fi
  exit 1
fi

# Link into a directory that is already on PATH, so there is no shell-config
# step. Homebrew's bin is user-writable, which is the common case on macOS.
pick_bin_dir() {
  if [ -n "${YTGRAB_BIN_DIR:-}" ]; then echo "$YTGRAB_BIN_DIR"; return; fi
  for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    case ":$PATH:" in *":$d:"*) [ -w "$d" ] && { echo "$d"; return; } ;; esac
  done
  echo "$HOME/.local/bin"
}
BIN_DIR="$(pick_bin_dir)"
TARGET="$BIN_DIR/ytgrab"

# ---------------------------------------------------------------- yt-dlp ----
if $MAC && command -v brew >/dev/null; then
  say "installing yt-dlp + ffmpeg with Homebrew"
  brew install yt-dlp 2>/dev/null || brew upgrade yt-dlp || true
  brew install ffmpeg 2>/dev/null || true
elif command -v yt-dlp >/dev/null; then
  say "updating yt-dlp"
  yt-dlp -U >/dev/null 2>&1 || pip3 install -q -U "yt-dlp[default]" --break-system-packages 2>/dev/null \
    || pip3 install -q -U "yt-dlp[default]" --user
else
  say "installing yt-dlp"
  if command -v pipx >/dev/null; then
    pipx install "yt-dlp[default]" >/dev/null
  else
    pip3 install -q -U "yt-dlp[default]" --break-system-packages 2>/dev/null \
      || pip3 install -q -U "yt-dlp[default]" --user
  fi
fi
command -v yt-dlp >/dev/null || python3 -m yt_dlp --version >/dev/null 2>&1 \
  || { warn "yt-dlp install failed — try: pip3 install -U 'yt-dlp[default]'"; exit 1; }
ok "yt-dlp ready"

# ---------------------------------------------------------------- ffmpeg ----
# ffmpeg does the stream merging (anything above 720p), the audio extraction
# and the SponsorBlock cutting. Without it ytgrab still runs, but limited.
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
  ok "ffmpeg ready"
else
  say "installing ffmpeg"
  if   command -v brew    >/dev/null; then brew install ffmpeg
  elif command -v apt-get >/dev/null; then sudo apt-get update -qq && sudo apt-get install -y ffmpeg
  elif command -v dnf     >/dev/null; then sudo dnf install -y ffmpeg
  elif command -v pacman  >/dev/null; then sudo pacman -S --noconfirm ffmpeg
  elif command -v winget  >/dev/null; then winget install --id Gyan.FFmpeg -e
  elif $MAC; then
    warn "ffmpeg needs Homebrew on macOS. Install it, then re-run this script:"
    printf '\n    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n    brew install ffmpeg\n\n'
  else warn "install ffmpeg yourself: https://ffmpeg.org/download.html"
  fi
  command -v ffmpeg >/dev/null && ok "ffmpeg ready" || warn "ffmpeg still missing"
fi

# --------------------------------------------------------------- install ----
mkdir -p "$BIN_DIR"
ln -sf "$SRC" "$TARGET"
chmod +x "$SRC"
ok "installed $TARGET"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) RC="$HOME/.bashrc"
     [ "${SHELL##*/}" = zsh ] && RC="$HOME/.zshrc"
     warn "$BIN_DIR is not on your PATH — run this once:"
     printf '\n    echo '"'"'export PATH="%s:$PATH"'"'"' >> %s && source %s\n\n' \
       "$BIN_DIR" "$RC" "$RC" ;;
esac

printf '\nRun \033[1mytgrab\033[0m for the interactive terminal, or:\n'
printf '  ytgrab "https://www.youtube.com/watch?v=..."\n\n'
