import * as dotenv from "dotenv";
dotenv.config();

function require_env(key: string): string {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required environment variable: ${key}`);
  return val;
}

export const CONFIG = {
  airtable: {
    pat: require_env("AIRTABLE_PAT"),
    baseId: require_env("AIRTABLE_BASE_ID"),
  },
  tables: {
    people: require_env("PEOPLE_TABLE_ID"),
    outreach: require_env("OUTREACH_TABLE_ID"),
    brandTargets: require_env("BRAND_TARGETS_TABLE_ID"),
    campaigns: require_env("CAMPAIGNS_TABLE_ID"),
  },
  dryRun: process.env.DRY_RUN === "true",
  rateLimitRps: parseInt(process.env.RATE_LIMIT_RPS ?? "4", 10),
  backfillBatchSize: parseInt(process.env.BACKFILL_BATCH_SIZE ?? "10", 10),
} as const;

export type TableKey = keyof typeof CONFIG.tables;
