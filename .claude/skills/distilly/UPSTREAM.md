# Distilly — vendored copy

Source: https://github.com/titanwings/distilly
Branch: `dot-skill` (the Claude Code "Legacy Skill" route — the only route
upstream marks as usable in Claude Code today)
Commit: `868c293f56116081733b78fc7db5f91634d7b62a` (2026-08-25)
License: MIT (see `LICENSE`)

What was kept: `SKILL.md`, `prompts/`, `tools/`, `references/`, `bin/`,
`requirements.txt`, `LICENSE`. Dropped: `docs/` (11 MB of images), `tests/`,
`.github/`, the three example Chinese colleague skills, README/INSTALL.

## How Florra OS uses it

`/distilly` distills a person's material into `persona.md` + `work.md` +
`meta.json`. In this repo those profiles live under `people/<family>/<slug>/`
and `neuroforge-os/scripts/neuroforge_pipeline.py` loads them as the voice
profile for a faculty member. See `people/README.md`.

## Refreshing from upstream

```bash
git clone --single-branch --branch dot-skill --depth 1 \
  https://github.com/titanwings/distilly.git /tmp/distilly
for item in SKILL.md prompts tools references bin requirements.txt LICENSE; do
  rm -rf .claude/skills/distilly/$item
  cp -r /tmp/distilly/$item .claude/skills/distilly/
done
git -C /tmp/distilly rev-parse HEAD   # update the commit above
```

## Boundaries

- Only feed it local files, pasted text, and public URLs. The Feishu, DingTalk
  and Slack auto-collectors write credentials to `~/.distilly/`; upstream marks
  them outside the reviewed security boundary. Don't run them from this repo.
- Raw source material lands in `knowledge/` and is git-ignored. Only the
  distilled profile is committed.
- Python deps: `requests` (already in the pipeline's requirements). Everything
  else in `requirements.txt` is optional.
