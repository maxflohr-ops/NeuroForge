# People — Person Profiles for Agents

The person layer of Florra OS. Every profile here is produced by Distilly
(`/distilly` in Claude Code, vendored at `.claude/skills/distilly/`) and is the
thing the pipeline agents read to write *as* someone rather than *about* them.

```
people/
  colleague/<slug>/      faculty personas and team members (built from brand docs)
  celebrity/<slug>/      roster talent researched from public material
  relationship/<slug>/   clients and partners we manage
```

Each profile is three files plus a `versions/` history:

| File | What it holds |
|------|---------------|
| `persona.md` | Layered voice: core character, identity, how they speak, how they decide |
| `work.md` | What they own, their standards, how they want work handed to them |
| `meta.json` | Name, slug, tags, sources, correction count, version |

## Create one

Run `/distilly` in Claude Code from the repo root and, when it writes files,
point it here with `--base-dir people/<family>`:

```bash
# faculty persona (fictional voice, built from the brand docs you supply)
python3 .claude/skills/distilly/tools/skill_writer.py --action create \
  --character colleague --base-dir people/colleague \
  --name "Dr. Nova Vale" --meta /tmp/meta.json --persona /tmp/persona.md --work /tmp/work.md

# roster talent (public material only)
python3 .claude/skills/distilly/tools/skill_writer.py --action list \
  --character celebrity --base-dir people/celebrity
```

`/distilly` handles the intake, analysis and writing itself. The commands above
are what it runs under the hood, so you can see where things land.

## Use one

The content pipeline looks a profile up by faculty name:

```bash
cd neuroforge-os
python scripts/neuroforge_pipeline.py --topic "Stop Overthinking" --faculty "Dr. Nova Vale" --mode full
#   → finds people/colleague/dr-nova-vale/ and injects persona.md into every agent
python scripts/neuroforge_pipeline.py --topic "..." --faculty "Kai Ren" --person kai-ren-v2
#   → explicit slug when the folder name differs from the faculty name
```

No profile found means the pipeline falls back to the three-line
`FACULTY_PROFILES` entry, exactly as before.

## Correct one

Tell `/distilly` "that's wrong, she wouldn't say that" and it patches the
profile and bumps the version. Roll back with
`python3 .claude/skills/distilly/tools/version_manager.py --action rollback --slug <slug> --base-dir people/<family> --version vN`.

## Rules

- Public material for public people. Private messages only with consent.
- `knowledge/` (raw source dumps) is git-ignored. Commit the distilled profile, not the evidence.
- Human review before a profile drives published content. Same rule as everything else here.
