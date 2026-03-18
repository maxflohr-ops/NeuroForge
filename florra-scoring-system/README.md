# Florra Scoring System

Airtable implementation package for the **Florra CRM & Operations Hub**.

Creates formula-based priority scoring across People, Outreach, and Brand Targets — giving every contact, deal, and brand a live score and tier (A+ / A / B / C / D) that auto-updates as data changes.

---

## Base Info

| Item | Value |
|------|-------|
| Base ID | `applXEAjh6k3Xmybl` |
| People | `tblvkCqhZRjOjFYlT` |
| Outreach | `tbldNGQfKwQEq4yAo` |
| Brand Targets | `tblWNJdX1WrYFAZyN` |
| Campaigns | `tblvbY12bVp1yudmp` |

---

## Quickstart

### 1. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and set your `AIRTABLE_PAT`:

```
AIRTABLE_PAT=patXXXXXXXXXXXXXX
```

Get your PAT at: https://airtable.com/create/tokens

Required scopes:
- `data.records:read`
- `data.records:write`
- `schema.bases:read`
- `schema.bases:write`

### 2. Install dependencies

```bash
npm install
```

### 3. Dry-run to verify plan

```bash
npm run dry-run:fields
npm run dry-run:views
```

This prints every field and view that will be created without touching Airtable.

### 4. Create scoring fields

```bash
npm run create-fields
```

Creates 11 formula fields on People, 9 on Outreach, and 9 on Brand Targets.
Existing fields with the same name are updated (not duplicated).

### 5. Create views

```bash
npm run create-views
```

Creates 5 views per table (15 total). Filter formulas are printed to the console
for manual application in the Airtable UI.

### 6. Audit scores

```bash
npm run backfill-scores
```

Reads all records and verifies that computed tiers match expected thresholds.
Flags any anomalies that indicate a formula misconfiguration.

### 7. Generate outreach list

```bash
npm run generate-outreach
```

Reads all A+ and A tier People and Brand Targets and outputs a ranked
outreach priority list with suggested actions and message templates.

```bash
npm run generate-outreach -- --create
```

Also creates stub Outreach records in Airtable for each item.

---

## Scoring System

### People Score (0–120 pts)

| Sub-Score | Max | Based On |
|-----------|-----|----------|
| Influence Score Normalized | 25 | Followers × Engagement Rate |
| Value Score Normalized | 25 | Lifetime Value (capped $10k) |
| Spend Score | 20 | Total Spend in bands |
| Order Score | 10 | Total Orders in bands |
| Recency Score | 10 | Days since Last Order Date |
| VIP Score | 10 | VIP checkbox |
| Relationship Strength Score | 10 | Relationship Stage |
| Relationship Tier Score | 5 | Tier (Platinum/Gold/Silver/Bronze) |
| Manual Priority Score | 5 | Manual Priority field (0–5) |

**Tiers:** A+ ≥90 · A ≥70 · B ≥50 · C ≥30 · D <30

---

### Outreach Score (0–110 pts)

| Sub-Score | Max | Based On |
|-----------|-----|----------|
| Rate Score | 20 | Quoted Rate in bands |
| Response Score | 25 | Response Status progression |
| Contract Score | 20 | Contract Status progression |
| Status Momentum Score | 15 | Deal Status |
| Deadline Urgency Score | 10 | Days until Deadline |
| Recency Score | 10 | Days since Last Follow-Up |
| Follow-Up Pressure Score | 10 | Inverted Follow-Up Count |

**Tiers:** A+ ≥85 · A ≥65 · B ≥45 · C ≥25 · D <25

---

### Brand Target Score (0–105 pts)

| Sub-Score | Max | Based On |
|-----------|-----|----------|
| Budget Score | 25 | Estimated Budget in bands |
| Brand Priority Score | 20 | Priority field |
| Pipeline Score | 20 | Pipeline Stage |
| Decision Maker Completeness Score | 10 | DM name + email + title |
| Contact Freshness Score | 10 | Days since Last Contact Date |
| Pitch Readiness Score | 10 | Pitch Status |
| Fit Completeness Score | 10 | Notes + Audience Match + Category |

**Tiers:** A+ ≥80 · A ≥60 · B ≥40 · C ≥20 · D <20

---

## Project Structure

```
florra-scoring-system/
├── README.md
├── package.json
├── tsconfig.json
├── .env.example
├── .gitignore
│
├── src/
│   ├── config.ts           # Environment config loader
│   ├── types.ts            # TypeScript types
│   ├── client.ts           # Airtable REST client (PAT insertion point)
│   ├── field-definitions.ts # All formula field specs
│   └── view-definitions.ts  # All view specs + filter formulas
│
├── scripts/
│   ├── create-fields.ts    # Create/update all scoring fields
│   ├── create-views.ts     # Create all views + print filter guide
│   ├── generate-outreach.ts # Rank A/A+ records + generate message drafts
│   └── backfill-scores.ts  # Audit score/tier consistency
│
└── docs/
    ├── field-spec.md       # Full formula documentation for all 29 fields
    ├── view-spec.md        # All 15 views with filter formulas + setup steps
    └── automation-spec.md  # 12 Airtable automations with full specs
```

---

## Airtable Automations

12 automations are fully specced in [`docs/automation-spec.md`](docs/automation-spec.md):

| ID | Name | Trigger |
|----|------|---------|
| AUTO-01 | Flag New A+ People | Record matches condition |
| AUTO-02 | VIP Upgrade Notification | Record updated |
| AUTO-03 | Re-engagement Reminder | Daily scheduled |
| AUTO-04 | Deadline Alert (7-day) | Daily scheduled |
| AUTO-05 | Contract Follow-Up Reminder | Record updated |
| AUTO-06 | Won Deal Celebration | Record updated |
| AUTO-07 | Stale Outreach Alert | Weekly scheduled |
| AUTO-08 | A+ Brand Target Alert | Record matches condition |
| AUTO-09 | Pitch Stall Detection | Weekly scheduled |
| AUTO-10 | Missing DM Info Alert | Record created/updated |
| AUTO-11 | Campaign Going Live (1-day) | Daily scheduled |
| AUTO-12 | Campaign Completion Wrap-Up | Record updated |

---

## Customizing Field Names

The scoring formulas reference source field names directly. If your Airtable field names differ, update them in `src/field-definitions.ts`:

```typescript
// Find the formula string for the field you want to adjust
// and rename the {Field Name} references to match your actual field names
formula: `IF({Your Actual Field Name} >= 5000, 20, ...)`
```

Then re-run `npm run create-fields` to push the updated formulas.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Missing required environment variable: AIRTABLE_PAT` | Copy `.env.example` to `.env` and set your PAT |
| `Airtable API error [401]` | PAT is invalid or expired — regenerate at airtable.com/create/tokens |
| `Airtable API error [403]` | PAT is missing required scopes — add `schema.bases:write` |
| `Table XXXXX not found` | Table ID mismatch — verify table IDs in `.env` |
| `Cannot update formula field` | Formula fields are read-only via Data API — this is expected |
| Score ≠ expected tier in audit | Source field name mismatch — check formula references in `field-definitions.ts` |
