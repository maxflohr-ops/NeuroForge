# Traps that have already cost time

Each of these was found the expensive way. Read this before any audit, cleanup,
or automation work — most of them look like success from the outside, which is
exactly why they persist.

## Automation that reports success while doing nothing

The single most important thing to know about this fleet.

Nine of eleven scheduled Routines carry **no connector grants at all** —
`mcp_connections: null`. Only routines created in the claude.ai UI
(`created_via: http_api`) have them; anything created by an agent over MCP
(`created_via: meta_mcp`) gets none, and that cannot be fixed from a session.

The failure is silent by construction. A routine that cannot reach its database
finds nothing, writes "nothing to report", and logs SUCCEEDED. Several were
explicitly written to stay quiet on a clean run — *"a clean month is one line"*,
*"send nothing at all"*, *"an empty harvest is a valid week"* — so the blind
output and the healthy output are byte-identical.

Corroborated independently: the Airtable **🤖 Agent Log** holds six rows, every
one `Manual` or `Chained` bootstrap from a single three-hour window on 17–18 Aug.
**Zero `Scheduled` entries, ever.** The automation layer was authored, logged
Success, and never wired to a scheduler.

A fail-loud clause was prepended to eight of them on 31 Aug: if a required tool
is absent, lead with `BLOCKED:` and stop. Verify it is still there before
trusting any of their output.

**One routine could not even log its own failure** — the schema-drift check was
told to write `Outcome = Blocked` to the Airtable table it had no access to.
When a routine goes blind, the push notification is the only channel that works.

## Peer sessions racing you

Three sessions each created a rival master to-do **inside the same minute**.
Read the hub before creating shared structure — someone may have just built it.

Worse: a renamed database is still a **writable** database. A peer session wrote
six new rows into a duplicate that had already been renamed "safe to delete",
three hours after the rename. Five were unique and would have been destroyed by
following the archive's own instructions. **Before emptying any archive, check
for rows newer than the rename.**

## Notion being confidently wrong about money

Notion pages have asserted, and been wrong about:

- **Which Stripe document was rejected and why.** The page said a verification
  document lacked issue and expiry dates. The live API said
  `verification_failed_tax_id_match` — an EIN mismatch. Completely different
  fixes; the written one would have burned a 30-day deadline.
- **How many payment links are live** — six recorded, eleven actual.
- **How many webhooks exist** — one recorded, two actual.
- **A client's retainer.** An agent read *Monthly Ad Spend Under Management* as
  *Retainer Amount*, logged $2,000/mo with a contract end three years early,
  marked it Success, and no human verified it.

**Read money from the source, not from the page.** Then correct the page.

## Stale blockers that are no longer true

Rows sat at `blocked` with "Stripe account activation" long after the account
was activated. A blocker is a claim about the world and it decays. When a
keystone clears, sweep everything that named it.

## Databases whose only row is fake

Contracts Ledger, Editor Roster and Funder Pipeline each hold exactly one
record, and each says "SYSTEM TEST ROW — delete after verification." The Bounty
Sounds board reads its go/no-go launch gates from those tables, so a gate is
currently measured against a fabricated row.

## Pipelines that die quietly, on different days

Three daily feeds stopped on three different dates — People scout 10 Aug, A&R
Watchlist 14 Jul, Market Trends 23 Jul. Staggered dates mean independent
failures with nothing watching. Outreach has been dead 104 days, UGC Pipeline
129. **Nothing monitors staleness.** One check covering all the feeds beats
each of them failing silently.

## Routines that block their own next run

A fresh-session-per-fire Routine whose session is still running when the next
fire is due gets **skipped, not queued** — and the earlier run eventually
completes and logs SUCCEEDED. Briefing's 28 Aug run took 2.7 days and swallowed
three weekday fires of both Briefing and Morning brief. Nothing recorded a
failure.

## Credentials travelling through chat

The Stripe live secret key, the Flowstage API key, a Bluesky password and a
Railway token each went through chat transcripts. A live `sk-ant-` key was
committed to a **public** repo and remains in its history. The Flowstage key
sits in plaintext on a Notion page that three Routines read purely to fetch it.

Two consequences: treat any key you find in a page or a transcript as burned and
say so, and **never write one back** to where you found it.

## Menus offering dishes the kitchen cannot cook

The live payment links offer "Retro game" as a look — a **blocklisted**
aesthetic. Four more options map to no built aesthetic at all. A buyer can pay
$999 today for something Florra cannot deliver. Guarding it in code is a net,
not a fix.

## Things that exist only in prose

The Broke recoupment ledger is **$2,660 short** of the invoice it backs.
Stella's EP shoot and Haaziq's tour poster are described on the invoice page and
have no database rows. The page diagnoses the gap itself and the rows were still
never created.

Prose is where work goes to be forgotten. If it matters, it needs a row.
