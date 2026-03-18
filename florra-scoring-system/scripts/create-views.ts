/**
 * scripts/create-views.ts
 *
 * Creates Florra scoring views across People, Outreach, and Brand Targets.
 *
 * NOTE: The Airtable Meta API supports creating views (name + type only).
 * Filters and sorts must be applied manually in the Airtable UI after creation,
 * OR by using Airtable's web scripting block with the filter formulas provided
 * in src/view-definitions.ts.
 *
 * This script:
 *   1. Creates each view if it doesn't exist
 *   2. Prints the filter formula to apply manually
 *
 * Usage:
 *   npm run create-views
 *   DRY_RUN=true npm run create-views
 */

import { CONFIG } from "../src/config";
import { client } from "../src/client";
import { PEOPLE_VIEWS, OUTREACH_VIEWS, BRAND_TARGET_VIEWS } from "../src/view-definitions";
import type { ViewSpec, ViewResult } from "../src/types";
import chalk from "chalk";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statusColor(status: ViewResult["status"]): string {
  switch (status) {
    case "created":  return chalk.green(status);
    case "updated":  return chalk.yellow(status);
    case "skipped":  return chalk.gray(status);
    case "dry-run":  return chalk.cyan(status);
    case "error":    return chalk.red(status);
  }
}

// ─── Core logic ───────────────────────────────────────────────────────────────

async function processTable(
  tableName: string,
  tableId: string,
  views: ViewSpec[]
): Promise<ViewResult[]> {
  const results: ViewResult[] = [];

  console.log(chalk.blue(`\n━━ ${tableName} (${tableId}) ━━`));

  // Fetch existing views from schema
  const schema = await client.getBaseSchema();
  const table = schema.tables.find((t) => t.id === tableId);
  const existingViewNames = new Set(
    (table?.views ?? []).map((v) => v.name.toLowerCase())
  );

  for (const spec of views) {
    if (CONFIG.dryRun) {
      const exists = existingViewNames.has(spec.name.toLowerCase());
      console.log(
        `  [${chalk.cyan("dry-run")}] ${tableName} → ${chalk.bold(spec.name)} (${spec.type})` +
        (exists ? chalk.gray(" — already exists") : "")
      );
      if (spec.filterByFormula) {
        console.log(chalk.gray(`           filter: ${spec.filterByFormula.replace(/\n\s*/g, " ").slice(0, 80)}…`));
      }
      results.push({ table: tableName, view: spec.name, status: "dry-run" });
      continue;
    }

    if (existingViewNames.has(spec.name.toLowerCase())) {
      console.log(`  [${statusColor("skipped")}] ${tableName} → ${chalk.bold(spec.name)}`);
      results.push({ table: tableName, view: spec.name, status: "skipped" });
      continue;
    }

    try {
      await client.createView(tableId, { name: spec.name, type: spec.type });
      console.log(`  [${statusColor("created")}] ${tableName} → ${chalk.bold(spec.name)}`);
      if (spec.filterByFormula) {
        console.log(chalk.gray(`           ↳ Apply filter manually: ${spec.filterByFormula.trim().slice(0, 80)}`));
      }
      results.push({ table: tableName, view: spec.name, status: "created" });
    } catch (err) {
      const result: ViewResult = {
        table: tableName,
        view: spec.name,
        status: "error",
        error: err instanceof Error ? err.message : String(err),
      };
      console.log(
        `  [${statusColor("error")}] ${tableName} → ${chalk.bold(spec.name)} — ${chalk.red(result.error)}`
      );
      results.push(result);
    }
  }

  return results;
}

// ─── Manual filter guide ──────────────────────────────────────────────────────

function printManualFilterGuide(
  views: ViewSpec[],
  tableName: string
): void {
  const viewsWithFilters = views.filter((v) => v.filterByFormula);
  if (viewsWithFilters.length === 0) return;

  console.log(chalk.bold(`\n  📋 Manual filter formulas for ${tableName}:`));
  for (const v of viewsWithFilters) {
    console.log(chalk.yellow(`\n  View: "${v.name}"`));
    console.log(chalk.gray(`  ${v.filterByFormula}`));
    if (v.sorts && v.sorts.length > 0) {
      const sort = v.sorts[0];
      console.log(chalk.gray(`  Sort: ${sort.fieldName} ${sort.direction}`));
    }
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log(chalk.bold("\n🌸 Florra Scoring System — View Creation\n"));
  console.log(`  Base: ${CONFIG.airtable.baseId}`);
  console.log(`  Mode: ${CONFIG.dryRun ? chalk.cyan("DRY RUN") : chalk.green("LIVE")}\n`);

  const tables = [
    { name: "People",        id: CONFIG.tables.people,       views: PEOPLE_VIEWS },
    { name: "Outreach",      id: CONFIG.tables.outreach,     views: OUTREACH_VIEWS },
    { name: "Brand Targets", id: CONFIG.tables.brandTargets, views: BRAND_TARGET_VIEWS },
  ];

  const allResults: ViewResult[] = [];

  for (const table of tables) {
    const results = await processTable(table.name, table.id, table.views);
    allResults.push(...results);
  }

  // Print filter guide for manual application
  console.log(chalk.bold("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"));
  console.log(chalk.bold("MANUAL FILTER FORMULAS (copy into Airtable UI)"));
  console.log(chalk.bold("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"));
  for (const table of tables) {
    printManualFilterGuide(table.views, table.name);
  }

  // Summary
  const counts = allResults.reduce(
    (acc, r) => { acc[r.status] = (acc[r.status] ?? 0) + 1; return acc; },
    {} as Record<string, number>
  );

  console.log(chalk.bold("\n─── Summary ───────────────────────────────────────"));
  console.log(`  Total views processed: ${allResults.length}`);
  if (counts.created)  console.log(`  ${chalk.green("✓")} Created:  ${counts.created}`);
  if (counts.skipped)  console.log(`  ${chalk.gray("–")} Skipped:  ${counts.skipped}`);
  if (counts["dry-run"]) console.log(`  ${chalk.cyan("◌")} Dry-run:  ${counts["dry-run"]}`);
  if (counts.error)    console.log(`  ${chalk.red("✗")} Errors:   ${counts.error}`);

  console.log(chalk.green("\n✅ Done.\n"));
}

main().catch((err) => {
  console.error(chalk.red("\n✗ Fatal error:"), err.message);
  process.exit(1);
});
