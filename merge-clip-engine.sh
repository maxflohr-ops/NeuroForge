#!/usr/bin/env bash
# merge-clip-engine.sh — lands the Florra OS Clip Engine into this project.
#
# The Clip Engine is the behind-the-scenes clipping machine for the Florra
# OS marketing stack: it ingests podcast/source clips, logs them to the Opus
# Airtable tables, and schedules them to TikTok / Instagram / YouTube via
# Postiz.
#
# Usage:
#   bash merge-clip-engine.sh           # lands in ./clip-engine/
#   bash merge-clip-engine.sh --root    # lands at the repo root
#
# It is idempotent: re-running updates the files in place without duplicating.
set -euo pipefail

# Resolve this script's real location (works via symlink / any CWD).
SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET="${1:-}"
if [[ "$TARGET" == "--root" ]]; then
    DEST="$(pwd)"
    DEST_CLIP="$DEST/clip-engine"
    echo "→ Landing Clip Engine at repo root: $DEST"
else
    DEST="$(pwd)/clip-engine"
    DEST_CLIP="$DEST"
    echo "→ Landing Clip Engine in: $DEST"
fi

# The engine source lives alongside this script (in the NeuroForge repo).
SRC_ENGINE="$SCRIPT_SRC/clip-engine"
if [[ ! -d "$SRC_ENGINE" ]]; then
    echo "Error: clip-engine/ not found next to this script ($SCRIPT_SRC)" >&2
    exit 1
fi

mkdir -p "$DEST_CLIP"
cp "$SRC_ENGINE"/clip_engine.py "$DEST_CLIP/clip_engine.py"
chmod +x "$DEST_CLIP/clip_engine.py" 2>/dev/null || true

# Keep a clips/ workspace for downloaded MP4s.
mkdir -p "$DEST_CLIP/clips"

echo "✓ Clip Engine merged to: $DEST_CLIP"
echo ""
echo "Next steps:"
echo "  1. Export API keys:  POSTIZ_API_KEY, AIRTABLE_API_KEY"
echo "  2. Ingest a clip:    python3 clip_engine.py --mode ingest --source <url-or-file> --title \"Clip title\""
echo "  3. Schedule:         python3 clip_engine.py --mode schedule --dry-run"
echo "  4. Live:             python3 clip_engine.py --mode schedule"
