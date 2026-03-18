# Florra Scoring System — Automation Specification

## Overview

These automations run inside Airtable (no code required) to keep the CRM
proactive. Each automation is described with trigger, conditions, actions,
and the exact notification text to use.

---

## PEOPLE TABLE AUTOMATIONS

### AUTO-01: Flag New A+ People

**Trigger:** When a record matches a condition
**Condition:** `{Florra Priority Tier}` is `A+`
**Frequency:** Check every hour (Airtable runs automations on save)

**Action 1 — Send Slack notification:**
```
🌟 New A+ Contact: {{Name}}
Score: {{Florra Priority Score}} | Tier: {{Florra Priority Tier}}
Relationship Stage: {{Relationship Stage}}
→ Review and initiate outreach in the next 24h
Airtable record: [link]
```

**Action 2 — Create linked Outreach record** (optional):
- Status: `New`
- Follow-Up Count: `0`
- Notes: `Auto-flagged: A+ tier reached. Initiate outreach.`

---

### AUTO-02: VIP Upgrade Notification

**Trigger:** When a record is updated
**Condition:** `{VIP}` changed to `checked`

**Action — Send email or Slack:**
```
💎 VIP Upgrade: {{Name}} has been marked as VIP.
Current Score: {{Florra Priority Score}}
→ Ensure they are in your weekly touch list.
```

---

### AUTO-03: Re-engagement Reminder (90-day stale)

**Trigger:** Scheduled automation — runs daily at 9:00 AM
**Find records where:**
```
AND(
  {Last Order Date},
  IS_BEFORE({Last Order Date}, DATEADD(TODAY(), -90, 'days')),
  OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A")
)
```

**Action — Send Slack digest:**
```
📅 Re-engagement Alert — {{Record Count}} high-value contacts are 90+ days stale.
Top priority: {{Name}} (last order: {{Last Order Date}})
→ Run re-engagement sequence or update Last Order Date.
```

---

## OUTREACH TABLE AUTOMATIONS

### AUTO-04: Deadline Alert (7-day warning)

**Trigger:** Scheduled automation — runs daily at 8:00 AM
**Find records where:**
```
AND(
  {Deadline},
  IS_BEFORE(TODAY(), DATEADD({Deadline}, 1, 'days')),
  IS_AFTER({Deadline}, DATEADD(TODAY(), -1, 'days')),
  DATETIME_DIFF({Deadline}, TODAY(), 'days') <= 7,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)
```

**Action — Send Slack notification per record:**
```
🚨 Deadline in {{DATETIME_DIFF({Deadline}, TODAY(), 'days')}} days: {{Name}}
Status: {{Status}} | Contract: {{Contract Status}}
Quoted Rate: {{Quoted Rate}}
→ Immediate action required.
```

---

### AUTO-05: Contract Follow-Up Reminder

**Trigger:** When record is updated
**Condition:** `{Contract Status}` changed to `Sent`

**Action — Create task / send reminder after 3 days:**
```
📄 Contract Sent Reminder: {{Name}}
Contract was sent on {{Last Modified Time}}.
→ Follow up if no response within 72 hours.
```

*(In Airtable, use the "Wait" step or schedule a 3-day delayed action.)*

---

### AUTO-06: Won Deal Celebration + CRM Update

**Trigger:** When record is updated
**Condition:** `{Status}` changed to `Closed Won`

**Action 1 — Send Slack:**
```
🎉 CLOSED WON: {{Name}}
Rate: {{Quoted Rate}} | Score: {{Outreach Priority Score}}
→ Update People record relationship stage to "Partner" or "Active".
→ Schedule post-campaign check-in in 30 days.
```

**Action 2 — Update linked People record:**
Set `{Relationship Stage}` → `Partner`
Set `{VIP}` → checked (if Quoted Rate ≥ $5,000)

---

### AUTO-07: Stale Outreach Alert (30-day no contact)

**Trigger:** Scheduled automation — runs Monday 9:00 AM
**Find records where:**
```
AND(
  {Last Follow-Up Date},
  DATETIME_DIFF(TODAY(), {Last Follow-Up Date}, 'days') > 30,
  {Status} != "Closed Won",
  {Status} != "Closed Lost"
)
```

**Action — Send Slack digest:**
```
💀 Stale Outreach Alert: {{Record Count}} deals have had no contact in 30+ days.
→ Review "💀 Stale Outreach" view and re-engage or close lost.
```

---

## BRAND TARGETS TABLE AUTOMATIONS

### AUTO-08: A+ Brand Target Alert

**Trigger:** When record matches a condition
**Condition:** `{Brand Target Tier}` is `A+`

**Action — Send Slack:**
```
💼 New A+ Brand Target: {{Brand Name}}
Score: {{Brand Target Score}} | Pipeline: {{Pipeline Stage}}
Budget: {{Estimated Budget}}
Decision Maker: {{Decision Maker Name}} ({{Decision Maker Email}})
→ Review and initiate pitch within 48h.
```

---

### AUTO-09: Pitch Stall Detection

**Trigger:** Scheduled automation — runs Wednesday 9:00 AM
**Find records where:**
```
AND(
  OR(
    {Pipeline Stage} = "Discovery",
    {Pipeline Stage} = "Proposal Sent"
  ),
  OR(
    NOT({Last Contact Date}),
    DATETIME_DIFF(TODAY(), {Last Contact Date}, 'days') > 14
  )
)
```

**Action — Send Slack:**
```
⚠️ Pitch Stall: {{Brand Name}} has been in {{Pipeline Stage}} for 14+ days without contact.
Last Contact: {{Last Contact Date}}
→ Send a check-in or move to next stage.
```

---

### AUTO-10: Decision Maker Missing on High-Priority Target

**Trigger:** When record is created OR updated
**Condition:**
```
AND(
  OR({Priority} = "Critical", {Priority} = "High"),
  OR({Decision Maker Name} = "", {Decision Maker Email} = "")
)
```

**Action — Send Slack:**
```
⚠️ Missing DM Info: {{Brand Name}} is marked {{Priority}} priority but lacks decision maker contact.
→ Research and add Decision Maker Name + Email before outreach.
```

---

## CAMPAIGNS TABLE AUTOMATIONS

### AUTO-11: Campaign Going Live (1-day reminder)

**Trigger:** Scheduled automation — runs daily at 7:00 AM
**Find records where:**
```
AND(
  {Launch Date},
  DATETIME_DIFF({Launch Date}, TODAY(), 'days') = 1,
  {Status} != "Live",
  {Status} != "Complete"
)
```

**Action — Send Slack:**
```
🚀 Campaign Goes Live TOMORROW: {{Campaign Name}}
Status: {{Status}} | Type: {{Campaign Type}}
→ Confirm all assets are uploaded and creators are briefed.
```

---

### AUTO-12: Campaign Completion Wrap-Up

**Trigger:** When record is updated
**Condition:** `{Status}` changed to `Complete`

**Action — Send Slack:**
```
✅ Campaign Complete: {{Campaign Name}}
→ Add final metrics (reach, engagement, conversions) within 48h.
→ Update linked People records with campaign participation tags.
```

---

## Implementation Notes

### Setting Up Airtable Automations
1. Go to **Automations** tab in your Airtable base
2. Click **+ New automation**
3. Select trigger type (When record matches, Scheduled, When record updated)
4. Add conditions using the formulas above
5. Add actions (Send Slack, Create record, Update record, Send email)
6. Name each automation with its AUTO-XX prefix for reference
7. Test with a sample record before enabling

### Slack Integration
- Requires Airtable's **Slack** action (available on Team+ plans)
- Connect your Slack workspace under **Integrations → Slack**
- Recommended channels:
  - `#crm-alerts` — People and Outreach automations
  - `#brand-targets` — Brand Target automations
  - `#campaigns` — Campaign automations

### Email Fallback
If Slack is not available, use the **Send email** action instead.
Set recipients to relevant team members.

### Rate Limits
Airtable automations run up to 25,000 runs/month on Team plan.
Scheduled automations count once per run regardless of records found.
Record-triggered automations count once per record that triggers them.
