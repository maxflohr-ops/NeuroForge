# legacy — the v1 prototype

What lives here is the first NeuroForge content pipeline, kept because it still
works and does things the current system does not. It is not maintained.

## `neuroforge_pipeline_v1.py`

Standalone script, was at the repo root. "NeuroForge — AI Educational Content
Pipeline": takes a topic and a faculty member and produces a course outline,
lecture script, notes, a quiz, and a faculty bio, in one pass against the
Anthropic API.

```bash
python legacy/neuroforge_pipeline_v1.py --topic "Stop Overthinking" --faculty "Dr. Nova Vale"
```

Last touched 2026-03-15 01:48 UTC.

## `output_v1/`

The only run it ever produced — `stop_overthinking`, with `outline.json`,
`outline.md`, `lecture_script.md`, `quiz.json` and `faculty_bio.md`.

## Why it was moved, not deleted

It shared a filename with `neuroforge-os/scripts/neuroforge_pipeline.py`, which
is a completely different program — the six-agent production orchestrator, last
touched seven hours later the same day and still in use. Two files with one name
doing two jobs is how the wrong one gets edited.

The v1 script is not superseded in features: quiz generation and faculty bios
have no equivalent in the OS pipeline or in `neuroforge-agent`. If either is
wanted again, take it from here rather than rewriting it.

## Also removed in this pass

`NeuroForge_OS.zip` — a 2026-03-14 snapshot of `neuroforge-os/`. Eight of its ten
files were byte-identical to the live tree and the other two were older versions
of files that have since grown. It remains in git history if it is ever needed.
