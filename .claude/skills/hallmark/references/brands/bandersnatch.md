# Brand token pack — Bandersnatch (the estate)

A house brand for Hallmark's custom-theme route. When a brief is for
**Bandersnatch**, the estate, the Historical Section, or any Bandersnatch drop
/ lot / clipping, use these locked tokens instead of a catalog theme — the
palette and type below ARE the brand, drawn from the estate's wax system and
rules of the house. Everything else in Hallmark (macrostructure variety,
slop-test gates, pre-emit critique, honest copy) still applies unchanged.

The world: a New-Deal-era federal photography office that was never dissolved,
documenting one county for ninety years. Southern gothic. Archival, not
decorative. The register is a records office, not a storefront.

## Locked tokens

```css
:root {
  /* ground + ink */
  --color-bg:        #141210;   /* estate ground — near-black warm */
  --color-surface:   #1b1815;   /* raised card / folder */
  --color-ink:       #E6E0D3;   /* bone text on ground */
  --color-ink-soft:  #a89f8d;   /* secondary, captions, meta */
  --color-rule:      #2c2822;   /* hairlines, dividers */

  /* wax — one color per world (from the bible's wax system) */
  --color-oxblood:   #6E1F1F;   /* the estate · obituary · primary accent */
  --color-silver:    #94969A;   /* the harbor · contract */
  --color-bone:      #d8cfbe;   /* the county · field report */
  --color-stem:      #56604B;   /* florra (the firm) · herbarium */

  --color-accent:    var(--color-oxblood);

  /* type — IM Fell is the estate face; a grotesque for data/labels */
  --font-display: "IM Fell English", "IM Fell DW Pica", Georgia, serif;
  --font-body:    Georgia, "IM Fell English", serif;
  --font-mono:    "IBM Plex Mono", ui-monospace, monospace; /* caption cards, LOT/negative nos. */
}
```

(Fell faces are on Google Fonts: `IM Fell English`, `IM Fell DW Pica`.)

## Craft rules specific to this brand

- **Documents, not marketing.** Favor macrostructures that read as archival
  record: `12-letter`, `07-manifesto`, `10-specimen`/`17-type-specimen`,
  `02-long-document`, `09-quote-led`. Avoid the SaaS `hero → 3-features → CTA`
  rhythm entirely — it breaks the world.
- **The seal, sparingly.** One wax seal / stamp motif per view, maximum
  (mirrors the bible's "one seal per video"). Never wallpaper it.
- **Mono for the record.** Caption-card lines, LOT numbers, negative numbers,
  dates, and class numbers set in `--font-mono`, lowercase, terse.
- **Oxblood is load-bearing, not loud.** Use it for rules, the seal, one key
  line — not large fills. 10% accent, 90% ground, echoing "10% beast, 90%
  county."
- **Honest copy is doubly law here.** No invented metrics, no fake reviews —
  the office only keeps evidence. Editions are capped at 24; never inflate.
- **Never depict the beast whole.** No monster imagery. Damage, absence, and
  the county stand in for it.
- **Voice:** lower-case-leaning, plain, southern-gothic. Wrestle, don't wink.

## Do not

- Do not use bright/candy accents, gradients-as-decoration, drop-shadow
  glassmorphism, or emoji — none survive the world.
- Do not invent testimonials, star ratings, "trusted by" logo walls, or
  countdown timers (the estate does not use urgency tactics — see the bible).
