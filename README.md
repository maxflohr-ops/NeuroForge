# bandersnatch — the field office

A multi-page static lore site for BANDERSNATCH: a southern-gothic world that
sells clothing, not a clothing site with lore. Plain HTML/CSS/JS — no
frameworks, no build step. Works straight from `file://`.

**Deploy:** drag this folder onto [Netlify Drop](https://app.netlify.com/drop)
(or run `vercel` in it) — it's static files, nothing to build.

## rooms

| file | room |
|---|---|
| `index.html` | the county — hero, now-printing plates, courthouse notice, three doors |
| `file.html` | the holdings — lots 001–011 with product photography, lamplight follows the cursor |
| `record.html` | the record — serial field dispatches; add entries here to give followers a reason to return |
| `bestiary.html` | three exhibits — plates I–III |
| `virginia.html` | the estate — obituary, the succession |
| `counter.html` | ask the office — the clerk (client-side only) |
| `ledger.html` | the visitor ledger — email capture |

Every page ends with a "next room" link so a visitor can walk the whole
building: county → file → record → bestiary → virginia → counter → ledger.

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
- **Images:** product photography is pulled straight from the Shopify CDN
  (with `&width=` resizing), shown desaturated and revealed in color on
  hover. The site still stands on type + texture if the CDN is unreachable.
- **SEO:** every page has Open Graph / Twitter cards, a canonical URL, and
  `og:url` pointing at `https://bandersnatch.world`; `index.html` carries
  Organization + WebSite JSON-LD and `file.html` carries an ItemList of
  Product schema pointing offers at the Shopify product pages. `robots.txt`
  and `sitemap.xml` reference the same domain — once the domain is live,
  submit the sitemap in Google Search Console.

## the office writes (content pipeline)

`office/bandersnatch_office.py` — repurposed from the NeuroForge staged
generate→QA pipeline — drafts in-world content and then audits it against
the canon's hard rules (the "archivist QA" pass emits a verdict, violations,
and a corrected version):

```bash
python3 office/bandersnatch_office.py --mode dispatch --count 3 \
  --context "september, year ninety. the canister marked vii is still undeveloped."
# modes: dispatch (record entries + paste-ready HTML) · lot (next holding)
#        shorts (no-faces tiktok scripts) · letter (estate email) · full
```

Output lands in `office/output/<date>_<context>/` as draft + QA pairs.
Runs on `ANTHROPIC_API_KEY` or the Claude remote session token.

the file is not closed.
