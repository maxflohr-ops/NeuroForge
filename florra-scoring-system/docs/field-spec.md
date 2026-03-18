# Florra Scoring System — Field Specification

## Overview

All scoring fields are **formula fields** — Airtable computes them automatically from source data. You never need to manually enter scores. Just keep source fields current and the scores update in real time.

### Scoring Philosophy

| Principle | Detail |
|-----------|--------|
| **Additive** | Sub-scores add up to a single composite score per table |
| **Capped inputs** | Raw values (followers, budget) are capped to prevent outliers from dominating |
| **Recency-weighted** | Date-based scores decay over time, rewarding active relationships |
| **Manual override** | A `Manual Priority` field lets you boost any record by up to 5 pts |
| **Tiers** | A+ / A / B / C / D tiers derived from composite score thresholds |

---

## People Table (`tblvkCqhZRjOjFYlT`)

### Source Fields (must exist before creating score fields)

| Field Name | Type | Notes |
|-----------|------|-------|
| `Followers` | Number | Total follower count across primary platform |
| `Engagement Rate` | Number | Percent (0–100), not decimal |
| `Lifetime Value` | Currency | Total revenue attributed to this person |
| `Total Spend` | Currency | Cumulative spend |
| `Total Orders` | Number | Count of completed orders |
| `Last Order Date` | Date | Date of most recent order |
| `VIP` | Checkbox | Manual VIP flag |
| `Relationship Stage` | Single Select | `VIP Partner` / `Partner` / `Active` / `Warm` / `Prospect` / `Cold` |
| `Tier` | Single Select | `Platinum` / `Gold` / `Silver` / `Bronze` |
| `Manual Priority` | Number | 0–5 override weight |

### Score Fields (created by `npm run create-fields`)

| Field Name | Type | Max Pts | Description |
|-----------|------|---------|-------------|
| `Influence Score Normalized` | Formula → Number | 25 | Follower reach × engagement, capped at 1M followers and 10% ER |
| `Value Score Normalized` | Formula → Number | 25 | Lifetime Value scaled to $10k ceiling |
| `Spend Score` | Formula → Number | 20 | Total Spend in tiered bands |
| `Order Score` | Formula → Number | 10 | Total Orders in tiered bands |
| `Recency Score` | Formula → Number | 10 | Days since Last Order Date (decays with time) |
| `VIP Score` | Formula → Number | 10 | VIP checkbox = 10 pts flat |
| `Relationship Strength Score` | Formula → Number | 10 | Based on Relationship Stage |
| `Relationship Tier Score` | Formula → Number | 5 | Based on Tier field |
| `Manual Priority Score` | Formula → Number | 5 | Pass-through of Manual Priority (clamped 0–5) |
| **`Florra Priority Score`** | Formula → Number | **120** | **Sum of all sub-scores** |
| **`Florra Priority Tier`** | Formula → Text | — | **A+ / A / B / C / D** |

### Tier Thresholds (People)

| Tier | Score Range | Meaning |
|------|------------|---------|
| A+ | ≥ 90 | VIP / highest priority |
| A  | 70–89 | High priority — engage this week |
| B  | 50–69 | Medium — keep warm |
| C  | 30–49 | Low — nurture sequence |
| D  | < 30 | Deprioritize / archive candidate |

### Formula Details

#### Influence Score Normalized
```
ROUND(
  MIN(25,
    IF(
      AND({Followers} > 0, {Engagement Rate} > 0),
      (MIN({Followers}, 1000000) / 1000000 * 15) + (MIN({Engagement Rate}, 10) / 10 * 10),
      IF({Followers} > 0, MIN({Followers}, 1000000) / 1000000 * 15, 0)
    )
  ),
  1
)
```

#### Value Score Normalized
```
ROUND(
  MIN(25,
    IF({Lifetime Value} > 0, MIN({Lifetime Value}, 10000) / 10000 * 25, 0)
  ),
  1
)
```

#### Spend Score
```
IF({Total Spend} >= 5000, 20,
IF({Total Spend} >= 2000, 15,
IF({Total Spend} >= 1000, 10,
IF({Total Spend} >= 500, 7,
IF({Total Spend} >= 100, 4,
IF({Total Spend} > 0, 2, 0))))))
```

#### Order Score
```
IF({Total Orders} >= 20, 10,
IF({Total Orders} >= 10, 8,
IF({Total Orders} >= 5, 6,
IF({Total Orders} >= 3, 4,
IF({Total Orders} >= 1, 2, 0)))))
```

#### Recency Score
```
ROUND(
  IF({Last Order Date},
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 30, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 90, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 180, 5,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 365, 3, 1)))),
    0
  ),
  1
)
```

#### VIP Score
```
IF({VIP}, 10, 0)
```

#### Relationship Strength Score
```
SWITCH({Relationship Stage},
  "VIP Partner", 10,
  "Partner", 8,
  "Active", 6,
  "Warm", 4,
  "Prospect", 2,
  "Cold", 1,
  0
)
```

#### Relationship Tier Score
```
SWITCH({Tier},
  "Platinum", 5,
  "Gold", 4,
  "Silver", 3,
  "Bronze", 2,
  1
)
```

#### Manual Priority Score
```
IF({Manual Priority}, MIN(5, MAX(0, {Manual Priority})), 0)
```

#### Florra Priority Score
```
ROUND(
  {Influence Score Normalized}
  + {Value Score Normalized}
  + {Spend Score}
  + {Order Score}
  + {Recency Score}
  + {VIP Score}
  + {Relationship Strength Score}
  + {Relationship Tier Score}
  + {Manual Priority Score},
  1
)
```

#### Florra Priority Tier
```
IF({Florra Priority Score} >= 90, "A+",
IF({Florra Priority Score} >= 70, "A",
IF({Florra Priority Score} >= 50, "B",
IF({Florra Priority Score} >= 30, "C",
"D"))))
```

---

## Outreach Table (`tbldNGQfKwQEq4yAo`)

### Source Fields

| Field Name | Type | Notes |
|-----------|------|-------|
| `Quoted Rate` | Currency | Rate quoted to/from this person |
| `Response Status` | Single Select | `Signed` / `Negotiating` / `Interested` / `Replied` / `Opened` / `Sent` / `No Response` |
| `Contract Status` | Single Select | `Signed` / `Negotiating` / `Sent` / `Drafting` / `Not Started` |
| `Status` | Single Select | `Closed Won` / `Active` / `Pending` / `New` / `On Hold` / `Closed Lost` |
| `Deadline` | Date | Hard deadline for this deal |
| `Last Follow-Up Date` | Date | Date of most recent follow-up |
| `Follow-Up Count` | Number | Total number of follow-ups sent |

### Score Fields

| Field Name | Type | Max Pts | Description |
|-----------|------|---------|-------------|
| `Rate Score` | Formula → Number | 20 | Quoted Rate in tiered bands |
| `Response Score` | Formula → Number | 25 | Response Status progression |
| `Contract Score` | Formula → Number | 20 | Contract Status progression |
| `Status Momentum Score` | Formula → Number | 15 | Pipeline Status weight |
| `Deadline Urgency Score` | Formula → Number | 10 | Urgency based on days to deadline |
| `Recency Score` | Formula → Number | 10 | Days since last follow-up |
| `Follow-Up Pressure Score` | Formula → Number | 10 | Inverted — fewer touches = more pressure |
| **`Outreach Priority Score`** | Formula → Number | **110** | **Sum of all sub-scores** |
| **`Outreach Priority Tier`** | Formula → Text | — | **A+ / A / B / C / D** |

### Tier Thresholds (Outreach)

| Tier | Score Range |
|------|------------|
| A+ | ≥ 85 |
| A  | 65–84 |
| B  | 45–64 |
| C  | 25–44 |
| D  | < 25 |

### Formula Details

#### Rate Score
```
IF({Quoted Rate} >= 10000, 20,
IF({Quoted Rate} >= 5000, 16,
IF({Quoted Rate} >= 2000, 12,
IF({Quoted Rate} >= 1000, 8,
IF({Quoted Rate} >= 500, 5,
IF({Quoted Rate} > 0, 2, 0))))))
```

#### Response Score
```
SWITCH({Response Status},
  "Signed", 25,
  "Negotiating", 20,
  "Interested", 16,
  "Replied", 12,
  "Opened", 6,
  "Sent", 3,
  "No Response", 1,
  0
)
```

#### Contract Score
```
SWITCH({Contract Status},
  "Signed", 20,
  "Negotiating", 16,
  "Sent", 14,
  "Drafting", 8,
  "Not Started", 2,
  0
)
```

#### Status Momentum Score
```
SWITCH({Status},
  "Closed Won", 15,
  "Active", 12,
  "Pending", 8,
  "New", 5,
  "On Hold", 2,
  "Closed Lost", 0,
  0
)
```

#### Deadline Urgency Score
```
ROUND(
  IF({Deadline},
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 0, 10,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 7, 9,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 14, 7,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 30, 5,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 60, 3, 1))))),
    0
  ),
  1
)
```

#### Recency Score
```
ROUND(
  IF({Last Follow-Up Date},
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 3, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 7, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 14, 5,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 30, 3, 1)))),
    0
  ),
  1
)
```

#### Follow-Up Pressure Score
```
IF({Follow-Up Count} = 0, 10,
IF({Follow-Up Count} = 1, 7,
IF({Follow-Up Count} = 2, 5,
IF({Follow-Up Count} = 3, 3,
IF({Follow-Up Count} >= 4, 1, 0)))))
```

#### Outreach Priority Score
```
ROUND(
  {Rate Score}
  + {Response Score}
  + {Contract Score}
  + {Status Momentum Score}
  + {Deadline Urgency Score}
  + {Recency Score}
  + {Follow-Up Pressure Score},
  1
)
```

#### Outreach Priority Tier
```
IF({Outreach Priority Score} >= 85, "A+",
IF({Outreach Priority Score} >= 65, "A",
IF({Outreach Priority Score} >= 45, "B",
IF({Outreach Priority Score} >= 25, "C",
"D"))))
```

---

## Brand Targets Table (`tblWNJdX1WrYFAZyN`)

### Source Fields

| Field Name | Type | Notes |
|-----------|------|-------|
| `Estimated Budget` | Currency | Brand's estimated campaign budget |
| `Priority` | Single Select | `Critical` / `High` / `Medium` / `Low` |
| `Pipeline Stage` | Single Select | `Cold Lead` / `Prospect` / `Discovery` / `Proposal Sent` / `Negotiating` / `Contract Out` / `Closed Won` |
| `Decision Maker Name` | Text | Name of decision maker |
| `Decision Maker Email` | Email | Email of decision maker |
| `Decision Maker Title` | Text | Title/role of decision maker |
| `Last Contact Date` | Date | Most recent contact with this brand |
| `Pitch Status` | Single Select | `Not Started` / `In Progress` / `Draft Ready` / `In Review` / `Scheduled` / `Delivered` |
| `Brand Fit Notes` | Long Text | Notes on brand fit |
| `Target Audience Match` | Text | Description of audience overlap |
| `Category` | Single Select | Industry/category |

### Score Fields

| Field Name | Type | Max Pts | Description |
|-----------|------|---------|-------------|
| `Budget Score` | Formula → Number | 25 | Estimated Budget in tiered bands |
| `Brand Priority Score` | Formula → Number | 20 | Priority single-select weight |
| `Pipeline Score` | Formula → Number | 20 | Pipeline Stage progression |
| `Decision Maker Completeness Score` | Formula → Number | 10 | DM name + email + title completeness |
| `Contact Freshness Score` | Formula → Number | 10 | Days since last contact |
| `Pitch Readiness Score` | Formula → Number | 10 | Pitch Status progression |
| `Fit Completeness Score` | Formula → Number | 10 | Brand Fit Notes + Audience Match + Category |
| **`Brand Target Score`** | Formula → Number | **105** | **Sum of all sub-scores** |
| **`Brand Target Tier`** | Formula → Text | — | **A+ / A / B / C / D** |

### Tier Thresholds (Brand Targets)

| Tier | Score Range |
|------|------------|
| A+ | ≥ 80 |
| A  | 60–79 |
| B  | 40–59 |
| C  | 20–39 |
| D  | < 20 |

### Formula Details

#### Budget Score
```
IF({Estimated Budget} >= 50000, 25,
IF({Estimated Budget} >= 25000, 20,
IF({Estimated Budget} >= 10000, 15,
IF({Estimated Budget} >= 5000, 10,
IF({Estimated Budget} >= 1000, 5,
IF({Estimated Budget} > 0, 2, 0))))))
```

#### Brand Priority Score
```
SWITCH({Priority},
  "Critical", 20,
  "High", 15,
  "Medium", 10,
  "Low", 5,
  0
)
```

#### Pipeline Score
```
SWITCH({Pipeline Stage},
  "Closed Won", 20,
  "Contract Out", 18,
  "Negotiating", 16,
  "Proposal Sent", 12,
  "Discovery", 8,
  "Prospect", 4,
  "Cold Lead", 2,
  0
)
```

#### Decision Maker Completeness Score
```
IF({Decision Maker Name}, 4, 0)
+ IF({Decision Maker Email}, 4, 0)
+ IF({Decision Maker Title}, 2, 0)
```

#### Contact Freshness Score
```
ROUND(
  IF({Last Contact Date},
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 7, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 14, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 30, 6,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 60, 4,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 90, 2, 1))))),
    0
  ),
  1
)
```

#### Pitch Readiness Score
```
SWITCH({Pitch Status},
  "Delivered", 10,
  "Scheduled", 8,
  "In Review", 6,
  "Draft Ready", 4,
  "In Progress", 2,
  "Not Started", 1,
  0
)
```

#### Fit Completeness Score
```
IF({Brand Fit Notes}, 4, 0)
+ IF({Target Audience Match}, 4, 0)
+ IF({Category}, 2, 0)
```

#### Brand Target Score
```
ROUND(
  {Budget Score}
  + {Brand Priority Score}
  + {Pipeline Score}
  + {Decision Maker Completeness Score}
  + {Contact Freshness Score}
  + {Pitch Readiness Score}
  + {Fit Completeness Score},
  1
)
```

#### Brand Target Tier
```
IF({Brand Target Score} >= 80, "A+",
IF({Brand Target Score} >= 60, "A",
IF({Brand Target Score} >= 40, "B",
IF({Brand Target Score} >= 20, "C",
"D"))))
```
