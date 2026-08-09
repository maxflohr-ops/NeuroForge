---
name: estate-browser
description: Interact with live websites from an agent session with zero dependencies — fetch and read pages, check deployed endpoints and JSON APIs, or drive a real headless Chromium (open pages, snapshot them as text with clickable refs, click, fill forms, screenshot, run page JS). Use whenever a task needs to reach or verify a live site - checking the Bandersnatch store or the front-desk chat, testing a deployed page, extracting content, filling a form, or capturing a screenshot. Two paths: a dependency-free fetch path that works anywhere, and a full Chromium path where outbound egress allows it.
license: MIT
metadata:
  version: "1.1"
  based_on: citrolabs/ego-lite ego-browser (MIT) — helper-runtime and snapshot-ref patterns, reimplemented as dependency-free CDP + fetch for headless Linux
---

# estate-browser

Run everything through a heredoc — the body executes as async JavaScript with
all helpers preloaded:

```bash
node .claude/skills/estate-browser/runtime/browse.mjs <<'EOF'
const r = await fetch('https://example.com/health')
log(r.status + ': ' + r.body)
EOF
```

## Two paths

**Fetch path (works anywhere)** — `fetch()` and `textOf()` make HTTP requests
through the environment's proxy and parse the result. No browser, no
rendering. Use for health checks, JSON APIs, static HTML, and reading pages
that don't need JavaScript. This is the reliable default.

**Browser path (where egress allows)** — `open()`, `snapshotText()`,
`click()`, etc. drive a real headless Chromium via CDP for pages that need
rendering or interaction. The runtime launches Chromium only when the script
calls a browser helper. Note: some locked-down sandboxes reset Chromium's
proxied TLS even when `fetch()` works — if `open()` returns
`ERR_CONNECTION_RESET`, fall back to the fetch path here and run the browser
path on a normal host (Railway, a laptop) instead.

```bash
node .claude/skills/estate-browser/runtime/browse.mjs <<'EOF'
await open('https://example.com')
log(await snapshotText())
await shot('example.png')
EOF
```

The Chromium daemon **persists between heredoc rounds** (profile under
`~/.estate-browser`), so cookies, logins, and tabs carry across rounds.
Each round reconnects automatically; call `await shutdown()` in your final
round when the task is done.

## Working loop

1. `open(url)` — navigate (reuses the current tab; `{newTab: true}` for another).
2. `snapshotText()` — read the page: title/url, a numbered list of
   interactive elements (`[@N] <button> send`), and the page text. Observe
   before acting; re-snapshot after anything that changes the page.
3. Act: `click('@N')` or `click('css selector')` or `click([x, y])`,
   `fill('@N', 'text')`, `press('Enter')`, `scroll(800)`.
4. Verify: `snapshotText()` again, or `shot('name.png')` for a screenshot
   (prints the saved path — send it to the user with SendUserFile when it is
   the deliverable).

## Helpers

Fetch path (no browser):
- `fetch(url, {method, headers, body, maxBytes})` — returns `{status, body}`;
  `body` may be a string or object (auto-JSON). Honors the environment proxy.
- `textOf(html)` — strip an HTML document to readable text
- `log(...)` — the only output channel; all findings must go through it

Browser path:
- `open(url, {newTab, timeout})` · `pageInfo()` · `tabs()` · `switchTab(id)` · `closeTab(id?)`
- `snapshotText({maxChars})` — text-first observation with `@N` refs
- `click(target)` · `fill(target, text)` · `press(key)` · `scroll(dy)`
- `waitFor(selectorOrMs, {timeout})` — selector presence or plain sleep
- `js(expression)` — evaluate in the page, awaits promises, returns by value
- `shot(name?)` — PNG screenshot, returns the file path
- `shutdown()` — close the browser daemon (final round only)

## Rules

- Snapshot before you click: never guess refs or selectors blind.
- `@N` refs are only valid against the **latest** snapshot of the current
  page — re-snapshot after navigation or DOM changes.
- Keep rounds small: one navigation + a few actions per heredoc, then read
  the output and decide the next round.
- Close scratch tabs as you go; finish tasks with `shutdown()` unless the
  next round clearly continues the same job.
- If a login wall or captcha appears, stop and tell the user what is needed
  — do not attempt to bypass it.
- This drives a real shared profile: do not visit sites or submit data the
  user did not ask for.

## Environment notes

- Chromium is auto-discovered from `PLAYWRIGHT_BROWSERS_PATH`
  (`/opt/pw-browsers`); override with `ESTATE_CHROMIUM=/path/to/chrome`.
- Screenshots default to `~/.estate-browser/`; override with `ESTATE_SHOT_DIR`.
- Headless only — there is no visible window and no user handoff in this
  environment. For co-browsing with a human, that is what ego-lite (macOS)
  is for.
