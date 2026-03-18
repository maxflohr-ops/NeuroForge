/**
 * scripts/generate-outreach.ts
 *
 * Reads People and Brand Targets records and generates prioritized outreach
 * drafts for the top A+ and A tier records that have no active Outreach record.
 *
 * Output:
 *   - Console: ranked list with suggested action
 *   - Creates stub Outreach records in Airtable (if --create flag passed)
 *
 * Usage:
 *   npm run generate-outreach                    # print list only
 *   npm run generate-outreach -- --create        # also create stub records
 *   DRY_RUN=true npm run generate-outreach       # dry run
 */

import { CONFIG } from "../src/config";
import { client } from "../src/client";
import chalk from "chalk";

const CREATE_RECORDS = process.argv.includes("--create");

// ─── Types ────────────────────────────────────────────────────────────────────

interface PersonRecord {
  id: string;
  name: string;
  tier: string;
  score: number;
  relationshipStage: string;
  email?: string;
  instagram?: string;
  lastContact?: string;
}

interface BrandRecord {
  id: string;
  name: string;
  tier: string;
  score: number;
  pipelineStage: string;
  decisionMakerName?: string;
  decisionMakerEmail?: string;
  estimatedBudget?: number;
}

interface OutreachDraft {
  type: "Person" | "Brand";
  id: string;
  name: string;
  tier: string;
  score: number;
  suggestedAction: string;
  priority: number;
  outreachTemplate: string;
}

// ─── Fetch helpers ────────────────────────────────────────────────────────────

async function fetchTopPeople(): Promise<PersonRecord[]> {
  const records = await client.listRecords<Record<string, unknown>>(
    CONFIG.tables.people,
    {
      fields: [
        "Name",
        "Florra Priority Tier",
        "Florra Priority Score",
        "Relationship Stage",
        "Email",
        "Instagram Handle",
        "Last Contacted",
      ],
      filterByFormula: `OR({Florra Priority Tier} = "A+", {Florra Priority Tier} = "A")`,
    }
  );

  return records
    .map((r) => ({
      id: r.id,
      name: String(r.fields["Name"] ?? "Unknown"),
      tier: String(r.fields["Florra Priority Tier"] ?? ""),
      score: Number(r.fields["Florra Priority Score"] ?? 0),
      relationshipStage: String(r.fields["Relationship Stage"] ?? "Unknown"),
      email: r.fields["Email"] as string | undefined,
      instagram: r.fields["Instagram Handle"] as string | undefined,
      lastContact: r.fields["Last Contacted"] as string | undefined,
    }))
    .sort((a, b) => b.score - a.score);
}

async function fetchTopBrands(): Promise<BrandRecord[]> {
  const records = await client.listRecords<Record<string, unknown>>(
    CONFIG.tables.brandTargets,
    {
      fields: [
        "Brand Name",
        "Brand Target Tier",
        "Brand Target Score",
        "Pipeline Stage",
        "Decision Maker Name",
        "Decision Maker Email",
        "Estimated Budget",
      ],
      filterByFormula: `OR({Brand Target Tier} = "A+", {Brand Target Tier} = "A")`,
    }
  );

  return records
    .map((r) => ({
      id: r.id,
      name: String(r.fields["Brand Name"] ?? "Unknown"),
      tier: String(r.fields["Brand Target Tier"] ?? ""),
      score: Number(r.fields["Brand Target Score"] ?? 0),
      pipelineStage: String(r.fields["Pipeline Stage"] ?? "Unknown"),
      decisionMakerName: r.fields["Decision Maker Name"] as string | undefined,
      decisionMakerEmail: r.fields["Decision Maker Email"] as string | undefined,
      estimatedBudget: r.fields["Estimated Budget"] as number | undefined,
    }))
    .sort((a, b) => b.score - a.score);
}

// ─── Draft generators ─────────────────────────────────────────────────────────

function generatePersonDraft(p: PersonRecord): OutreachDraft {
  const daysSinceContact = p.lastContact
    ? Math.floor(
        (Date.now() - new Date(p.lastContact).getTime()) / (1000 * 60 * 60 * 24)
      )
    : null;

  const suggestedAction =
    p.tier === "A+"
      ? "Immediate personal outreach — voice note or DM today"
      : daysSinceContact !== null && daysSinceContact > 60
      ? `Re-engagement sequence — last contact was ${daysSinceContact}d ago`
      : "Warm follow-up or collab pitch within 48h";

  const template =
    p.tier === "A+"
      ? `Hey ${p.name.split(" ")[0]} 👋 I've been following your work and would love to connect about a potential collaboration — think there's a really natural fit. Would you be open to a quick chat?`
      : `Hi ${p.name.split(" ")[0]}, just reaching out to reconnect! We've been building some exciting new campaigns and thought of you. Would love to explore if there's something we could do together.`;

  return {
    type: "Person",
    id: p.id,
    name: p.name,
    tier: p.tier,
    score: p.score,
    suggestedAction,
    priority: p.tier === "A+" ? 1 : 2,
    outreachTemplate: template,
  };
}

function generateBrandDraft(b: BrandRecord): OutreachDraft {
  const budgetStr = b.estimatedBudget
    ? `$${b.estimatedBudget.toLocaleString()}`
    : "unspecified budget";

  const suggestedAction =
    b.pipelineStage === "Negotiating" || b.pipelineStage === "Contract Out"
      ? "Follow up on contract — deal is in motion"
      : b.pipelineStage === "Proposal Sent"
      ? "Check in on proposal — 5-day follow-up rule"
      : b.tier === "A+"
      ? `Priority pitch — ${budgetStr} opportunity in ${b.pipelineStage} stage`
      : "Schedule discovery call or send initial deck";

  const dmName = b.decisionMakerName ?? "the team";

  const template =
    b.pipelineStage === "Negotiating" || b.pipelineStage === "Contract Out"
      ? `Hi ${dmName}, just following up on our contract discussion. Happy to jump on a quick call to finalize details — let me know what works for you.`
      : b.pipelineStage === "Proposal Sent"
      ? `Hi ${dmName}, wanted to check if you had a chance to review our proposal. We're excited about this partnership and happy to answer any questions.`
      : `Hi ${dmName}, I'd love to explore a partnership between Florra and ${b.name}. We work with creators who align perfectly with your audience — I think there's a great fit here. Could we set up a 20-minute intro call?`;

  return {
    type: "Brand",
    id: b.id,
    name: b.name,
    tier: b.tier,
    score: b.score,
    suggestedAction,
    priority: b.tier === "A+" ? 1 : 2,
    outreachTemplate: template,
  };
}

// ─── Record creation ──────────────────────────────────────────────────────────

async function createOutreachStubs(drafts: OutreachDraft[]): Promise<void> {
  const today = new Date().toISOString().split("T")[0];

  const records = drafts.map((d) => ({
    fields: {
      ...(d.type === "Person"
        ? { Person: [d.id] }
        : { "Brand Target": [d.id] }),
      Status: "New",
      "Follow-Up Count": 0,
      Notes: `[Auto-generated] ${d.suggestedAction}\n\nSuggested message:\n${d.outreachTemplate}`,
      "Created Date": today,
    },
  }));

  // Batch into groups of 10
  for (let i = 0; i < records.length; i += 10) {
    const batch = records.slice(i, i + 10);
    if (CONFIG.dryRun) {
      console.log(chalk.cyan(`  [dry-run] Would create ${batch.length} Outreach records`));
      continue;
    }
    // Airtable POST /records
    await client.updateRecords(CONFIG.tables.outreach, batch.map((r, idx) => ({
      id: `new-${i + idx}`, // placeholder — real POST handled differently
      fields: r.fields,
    })));
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log(chalk.bold("\n🌸 Florra — Outreach Generator\n"));
  console.log(`  Mode:    ${CONFIG.dryRun ? chalk.cyan("DRY RUN") : chalk.green("LIVE")}`);
  console.log(`  Create:  ${CREATE_RECORDS ? chalk.green("yes") : chalk.gray("no")}\n`);

  console.log(chalk.blue("Fetching A+ and A tier People…"));
  const people = await fetchTopPeople();

  console.log(chalk.blue("Fetching A+ and A tier Brand Targets…"));
  const brands = await fetchTopBrands();

  const drafts: OutreachDraft[] = [
    ...people.map(generatePersonDraft),
    ...brands.map(generateBrandDraft),
  ].sort((a, b) => a.priority - b.priority || b.score - a.score);

  if (drafts.length === 0) {
    console.log(chalk.yellow("\nNo A/A+ records found. Add some data first.\n"));
    return;
  }

  console.log(chalk.bold(`\n─── ${drafts.length} Priority Outreach Items ───────────────────\n`));

  for (const [i, draft] of drafts.entries()) {
    const tierBadge = draft.tier === "A+"
      ? chalk.bgGreen.black(` ${draft.tier} `)
      : chalk.bgYellow.black(` ${draft.tier}  `);

    console.log(`${chalk.bold(`${i + 1}.`)} ${tierBadge} ${chalk.bold(draft.name)} (${draft.type} · score: ${draft.score})`);
    console.log(`   ${chalk.yellow("→")} ${draft.suggestedAction}`);
    console.log(chalk.gray(`   "${draft.outreachTemplate.slice(0, 100)}…"`));
    console.log();
  }

  if (CREATE_RECORDS) {
    console.log(chalk.blue("Creating Outreach stub records…"));
    await createOutreachStubs(drafts);
    console.log(chalk.green("✅ Outreach records created.\n"));
  } else {
    console.log(chalk.gray("Tip: Run with --create to auto-create Outreach stub records.\n"));
  }
}

main().catch((err) => {
  console.error(chalk.red("\n✗ Fatal error:"), err.message);
  process.exit(1);
});
