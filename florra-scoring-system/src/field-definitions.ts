/**
 * Florra Scoring System — Field Definitions
 *
 * All formula fields for People, Outreach, and Brand Targets tables.
 * Formulas use Airtable formula syntax and reference existing field names.
 *
 * FIELD NAME ASSUMPTIONS:
 * If your actual field names differ, update the references inside each formula
 * string. The section header above each block documents the assumed source fields.
 *
 * SCORING SCALE:
 *   A+  = top tier (90%+ of max score)
 *   A   = high priority
 *   B   = medium priority
 *   C   = low priority
 *   D   = deprioritize / archive candidate
 */

import type { FieldSpec } from "./types";

// ─────────────────────────────────────────────────────────────────────────────
// PEOPLE TABLE
// Source fields assumed: Followers (number), Engagement Rate (number 0–100),
//   Lifetime Value (currency), Total Spend (currency), Total Orders (number),
//   Last Order Date (date), VIP (checkbox), Relationship Stage (single select),
//   Tier (single select), Manual Priority (number 1–5)
// ─────────────────────────────────────────────────────────────────────────────

export const PEOPLE_FIELDS: FieldSpec[] = [
  {
    name: "Influence Score Normalized",
    type: "formula",
    description: "0–25 pts. Follower reach × engagement rate, capped at 1M followers and 10% engagement.",
    options: {
      formula: `ROUND(
  MIN(25,
    IF(
      AND({Followers} > 0, {Engagement Rate} > 0),
      (MIN({Followers}, 1000000) / 1000000 * 15) + (MIN({Engagement Rate}, 10) / 10 * 10),
      IF({Followers} > 0, MIN({Followers}, 1000000) / 1000000 * 15, 0)
    )
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Value Score Normalized",
    type: "formula",
    description: "0–25 pts. Lifetime Value scaled to $10k ceiling.",
    options: {
      formula: `ROUND(
  MIN(25,
    IF({Lifetime Value} > 0, MIN({Lifetime Value}, 10000) / 10000 * 25, 0)
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Spend Score",
    type: "formula",
    description: "0–20 pts. Total Spend in tiered bands.",
    options: {
      formula: `IF({Total Spend} >= 5000, 20,
IF({Total Spend} >= 2000, 15,
IF({Total Spend} >= 1000, 10,
IF({Total Spend} >= 500, 7,
IF({Total Spend} >= 100, 4,
IF({Total Spend} > 0, 2, 0))))))`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Order Score",
    type: "formula",
    description: "0–10 pts. Total Orders in tiered bands.",
    options: {
      formula: `IF({Total Orders} >= 20, 10,
IF({Total Orders} >= 10, 8,
IF({Total Orders} >= 5, 6,
IF({Total Orders} >= 3, 4,
IF({Total Orders} >= 1, 2, 0)))))`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Recency Score",
    type: "formula",
    description: "0–10 pts. Days since Last Order Date: ≤30d=10, ≤90d=8, ≤180d=5, ≤365d=3, older=1, no date=0.",
    options: {
      formula: `ROUND(
  IF({Last Order Date},
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 30, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 90, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 180, 5,
    IF(DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') <= 365, 3, 1)))),
    0
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "VIP Score",
    type: "formula",
    description: "0 or 10 pts. VIP checkbox = instant 10-point boost.",
    options: {
      formula: `IF({VIP}, 10, 0)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Relationship Strength Score",
    type: "formula",
    description: "0–10 pts. Based on Relationship Stage single-select.",
    options: {
      formula: `SWITCH({Relationship Stage},
  "VIP Partner", 10,
  "Partner", 8,
  "Active", 6,
  "Warm", 4,
  "Prospect", 2,
  "Cold", 1,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Relationship Tier Score",
    type: "formula",
    description: "0–5 pts. Based on Tier field (Platinum/Gold/Silver/Bronze).",
    options: {
      formula: `SWITCH({Tier},
  "Platinum", 5,
  "Gold", 4,
  "Silver", 3,
  "Bronze", 2,
  1
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Manual Priority Score",
    type: "formula",
    description: "0–5 pts. Direct pass-through of Manual Priority field (clamped 0–5).",
    options: {
      formula: `IF({Manual Priority}, MIN(5, MAX(0, {Manual Priority})), 0)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Florra Priority Score",
    type: "formula",
    description: "0–120 pts. Weighted composite of all People sub-scores. A+ ≥90, A ≥70, B ≥50, C ≥30, D <30.",
    options: {
      formula: `ROUND(
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
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Florra Priority Tier",
    type: "formula",
    description: "Text tier derived from Florra Priority Score: A+ / A / B / C / D",
    options: {
      formula: `IF({Florra Priority Score} >= 90, "A+",
IF({Florra Priority Score} >= 70, "A",
IF({Florra Priority Score} >= 50, "B",
IF({Florra Priority Score} >= 30, "C",
"D"))))`,
      result: { type: "singleLineText" },
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// OUTREACH TABLE
// Source fields assumed: Quoted Rate (currency), Response Status (single select),
//   Contract Status (single select), Status (single select), Deadline (date),
//   Last Follow-Up Date (date), Follow-Up Count (number)
// ─────────────────────────────────────────────────────────────────────────────

export const OUTREACH_FIELDS: FieldSpec[] = [
  {
    name: "Rate Score",
    type: "formula",
    description: "0–20 pts. Quoted Rate in tiered bands (≥$10k=20 down to >$0=2).",
    options: {
      formula: `IF({Quoted Rate} >= 10000, 20,
IF({Quoted Rate} >= 5000, 16,
IF({Quoted Rate} >= 2000, 12,
IF({Quoted Rate} >= 1000, 8,
IF({Quoted Rate} >= 500, 5,
IF({Quoted Rate} > 0, 2, 0))))))`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Response Score",
    type: "formula",
    description: "0–25 pts. Response Status: Signed=25, Negotiating=20, Interested=16, Replied=12, Opened=6, Sent=3, No Response=1.",
    options: {
      formula: `SWITCH({Response Status},
  "Signed", 25,
  "Negotiating", 20,
  "Interested", 16,
  "Replied", 12,
  "Opened", 6,
  "Sent", 3,
  "No Response", 1,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Contract Score",
    type: "formula",
    description: "0–20 pts. Contract Status: Signed=20, Negotiating=16, Sent=14, Drafting=8, Not Started=2.",
    options: {
      formula: `SWITCH({Contract Status},
  "Signed", 20,
  "Negotiating", 16,
  "Sent", 14,
  "Drafting", 8,
  "Not Started", 2,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Status Momentum Score",
    type: "formula",
    description: "0–15 pts. Outreach Status pipeline stage weight.",
    options: {
      formula: `SWITCH({Status},
  "Closed Won", 15,
  "Active", 12,
  "Pending", 8,
  "New", 5,
  "On Hold", 2,
  "Closed Lost", 0,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Deadline Urgency Score",
    type: "formula",
    description: "0–10 pts. Days until Deadline: overdue=10, ≤7d=9, ≤14d=7, ≤30d=5, ≤60d=3, further=1, no date=0.",
    options: {
      formula: `ROUND(
  IF({Deadline},
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 0, 10,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 7, 9,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 14, 7,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 30, 5,
    IF(DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 60, 3, 1))))),
    0
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Recency Score",
    type: "formula",
    description: "0–10 pts. Days since Last Follow-Up Date: ≤3d=10, ≤7d=8, ≤14d=5, ≤30d=3, older=1, no date=0.",
    options: {
      formula: `ROUND(
  IF({Last Follow-Up Date},
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 3, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 7, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 14, 5,
    IF(DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') <= 30, 3, 1)))),
    0
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Follow-Up Pressure Score",
    type: "formula",
    description: "0–10 pts. Inverted follow-up count — fewer attempts = more urgency to reach out.",
    options: {
      formula: `IF({Follow-Up Count} = 0, 10,
IF({Follow-Up Count} = 1, 7,
IF({Follow-Up Count} = 2, 5,
IF({Follow-Up Count} = 3, 3,
IF({Follow-Up Count} >= 4, 1, 0)))))`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Outreach Priority Score",
    type: "formula",
    description: "0–110 pts. Weighted composite of all Outreach sub-scores. A+ ≥85, A ≥65, B ≥45, C ≥25, D <25.",
    options: {
      formula: `ROUND(
  {Rate Score}
  + {Response Score}
  + {Contract Score}
  + {Status Momentum Score}
  + {Deadline Urgency Score}
  + {Recency Score}
  + {Follow-Up Pressure Score},
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Outreach Priority Tier",
    type: "formula",
    description: "Text tier derived from Outreach Priority Score: A+ / A / B / C / D",
    options: {
      formula: `IF({Outreach Priority Score} >= 85, "A+",
IF({Outreach Priority Score} >= 65, "A",
IF({Outreach Priority Score} >= 45, "B",
IF({Outreach Priority Score} >= 25, "C",
"D"))))`,
      result: { type: "singleLineText" },
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// BRAND TARGETS TABLE
// Source fields assumed: Estimated Budget (currency), Priority (single select),
//   Pipeline Stage (single select), Decision Maker Name (text),
//   Decision Maker Email (email), Decision Maker Title (text),
//   Last Contact Date (date), Pitch Status (single select),
//   Brand Fit Notes (text), Target Audience Match (text), Category (single select)
// ─────────────────────────────────────────────────────────────────────────────

export const BRAND_TARGET_FIELDS: FieldSpec[] = [
  {
    name: "Budget Score",
    type: "formula",
    description: "0–25 pts. Estimated Budget tiered bands (≥$50k=25 down to >$0=2).",
    options: {
      formula: `IF({Estimated Budget} >= 50000, 25,
IF({Estimated Budget} >= 25000, 20,
IF({Estimated Budget} >= 10000, 15,
IF({Estimated Budget} >= 5000, 10,
IF({Estimated Budget} >= 1000, 5,
IF({Estimated Budget} > 0, 2, 0))))))`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Brand Priority Score",
    type: "formula",
    description: "0–20 pts. Priority single-select: Critical=20, High=15, Medium=10, Low=5.",
    options: {
      formula: `SWITCH({Priority},
  "Critical", 20,
  "High", 15,
  "Medium", 10,
  "Low", 5,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Pipeline Score",
    type: "formula",
    description: "0–20 pts. Pipeline Stage progression weight.",
    options: {
      formula: `SWITCH({Pipeline Stage},
  "Closed Won", 20,
  "Contract Out", 18,
  "Negotiating", 16,
  "Proposal Sent", 12,
  "Discovery", 8,
  "Prospect", 4,
  "Cold Lead", 2,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Decision Maker Completeness Score",
    type: "formula",
    description: "0–10 pts. Name=4pts, Email=4pts, Title=2pts.",
    options: {
      formula: `IF({Decision Maker Name}, 4, 0)
+ IF({Decision Maker Email}, 4, 0)
+ IF({Decision Maker Title}, 2, 0)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Contact Freshness Score",
    type: "formula",
    description: "0–10 pts. Days since Last Contact Date: ≤7d=10, ≤14d=8, ≤30d=6, ≤60d=4, ≤90d=2, older=1, no date=0.",
    options: {
      formula: `ROUND(
  IF({Last Contact Date},
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 7, 10,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 14, 8,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 30, 6,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 60, 4,
    IF(DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') <= 90, 2, 1))))),
    0
  ),
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Pitch Readiness Score",
    type: "formula",
    description: "0–10 pts. Pitch Status: Delivered=10, Scheduled=8, In Review=6, Draft Ready=4, In Progress=2, Not Started=1.",
    options: {
      formula: `SWITCH({Pitch Status},
  "Delivered", 10,
  "Scheduled", 8,
  "In Review", 6,
  "Draft Ready", 4,
  "In Progress", 2,
  "Not Started", 1,
  0
)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Fit Completeness Score",
    type: "formula",
    description: "0–10 pts. Brand Fit Notes=4pts, Target Audience Match=4pts, Category=2pts.",
    options: {
      formula: `IF({Brand Fit Notes}, 4, 0)
+ IF({Target Audience Match}, 4, 0)
+ IF({Category}, 2, 0)`,
      result: { type: "number", options: { precision: 0 } },
    },
  },
  {
    name: "Brand Target Score",
    type: "formula",
    description: "0–105 pts. Weighted composite of all Brand Target sub-scores. A+ ≥80, A ≥60, B ≥40, C ≥20, D <20.",
    options: {
      formula: `ROUND(
  {Budget Score}
  + {Brand Priority Score}
  + {Pipeline Score}
  + {Decision Maker Completeness Score}
  + {Contact Freshness Score}
  + {Pitch Readiness Score}
  + {Fit Completeness Score},
  1
)`,
      result: { type: "number", options: { precision: 1 } },
    },
  },
  {
    name: "Brand Target Tier",
    type: "formula",
    description: "Text tier derived from Brand Target Score: A+ / A / B / C / D",
    options: {
      formula: `IF({Brand Target Score} >= 80, "A+",
IF({Brand Target Score} >= 60, "A",
IF({Brand Target Score} >= 40, "B",
IF({Brand Target Score} >= 20, "C",
"D"))))`,
      result: { type: "singleLineText" },
    },
  },
];
