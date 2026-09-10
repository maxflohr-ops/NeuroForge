# Archify — vendored copy

Source: https://github.com/tt-a1i/archify (the `archify/` skill directory)
Commit: `18911058008f17dc065af23a2cdc9bfeff6d3f7a` (2026-09-10, v2.17.0-dev.1)
License: MIT (see `LICENSE`, `THIRD_PARTY_NOTICES.md`)

Dropped from upstream: `test/` and the rendered `examples/*.html`. Everything the
skill reads (SKILL.md, schemas, JSON examples, renderers, bin, scripts,
references, brand marks) is intact. Zero npm dependencies; needs Node 22+.

## How Florra OS uses it

`docs/maps/*.architecture.json` is the typed source. `/archify` in Claude Code
edits it; the CLI validates and delivers the HTML:

```bash
cd .claude/skills/archify
export ARCHIFY_UPDATE_CHECK_DISABLED=1
node bin/archify.mjs validate architecture ../../../docs/maps/florra-os.architecture.json --quality showcase --json
node bin/archify.mjs deliver  architecture ../../../docs/maps/florra-os.architecture.json ../../../docs/maps/florra-os.architecture.html --quality showcase --json
ARCHIFY_CHROME=$(command -v chromium || command -v google-chrome) node bin/archify.mjs visual-check ../../../docs/maps/florra-os.architecture.html --json
```

Showcase acceptance means 9 of 9 artifact checks, 0 composition errors, 0
warnings. A failed deliver keeps the previous HTML in place.

## Refreshing from upstream

```bash
git clone --depth 1 https://github.com/tt-a1i/archify.git /tmp/archify
rm -rf .claude/skills/archify && cp -r /tmp/archify/archify .claude/skills/archify
rm -rf .claude/skills/archify/test .claude/skills/archify/examples/*.html
git -C /tmp/archify rev-parse HEAD   # update the commit above; restore this file
```

## Boundaries

- The skill's update checker may GET a fixed manifest to show a reminder. It
  never downloads anything. `ARCHIFY_UPDATE_CHECK_DISABLED=1` turns it off.
- Diagrams show authored facts only. Archify does not inspect live infra and
  does not infer impact; keep the map honest about what is live vs built.
