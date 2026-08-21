#!/bin/bash
# ytgrab macOS setup — one paste, start to finish.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/maxflohr-ops/NeuroForge/refs/heads/claude/youtube-video-downloader-f4qg1x/ytgrab/mac-setup.sh)"
#
# Handles the usual macOS snags: Homebrew missing, Homebrew installed but not
# on PATH (the Apple Silicon classic), and Command Line Tools not installed.
# Safe to re-run.

set -u

BASE="https://raw.githubusercontent.com/maxflohr-ops/NeuroForge/refs/heads/claude/youtube-video-downloader-f4qg1x/ytgrab"
RAW="$BASE/ytgrab.py"
SELF="$BASE/mac-setup.sh"

say()  { printf '\033[36m::\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "this script is for macOS — on Linux run ./install.sh"

printf '\n\033[1mytgrab setup\033[0m\n\n'

# ------------------------------------------------------------------ brew ----
# Homebrew installs to /opt/homebrew on Apple Silicon and /usr/local on Intel.
# Its installer prints a "Next steps" PATH command that is easy to miss, which
# is why `brew: command not found` is the #1 way this goes wrong.
#
# Everything below drives brew through an absolute path, so nothing depends on
# PATH being correct while we are still repairing PATH.
BREW=""
command -v brew >/dev/null 2>&1 && BREW="$(command -v brew)"

if [ -z "$BREW" ]; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$candidate" ] || continue
    say "Homebrew is installed but not on your PATH — fixing that"
    BREW="$candidate"
    LINE="eval \"\$($candidate shellenv)\""
    for rc in "$HOME/.zprofile" "$HOME/.bash_profile"; do
      [ -e "$rc" ] || [ "$rc" = "$HOME/.zprofile" ] || continue
      grep -qF "$candidate shellenv" "$rc" 2>/dev/null || echo "$LINE" >> "$rc"
    done
    ok "Homebrew on PATH (and saved for future terminals)"
    break
  done
fi

if [ -z "$BREW" ]; then
  # The Homebrew installer needs a real terminal to ask for your password.
  if [ ! -t 0 ]; then
    warn "Homebrew is not installed, and this script cannot install it when piped."
    printf '\nRun it this way instead (note the bash -c):\n\n'
    printf '    bash -c "$(curl -fsSL %s)"\n\n' "$SELF"
    exit 1
  fi
  say "installing Homebrew — this takes a few minutes and asks for your Mac password"
  printf '   %s\n\n' "(the password is invisible while you type it — that is normal)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || die "Homebrew install failed. Install it from https://brew.sh, then re-run this script."
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$candidate" ] && { BREW="$candidate"; break; }
  done
  [ -n "$BREW" ] || die "Homebrew installed but I cannot find it — restart Terminal and re-run this."
fi

# Make brew and everything it installs reachable for the rest of this script.
eval "$("$BREW" shellenv)" 2>/dev/null || true
export PATH="$(dirname "$BREW"):$("$BREW" --prefix)/bin:$PATH"
ok "Homebrew ready  ($BREW)"

# -------------------------------------------------------------- payloads ----
say "installing yt-dlp and ffmpeg (this is the slow part)"
"$BREW" install yt-dlp 2>/dev/null || "$BREW" upgrade yt-dlp 2>/dev/null || true
"$BREW" install ffmpeg 2>/dev/null || true
command -v yt-dlp  >/dev/null 2>&1 || die "yt-dlp did not install — try: brew install yt-dlp"
command -v ffmpeg  >/dev/null 2>&1 || warn "ffmpeg missing: you will be capped at 720p and sponsors will not be cut"
ok "yt-dlp $(yt-dlp --version 2>/dev/null)"

command -v python3 >/dev/null 2>&1 || {
  warn "python3 is missing. Install Apple's command line tools, then re-run this script:"
  printf '\n    xcode-select --install\n\n'
  exit 1
}

# --------------------------------------------------------------- ytgrab -----
TARGET="$("$BREW" --prefix)/bin/ytgrab"
say "installing ytgrab to $TARGET"
curl -fsSL "$RAW" -o "$TARGET" || die "could not download ytgrab — check your internet connection"
chmod +x "$TARGET"

"$TARGET" --version >/dev/null 2>&1 || die "ytgrab downloaded but will not run — paste this output to Claude"
ok "$("$TARGET" --version) installed"

printf '\n\033[1mDone.\033[0m Type this to start:\n\n    \033[36mytgrab\033[0m\n\n'
printf 'Then paste a YouTube link and press Enter.\n'
command -v ytgrab >/dev/null 2>&1 || printf '\n%s\n' "If 'ytgrab' is not found, close and reopen Terminal first."
printf '\n'
