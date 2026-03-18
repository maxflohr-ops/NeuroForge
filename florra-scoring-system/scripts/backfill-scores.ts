/**
 * scripts/backfill-scores.ts
 *
 * For formula fields that Airtable should compute automatically, this script
 * verifies that computed values are consistent across all records and flags
 * anomalies. It does NOT overwrite formula fields (Airtable disallows writing
 * to formula fields via the API) — instead it:
 *
 *   1. Reads all records with their computed score fields
 *   2. Validates expected tier vs actual tier
 *   3. Reports records where score ≠ tier (indicating formula misconfiguration)
 *   4. Optionally writes a "Score Verified" checkbox or "Score Verified Date" field
 *      to mark records as audited
 *
 * Usage:
 *   npm run backfill-scores
 *   DRY_RUN=true npm run backfill-scores
 *   npm run backfill-scores -- --table people
 *   npm run backfill-scores -- --table outreach
 *   npm run backfill-scores -- --table brands
 */

import { CONFIG } from "../src/config";
import { client } from "../src/client";
import chalk from "chalk";

// ─── CLI args ─────────────────────────────────────────────────────────────────

const tableArg = ((): string | null => {
  const idx = process.argv.indexOf("--table");
  return idx !== -1 ? process.argv[idx + 1] : null;
})();

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScoreAuditResult {
  recordId: string;
  name: string;
  score: number;
  tier: string;
  expectedTier: string;
  valid: boolean;
  anomalyReason?: string;
}

interface TableAudit {
  tableName: string;
  total: number;
  valid: number;
  anomalies: ScoreAuditResult[];
}

// ─── Tier calculators (mirrors Airtable formulas) ────────────────────────────

function peopleExpectedTier(score: number): string {
  if (score >= 90) return "A+";
  if (score >= 70) return "A";
  if (score >= 50) return "B";
  if (score >= 30) return "C";
  return "D";
}

function outreachExpectedTier(score: number): string {
  if (score >= 85) return "A+";
  if (score >= 65) return "A";
  if (score >= 45) return "B";
  if (score >= 25) return "C";
  return "D";
}

function brandExpectedTier(score: number): string {
  if (score >= 80) return "A+";
  if (score >= 60) return "A";
  if (score >= 40) return "B";
  if (score >= 20) return "C";
  return "D";
}

// ─── Audit functions ─────────────────────────────────────────────────────────

async function auditPeople(): Promise<TableAudit> {
  const records = await client.listRecords<Record<string, unknown>>(
    CONFIG.tables.people,
    {
      fields: ["Name", "Florra Priority Score", "Florra Priority Tier"],
    }
  );

  const results: ScoreAuditResult[] = records.map((r) => {
    const name  = String(r.fields["Name"] ?? r.id);
    const score = Number(r.fields["Florra Priority Score"] ?? 0);
    const tier  = String(r.fields["Florra Priority Tier"] ?? "");
    const expectedTier = peopleExpectedTier(score);
    const valid = tier === expectedTier;

    return {
      recordId: r.id,
      name,
      score,
      tier,
      expectedTier,
      valid,
      anomalyReason: valid
        ? undefined
        : `Score ${score} → expected tier ${expectedTier}, got "${tier}"`,
    };
  });

  return {
    tableName: "People",
    total: results.length,
    valid: results.filter((r) => r.valid).length,
    anomalies: results.filter((r) => !r.valid),
  };
}

async function auditOutreach(): Promise<TableAudit> {
  const records = await client.listRecords<Record<string, unknown>>(
    CONFIG.tables.outreach,
    {
      fields: ["Name", "Outreach Priority Score", "Outreach Priority Tier"],
    }
  );

  const results: ScoreAuditResult[] = records.map((r) => {
    const name  = String(r.fields["Name"] ?? r.id);
    const score = Number(r.fields["Outreach Priority Score"] ?? 0);
    const tier  = String(r.fields["Outreach Priority Tier"] ?? "");
    const expectedTier = outreachExpectedTier(score);
    const valid = tier === expectedTier;

    return {
      recordId: r.id,
      name,
      score,
      tier,
      expectedTier,
      valid,
      anomalyReason: valid
        ? undefined
        : `Score ${score} → expected tier ${expectedTier}, got "${tier}"`,
    };
  });

  return {
    tableName: "Outreach",
    total: results.length,
    valid: results.filter((r) => r.valid).length,
    anomalies: results.filter((r) => !r.valid),
  };
}

async function auditBrandTargets(): Promise<TableAudit> {
  const records = await client.listRecords<Record<string, unknown>>(
    CONFIG.tables.brandTargets,
    {
      fields: ["Brand Name", "Brand Target Score", "Brand Target Tier"],
    }
  );

  const results: ScoreAuditResult[] = records.map((r) => {
    const name  = String(r.fields["Brand Name"] ?? r.id);
    const score = Number(r.fields["Brand Target Score"] ?? 0);
    const tier  = String(r.fields["Brand Target Tier"] ?? "");
    const expectedTier = brandExpectedTier(score);
    const valid = tier === expectedTier;

    return {
      recordId: r.id,
      name,
      score,
      tier,
      expectedTier,
      valid,
      anomalyReason: valid
        ? undefined
        : `Score ${score} → expected tier ${expectedTier}, got "${tier}"`,
    };
  });

  return {
    tableName: "Brand Targets",
    total: results.length,
    valid: results.filter((r) => r.valid).length,
    anomalies: results.filter((r) => !r.valid),
  };
}

// ─── Score distribution ───────────────────────────────────────────────────────

function printDistribution(
  records: Array<{ score: number }>,
  tierFn: (s: number) => string
): void {
  const dist: Record<string, number> = {};
  for (const r of records) {
    const t = tierFn(r.score);
    dist[t] = (dist[t] ?? 0) + 1;
  }

  const tiers = ["A+", "A", "B", "C", "D"];
  for (const tier of tiers) {
    const count = dist[tier] ?? 0;
    const bar = "█".repeat(Math.min(count, 40));
    const color =
      tier === "A+" ? chalk.green :
      tier === "A"  ? chalk.greenBright :
      tier === "B"  ? chalk.yellow :
      tier === "C"  ? chalk.gray :
      chalk.red;
    console.log(`  ${color(tier.padEnd(3))} ${bar} ${count}`);
  }
}

// ─── Report printer ───────────────────────────────────────────────────────────

function printAudit(audit: TableAudit): void {
  const pct = audit.total > 0
    ? ((audit.valid / audit.total) * 100).toFixed(1)
    : "0.0";

  const statusIcon = audit.anomalies.length === 0
    ? chalk.green("✓")
    : chalk.red("✗");

  console.log(
    `\n${chalk.bold(audit.tableName)}: ${statusIcon} ${audit.valid}/${audit.total} valid (${pct}%)`
  );

  if (audit.anomalies.length > 0) {
    console.log(chalk.red(`  ${audit.anomalies.length} anomalies detected:`));
    for (const a of audit.anomalies.slice(0, 20)) {
      console.log(chalk.red(`  ✗ [${a.recordId}] ${a.name}`));
      console.log(chalk.gray(`      ${a.anomalyReason}`));
    }
    if (audit.anomalies.length > 20) {
      console.log(chalk.gray(`  … and ${audit.anomalies.length - 20} more`));
    }
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log(chalk.bold("\n🌸 Florra — Score Backfill & Audit\n"));
  console.log(`  Mode:  ${CONFIG.dryRun ? chalk.cyan("DRY RUN") : chalk.green("LIVE")}`);
  console.log(`  Table: ${tableArg ?? "all"}\n`);

  const audits: TableAudit[] = [];

  const run = (name: string) =>
    !tableArg || tableArg === name;

  if (run("people")) {
    console.log(chalk.blue("Auditing People…"));
    audits.push(await auditPeople());
  }

  if (run("outreach")) {
    console.log(chalk.blue("Auditing Outreach…"));
    audits.push(await auditOutreach());
  }

  if (run("brands") || run("brand-targets")) {
    console.log(chalk.blue("Auditing Brand Targets…"));
    audits.push(await auditBrandTargets());
  }

  console.log(chalk.bold("\n══ Audit Results ═══════════════════════════════════"));

  for (const audit of audits) {
    printAudit(audit);
  }

  const totalAnomalies = audits.reduce((s, a) => s + a.anomalies.length, 0);
  const totalRecords   = audits.reduce((s, a) => s + a.total, 0);

  console.log(chalk.bold("\n─── Summary ───────────────────────────────────────"));
  console.log(`  Records audited: ${totalRecords}`);
  console.log(
    totalAnomalies === 0
      ? chalk.green(`  ✓ All scores and tiers are consistent`)
      : chalk.red(`  ✗ ${totalAnomalies} inconsistencies found — check formula definitions`)
  );

  if (totalAnomalies > 0) {
    console.log(chalk.yellow("\n  Fix: Re-run `npm run create-fields` to update the formula fields."));
    console.log(chalk.yellow("  Then re-run this audit to verify.\n"));
    process.exit(1);
  }

  console.log(chalk.green("\n✅ Audit complete.\n"));
}

main().catch((err) => {
  console.error(chalk.red("\n✗ Fatal error:"), err.message);
  process.exit(1);
});
