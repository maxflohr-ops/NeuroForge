# Florra systems — canonical IDs

Verified 31 Aug 2026 by direct read. IDs move; if one 404s, that is drift and
worth reporting rather than working around.

## Notion

| Thing | ID |
|---|---|
| 🌱 Florra OS (the hub) | `3c0ad17a-5fd0-810d-be4f-c99b3418bcf5` |
| Florra OS — Master To-Do | `1d9c5413-6e50-494a-80ef-3a1338a68dae` |
| ↳ its data source | `collection://d7532958-6ff0-491a-a4bd-b417613cfac0` |
| Artist Roster | `073e3a20-c0a8-4709-b9c5-1487a435ed7b` |
| Florra Products | `205df97e-c4bb-44cc-8cfa-9d01516fa9e1` |
| Florra Skills | `a1b9796c-8d5d-4855-b3f2-5f3be2fad079` |
| Taking on a new client — walkthrough | `3c0ad17a-5fd0-815c-8941-f1312b83ae75` |
| Flowstage Engine — control page | `3cdad17a-5fd0-8181-8f66-cb4c313cd3d6` |
| Broke Recoupment Ledger | `collection://7046a6fb-c8ce-4aef-9b5e-190bd03481ba` |
| UMG Reimbursement Ledger | `collection://3ac74061-e1e6-4d6b-9e3d-649a28714173` |
| The Tap Counter | `collection://33ead492-64c5-43fe-90da-7bc8f620d99c` |

**Master To-Do schema.** Item (title) · Status (open / blocked / waiting on data
/ done / duplicate) · Owner (max / claude / either) · Priority (now / next /
later) · Area (measurement / money / florra.net / redstring / bounty sounds /
roster / infrastructure / legal + admin) · Blocker · Why it matters.

**Do not write to these.** Two rival master to-dos, merged and renamed for
deletion, parked under 🗑️ Archive: `22867071-2f36-4da4-adef-aa2508959a7f` and
`d0089d5b-8282-4bf0-9c2c-1db74a207f17`.

## Airtable — base `applXEAjh6k3Xmybl` ("Florra CRM & Operations Hub")

All 16 documented table IDs resolved clean on 31 Aug 2026.

| Table | ID |
|---|---|
| People | `tblvkCqhZRjOjFYlT` |
| 🎯 Targets — One List | `tblTYdXGh5ObgjzOY` |
| Outreach | `tbldNGQfKwQEq4yAo` |
| Clients | `tbligbqtzVynVm5mj` |
| Campaigns | `tblvbY12bVp1yudmp` |
| 🚀 Deployments | `tblNR1qWvM3GrH74r` |
| ⚔️ Arsenal — Fan Systems | `tblsBDyzomoXba5Bz` |
| Daily Ad Performance | `tbl4Oj4XiKwlyQmBW` |
| Ad Spend Tracker | `tbl6OSZ1mB4ve4wVf` |
| 🤖 Agent Log | `tbl5WgFWOXXef3GsR` |
| 🧠 Gotchas | `tblxPwfPNKhFx3ril` |
| 🪝 Hook Inventory | `tblvpHvR31j8ea070` |
| UGC Content Submissions | `tblnuiXMJVE88Gr1S` |
| Content Library | `tblmKJcNNOeEUaI79` |
| Spark Codes | `tblqRpE6Ou9vXImey` |
| UGC Pipeline | `tblqTn9O3rIMMecbT` |

The base holds **34 tables**; only these 16 are documented. Two undocumented
ones matter: **Ad Groups** `tblfW28SNHyraON6S` is the parent of Daily Ad
Performance, so ad data cannot be reasoned about without it; and
**zz OLD — Prospects** `tblWNJdX1WrYFAZyN` is retired but still live and still
linked from Clients.

## Stripe

Account `acct_1THx5L02QBnOMPfQ` — Florra LLC, US/USD, activated. One account
carries every rail. Payout destination Bank of America …4459.

Eleven live payment links: six Florra Network ($99 / $399 / $999, song and
brand ladders) and five Redstring (Case Sponsor $1,200, Featured Show $600, Up
Next $250, Founding String $50/yr, Pro $5/mo).

Two webhook endpoints, both subscribed to `checkout.session.completed`:
`we_1UAQU702QBnOMPfQv2UzmBFT` → florra.net, and `we_1UANAB02QBnOMPfQb2gSFX3r` →
the Redstring Supabase function. **Stripe webhooks are account-wide**, so every
sale fires both — handlers must filter on `metadata.app`.

## Flowstage

Base `https://api.theflowstage.com/v1`. Auth header **`X-API-Key`** — Bearer
returns 422. Contract verified live 31 Aug 2026; the full detail lives in
section 3 of the Flowstage control page and should not be re-derived.

`POST /video-edits/draft` requires `aesthetic_id`, `audio_id`,
`section_start_time`, `section_end_time`. Optional: `hook`, `preset_name`,
`name`, `videos`.

**Do not trust `render_status`** — it has been observed at `in_progress` /
`render_progress: 0.03` for five minutes after the finished MP4 was already
written. Poll `render_url` with HEAD and require HTTP 200 with the same
Content-Length twice, a few seconds apart; a HEAD can return 403 or a partial
length mid-write.

**Blocklist, absolute:** audio `cbc22eb0` ("out the cage") and aesthetic
`1b38eec9-72fa-4d9e-827e-e48529f291ff` ("retro game"). Never build, schedule or
post on either. Aesthetic "the backrooms" is unusable until another audio is
uploaded to it, since out the cage is its only one.

**Flowstage never autoposts.** It drops a draft into the TikTok app inbox; a
human attaches the official sound and posts. This is not a limitation to route
around — TikTok's own Direct Post audit requires a human-driven UI, so it is the
compliant pattern.

## Sites

florra.net (Vercel, apex 308s to www) · redstringlive.com · bountysounds.com ·
bandersnatch.world · ridgeclubhouse.com · ebril.net (UMG's platform).

GA4: florra.net `G-FH2CKB37CM` · redstringlive.com `G-5GMVP52B8V` ·
bountysounds.com `G-TZJ2P5F6R5`.

## Repos

`maxflohr-ops/florra-net` · `redstring-live` · `tiktok-bounty-beat` ·
`NeuroForge` · `designrepo1`. Sessions can read public ones anonymously but
need an explicit attach to push.
