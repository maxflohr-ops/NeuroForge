# bandersnatch — the field office

A multi-page static lore site for BANDERSNATCH: a southern-gothic world that
sells clothing, not a clothing site with lore. Plain HTML/CSS/JS — no
frameworks, no build step. Works straight from `file://`.

**Deploy:** drag this folder onto [Netlify Drop](https://app.netlify.com/drop)
(or run `vercel` in it) — it's static files, nothing to build.

## rooms

| file | room |
|---|---|
| `index.html` | the county — hero, courthouse notice, three doors |
| `file.html` | the holdings — lots 001–008, lamplight follows the cursor |
| `bestiary.html` | three exhibits — plates I–III |
| `virginia.html` | the estate — obituary, the succession |
| `counter.html` | ask the office — the clerk (client-side only) |
| `ledger.html` | the visitor ledger — email capture |

## wiring

- **Fonts:** all typography lives in `assets/fonts.css` — the one file to
  edit when plugging in a different font. Load your face there (Google
  `@import` or self-hosted `@font-face`), then put its name first in the
  matching role variable (`--serif` prose, `--display` titles, `--mono`
  typewriter). Nothing else references a typeface by name.
- **Email capture:** `ledger.html` contains a clearly marked `KLAVIYO
  PLACEHOLDER` comment — swap the form `action` for your Klaviyo subscribe
  endpoint and remove `data-placeholder="true"`. Until then it confirms
  locally and sends nothing.
- **Commerce:** each holding on `file.html` deep-links to its product page
  on `https://bandersnatch-2.myshopify.com` (lots 001–008 as of collection
  001; lots 009–011 are UNTITLED teases with no link).
- **Images:** none required — the site stands on type and CSS/SVG texture
  (film grain, halftone, vignette). Drop plates into `/assets` and reference
  them if you want photographs.

the file is not closed.
