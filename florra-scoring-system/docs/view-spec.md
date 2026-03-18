# Florra Scoring System — View Specification

## Setup Instructions

The Airtable Meta API supports creating views by name + type. Filter formulas
and sort orders must be applied in the Airtable UI after creation.

**Steps:**
1. Run `npm run create-views` to create all views
2. Open each view in Airtable
3. Apply the filter formula from this doc (Filter → Condition → Formula)
4. Apply the sort order described below
5. Save the view

---

## People Table Views

### 1. 🌟 A+ Priority People

**Type:** Grid
**Purpose:** Top-tier contacts scoring ≥90. Review and action weekly.

**Filter formula:**
```
{Florra Priority Tier} = "A+"
```

**Sort:** `Florra Priority Score` → Z→A (descending)

**Suggested fields to show:**
- Name, Florra Priority Score, Florra Priority Tier, Relationship Stage, Followers, Last Order Date, Last Contacted

---

### 2. 💎 VIP Contacts

**Type:** Grid
**Purpose:** All VIP-flagged contacts regardless of score.

**Filter formula:**
```
{VIP} = 1
```

**Sort:** `Florra Priority Score` → Z→A (descending)

---

### 3. 🔥 High Value Pipeline (A/A+)

**Type:** Grid
**Purpose:** All A and A+ contacts. Core weekly engagement list.

**Filter formula:**
```
OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A")
```

**Sort:** `Florra Priority Score` → Z→A (descending)

---

### 4. 🧊 Cold / Deprioritized

**Type:** Grid
**Purpose:** D-tier contacts for nurture sequences or archive review.

**Filter formula:**
```
{Florra Priority Tier} = "D"
```

**Sort:** `Florra Priority Score` → A→Z (ascending)

---

### 5. 📅 Needs Re-engagement (Stale >90d)

**Type:** Grid
**Purpose:** High-value contacts who haven't ordered in 90+ days — prime re-engagement targets.

**Filter formula:**
```
AND(
  {Last Order Date},
  DATETIME_DIFF(TODAY(), {Last Order Date}, 'days') > 90,
  OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A", {Florra Priority Tier} = "B")
)
```

**Sort:** `Last Order Date` → A→Z (oldest first)

---

## Outreach Table Views

### 1. 🚨 Urgent — Deadline This Week

**Type:** Grid
**Purpose:** Active deals with deadlines in the next 7 days.

**Filter formula:**
```
AND(
  {Deadline},
  DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 7,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)
```

**Sort:** `Deadline` → A→Z (soonest first)

---

### 2. 🏆 A+ Outreach

**Type:** Grid
**Purpose:** Highest-priority outreach threads — act today.

**Filter formula:**
```
{Outreach Priority Tier} = "A+"
```

**Sort:** `Outreach Priority Score` → Z→A (descending)

---

### 3. 📬 Needs Follow-Up (0 touches)

**Type:** Grid
**Purpose:** Outreach records with zero follow-ups sent — these are overdue.

**Filter formula:**
```
AND(
  {Follow-Up Count} = 0,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)
```

**Sort:** `Outreach Priority Score` → Z→A (descending)

---

### 4. 🤝 Contract Pending

**Type:** Grid
**Purpose:** Deals with contracts currently in-flight (Drafting / Sent / Negotiating).

**Filter formula:**
```
OR(
  {Contract Status} = "Sent",
  {Contract Status} = "Negotiating",
  {Contract Status} = "Drafting"
)
```

**Sort:** `Deadline` → A→Z (soonest first)

---

### 5. 💀 Stale Outreach (>30d no contact)

**Type:** Grid
**Purpose:** Active deals with no contact in 30+ days — at risk of going cold.

**Filter formula:**
```
AND(
  {Last Follow-Up Date},
  DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') > 30,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)
```

**Sort:** `Last Follow-Up Date` → A→Z (oldest first)

---

## Brand Targets Table Views

### 1. 💼 A+ Brand Targets

**Type:** Grid
**Purpose:** Highest-value brand partnership targets.

**Filter formula:**
```
{Brand Target Tier} = "A+"
```

**Sort:** `Brand Target Score` → Z→A (descending)

---

### 2. 🎯 Pitch Ready (Stage: Discovery+)

**Type:** Grid
**Purpose:** Brands in active pipeline stages where pitch work is happening now.

**Filter formula:**
```
OR(
  {Pipeline Stage} = "Discovery",
  {Pipeline Stage} = "Proposal Sent",
  {Pipeline Stage} = "Negotiating",
  {Pipeline Stage} = "Contract Out"
)
```

**Sort:** `Brand Target Score` → Z→A (descending)

---

### 3. 📋 Missing Decision Maker Info

**Type:** Grid
**Purpose:** High-priority targets where DM contact data is incomplete — fill this in before outreach.

**Filter formula:**
```
OR(
  {Decision Maker Name} = "",
  {Decision Maker Email} = ""
)
```

**Sort:** `Brand Target Score` → Z→A (descending)

---

### 4. 🥶 Cold / Uncontacted (>60d)

**Type:** Grid
**Purpose:** Brands not contacted in 60+ days.

**Filter formula:**
```
OR(
  NOT({Last Contact Date}),
  DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') > 60
)
```

**Sort:** `Brand Target Score` → Z→A (descending)

---

### 5. 🏁 Pipeline Board (All Stages)

**Type:** Kanban
**Purpose:** Visual board of all brand targets grouped by Pipeline Stage.

**Group by:** `Pipeline Stage`
**Filter formula:** (no filter — show all)

**Sort:** `Brand Target Score` → Z→A (descending)

**Kanban column order:** Cold Lead → Prospect → Discovery → Proposal Sent → Negotiating → Contract Out → Closed Won
