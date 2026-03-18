/**
 * Florra Scoring System — View Definitions
 *
 * Views use filterByFormula strings that Airtable evaluates at render time.
 * The Airtable Meta API (POST /views) supports creating grid views with a name
 * and type; filter/sort must be applied via the UI or by updating the view
 * after creation. The filterByFormula here documents the intended filter
 * to apply manually or via a future API that supports it.
 */

import type { ViewSpec } from "./types";

// ─────────────────────────────────────────────────────────────────────────────
// PEOPLE TABLE VIEWS
// ─────────────────────────────────────────────────────────────────────────────

export const PEOPLE_VIEWS: ViewSpec[] = [
  {
    name: "🌟 A+ Priority People",
    type: "grid",
    filterByFormula: `{Florra Priority Tier} = "A+"`,
    sorts: [{ fieldName: "Florra Priority Score", direction: "desc" }],
    description: "Top-tier contacts scoring ≥90. Review and activate weekly.",
  },
  {
    name: "💎 VIP Contacts",
    type: "grid",
    filterByFormula: `{VIP} = 1`,
    sorts: [{ fieldName: "Florra Priority Score", direction: "desc" }],
    description: "All VIP-flagged contacts regardless of score.",
  },
  {
    name: "🔥 High Value Pipeline (A/A+)",
    type: "grid",
    filterByFormula: `OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A")`,
    sorts: [{ fieldName: "Florra Priority Score", direction: "desc" }],
    description: "All A and A+ contacts. Core engagement list.",
  },
  {
    name: "🧊 Cold / Deprioritized",
    type: "grid",
    filterByFormula: `{Florra Priority Tier} = "D"`,
    sorts: [{ fieldName: "Florra Priority Score", direction: "asc" }],
    description: "D-tier contacts for nurture sequences or archive.",
  },
  {
    name: "📅 Needs Re-engagement (Stale >90d)",
    type: "grid",
    filterByFormula: `AND(
  {Last Order Date},
  DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') > 90,
  OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A", {Florra Priority Tier} = "B")
)`,
    sorts: [{ fieldName: "Last Order Date", direction: "asc" }],
    description: "High-value contacts who haven't ordered in 90+ days.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// OUTREACH TABLE VIEWS
// ─────────────────────────────────────────────────────────────────────────────

export const OUTREACH_VIEWS: ViewSpec[] = [
  {
    name: "🚨 Urgent — Deadline This Week",
    type: "grid",
    filterByFormula: `AND(
  {Deadline},
  DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 7,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)`,
    sorts: [{ fieldName: "Deadline", direction: "asc" }],
    description: "Active deals with deadlines in the next 7 days.",
  },
  {
    name: "🏆 A+ Outreach",
    type: "grid",
    filterByFormula: `{Outreach Priority Tier} = "A+"`,
    sorts: [{ fieldName: "Outreach Priority Score", direction: "desc" }],
    description: "Highest-priority outreach threads — act today.",
  },
  {
    name: "📬 Needs Follow-Up (0 touches)",
    type: "grid",
    filterByFormula: `AND(
  {Follow-Up Count} = 0,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)`,
    sorts: [{ fieldName: "Outreach Priority Score", direction: "desc" }],
    description: "Outreach records with zero follow-ups sent.",
  },
  {
    name: "🤝 Contract Pending",
    type: "grid",
    filterByFormula: `OR(
  {Contract Status} = "Sent",
  {Contract Status} = "Negotiating",
  {Contract Status} = "Drafting"
)`,
    sorts: [{ fieldName: "Deadline", direction: "asc" }],
    description: "Deals with contracts in-flight.",
  },
  {
    name: "💀 Stale Outreach (>30d no contact)",
    type: "grid",
    filterByFormula: `AND(
  {Last Follow-Up Date},
  DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') > 30,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)`,
    sorts: [{ fieldName: "Last Follow-Up Date", direction: "asc" }],
    description: "Active deals with no contact in 30+ days.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// BRAND TARGETS TABLE VIEWS
// ─────────────────────────────────────────────────────────────────────────────

export const BRAND_TARGET_VIEWS: ViewSpec[] = [
  {
    name: "💼 A+ Brand Targets",
    type: "grid",
    filterByFormula: `{Brand Target Tier} = "A+"`,
    sorts: [{ fieldName: "Brand Target Score", direction: "desc" }],
    description: "Highest-value brand partnership targets.",
  },
  {
    name: "🎯 Pitch Ready (Stage: Discovery+)",
    type: "grid",
    filterByFormula: `OR(
  {Pipeline Stage} = "Discovery",
  {Pipeline Stage} = "Proposal Sent",
  {Pipeline Stage} = "Negotiating",
  {Pipeline Stage} = "Contract Out"
)`,
    sorts: [{ fieldName: "Brand Target Score", direction: "desc" }],
    description: "Brands in active pipeline stages — prioritize pitch prep.",
  },
  {
    name: "📋 Missing Decision Maker Info",
    type: "grid",
    filterByFormula: `OR(
  {Decision Maker Name} = "",
  {Decision Maker Email} = ""
)`,
    sorts: [{ fieldName: "Brand Target Score", direction: "desc" }],
    description: "High-priority targets with incomplete DM contact data.",
  },
  {
    name: "🥶 Cold / Uncontacted (>60d)",
    type: "grid",
    filterByFormula: `OR(
  NOT({Last Contact Date}),
  DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') > 60
)`,
    sorts: [{ fieldName: "Brand Target Score", direction: "desc" }],
    description: "Brands not contacted in 60+ days.",
  },
  {
    name: "🏁 Pipeline Board (All Stages)",
    type: "kanban",
    filterByFormula: `{Pipeline Stage} != ""`,
    sorts: [{ fieldName: "Brand Target Score", direction: "desc" }],
    description: "Kanban board grouped by Pipeline Stage.",
  },
];
