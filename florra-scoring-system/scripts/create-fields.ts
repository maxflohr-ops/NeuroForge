/**
 * scripts/create-fields.ts
 *
 * Creates (or updates) all Florra scoring formula fields across the three
 * core tables: People, Outreach, and Brand Targets.
 *
 * Usage:
 *   npm run create-fields                   # live run
 *   DRY_RUN=true npm run create-fields      # print plan without writing
 *
 * ─── PAT INSERTION POINT ─────────────────────────────────────────────────
 * Ensure AIRTABLE_PAT is set in your .env before running.
 * ──────────────────────────────────────────────────────────────────────────
 */

import { CONFIG } from "../src/config";
import { client } from "../src/client";
import { PEOPLE_FIELDS } from "../src/field-definitions";
import { OUTREACH_FIELDS } from "../src/field-definitions";
import { BRAND_TARGET_FIELDS } from "../src/field-definitions";
import type { FieldSpec, FieldResult } from "../src/types";
import chalk from "chalk";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function statusColor(status: FieldResult["status"]): string {
  switch (status) {
    case "created":   return chalk.green(status);
    case "updated":   return chalk.yellow(status);
    case "skipped":   return chalk.gray(status);
    case "dry-run":   return chalk.cyan(status);
    case "error":     return chalk.red(status);
  }
}

function printResult(r: FieldResult): void {
  console.log(
    `  [${statusColor(r.status)}] ${r.table} → ${chalk.bold(r.field)}` +
    (r.error ? chalk.red(`  ERROR: ${r.error}`) : "")
  );
}

// ─── Core logic ──────────────────────────────────────────────────────────────

async function processTable(
  tableName: string,
  tableId: string,
  fields: FieldSpec[]
): Promise<FieldResult[]> {
  const results: FieldResult[] = [];

  console.log(chalk.blue(`\n━━ ${tableName} (${tableId}) ━━`));

  for (const spec of fields) {
    if (CONFIG.dryRun) {
      console.log(`  [${chalk.cyan("dry-run")}] ${tableName} → ${chalk.bold(spec.name)}`);
      console.log(chalk.gray(`           type: ${spec.type}`));
      if (spec.options?.formula) {
        const preview = spec.options.formula.replace(/\n\s*/g, " ").slice(0, 80);
        console.log(chalk.gray(`           formula: ${preview}${spec.options.formula.length > 80 ? "…" : ""}`));
      }
      results.push({ table: tableName, field: spec.name, status: "dry-run" });
      continue;
    }

    try {
      const { action } = await client.upsertField(tableId, spec);
      const result: FieldResult = {
        table: tableName,
        field: spec.name,
        status: action,
      };
      printResult(result);
      results.push(result);
    } catch (err) {
      const result: FieldResult = {
        table: tableName,
        field: spec.name,
        status: "error",
        error: err instanceof Error ? err.message : String(err),
      };
      printResult(result);
      results.push(result);
    }
  }

  return results;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log(chalk.bold("\n🌸 Florra Scoring System — Field Creation\n"));
  console.log(`  Base:    ${CONFIG.airtable.baseId}`);
  console.log(`  Mode:    ${CONFIG.dryRun ? chalk.cyan("DRY RUN") : chalk.green("LIVE")}`);
  console.log(`  PAT:     ${CONFIG.airtable.pat.slice(0, 8)}…\n`);

  const tables = [
    { name: "People",        id: CONFIG.tables.people,       fields: PEOPLE_FIELDS },
    { name: "Outreach",      id: CONFIG.tables.outreach,     fields: OUTREACH_FIELDS },
    { name: "Brand Targets", id: CONFIG.tables.brandTargets, fields: BRAND_TARGET_FIELDS },
  ];

  const allResults: FieldResult[] = [];

  for (const table of tables) {
    const results = await processTable(table.name, table.id, table.fields);
    allResults.push(...results);
  }

  // Summary
  const counts = allResults.reduce(
    (acc, r) => { acc[r.status] = (acc[r.status] ?? 0) + 1; return acc; },
    {} as Record<string, number>
  );

  console.log(chalk.bold("\n─── Summary ───────────────────────────────────────"));
  console.log(`  Total fields processed: ${allResults.length}`);
  if (counts.created)  console.log(`  ${chalk.green("✓")} Created:  ${counts.created}`);
  if (counts.updated)  console.log(`  ${chalk.yellow("↻")} Updated:  ${counts.updated}`);
  if (counts.skipped)  console.log(`  ${chalk.gray("–")} Skipped:  ${counts.skipped}`);
  if (counts["dry-run"]) console.log(`  ${chalk.cyan("◌")} Dry-run:  ${counts["dry-run"]}`);
  if (counts.error)    console.log(`  ${chalk.red("✗")} Errors:   ${counts.error}`);

  const errorFields = allResults.filter((r) => r.status === "error");
  if (errorFields.length > 0) {
    console.log(chalk.red("\n⚠  Some fields failed. Check errors above."));
    process.exit(1);
  }

  console.log(chalk.green("\n✅ Done.\n"));
}

main().catch((err) => {
  console.error(chalk.red("\n✗ Fatal error:"), err.message);
  process.exit(1);
});
