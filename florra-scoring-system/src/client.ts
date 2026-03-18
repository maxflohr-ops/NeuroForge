/**
 * Airtable REST client for Meta API (schema) and Data API (records).
 *
 * ─── PAT / MCP INSERTION POINT ────────────────────────────────────────────
 * When credentials are available, set AIRTABLE_PAT in your .env file.
 * The client reads CONFIG.airtable.pat at construction time.
 *
 * If using Airtable MCP tools instead, swap the `request()` method body
 * for your MCP tool calls. The rest of the code does not need to change.
 * ──────────────────────────────────────────────────────────────────────────
 */

import axios, { AxiosInstance, AxiosError } from "axios";
import { CONFIG } from "./config";
import type {
  AirtableBaseSchema,
  AirtableField,
  FieldSpec,
  ViewSpec,
} from "./types";

const META_BASE = "https://api.airtable.com/v0/meta";
const DATA_BASE = "https://api.airtable.com/v0";

// Simple token-bucket rate limiter
class RateLimiter {
  private queue: Array<() => void> = [];
  private running = 0;
  private readonly limit: number;

  constructor(rps: number) {
    this.limit = rps;
  }

  async acquire(): Promise<void> {
    if (this.running < this.limit) {
      this.running++;
      return;
    }
    return new Promise((resolve) => {
      this.queue.push(() => {
        this.running++;
        resolve();
      });
    });
  }

  release(): void {
    this.running--;
    const next = this.queue.shift();
    if (next) {
      setTimeout(next, 1000 / this.limit);
    }
  }
}

export class AirtableClient {
  private http: AxiosInstance;
  private limiter: RateLimiter;
  readonly baseId: string;

  constructor() {
    this.baseId = CONFIG.airtable.baseId;
    this.limiter = new RateLimiter(CONFIG.rateLimitRps);

    // ── PAT INSERTION POINT ──────────────────────────────────────────────
    // Replace CONFIG.airtable.pat with your token source if needed.
    this.http = axios.create({
      headers: {
        Authorization: `Bearer ${CONFIG.airtable.pat}`,
        "Content-Type": "application/json",
      },
      timeout: 30_000,
    });
  }

  // ── Internal request wrapper ─────────────────────────────────────────────

  private async request<T>(
    method: "get" | "post" | "patch" | "delete",
    url: string,
    data?: unknown
  ): Promise<T> {
    await this.limiter.acquire();
    try {
      const resp = await this.http.request<T>({ method, url, data });
      return resp.data;
    } catch (err) {
      const ae = err as AxiosError<{ error?: { type: string; message: string } }>;
      const msg = ae.response?.data?.error?.message ?? ae.message;
      throw new Error(`Airtable API error [${ae.response?.status}]: ${msg}`);
    } finally {
      this.limiter.release();
    }
  }

  // ── Meta API: Schema ─────────────────────────────────────────────────────

  async getBaseSchema(): Promise<AirtableBaseSchema> {
    return this.request<AirtableBaseSchema>(
      "get",
      `${META_BASE}/bases/${this.baseId}/tables`
    );
  }

  async getTableFields(tableId: string): Promise<AirtableField[]> {
    const schema = await this.getBaseSchema();
    const table = schema.tables.find((t) => t.id === tableId);
    if (!table) throw new Error(`Table ${tableId} not found in base schema`);
    return table.fields;
  }

  // ── Meta API: Fields ─────────────────────────────────────────────────────

  async createField(tableId: string, spec: FieldSpec): Promise<AirtableField> {
    return this.request<AirtableField>(
      "post",
      `${META_BASE}/bases/${this.baseId}/tables/${tableId}/fields`,
      spec
    );
  }

  async updateField(
    tableId: string,
    fieldId: string,
    spec: Partial<FieldSpec>
  ): Promise<AirtableField> {
    return this.request<AirtableField>(
      "patch",
      `${META_BASE}/bases/${this.baseId}/tables/${tableId}/fields/${fieldId}`,
      spec
    );
  }

  async upsertField(
    tableId: string,
    spec: FieldSpec
  ): Promise<{ field: AirtableField; action: "created" | "updated" }> {
    const fields = await this.getTableFields(tableId);
    const existing = fields.find(
      (f) => f.name.toLowerCase() === spec.name.toLowerCase()
    );

    if (existing) {
      const updated = await this.updateField(tableId, existing.id, spec);
      return { field: updated, action: "updated" };
    }

    const created = await this.createField(tableId, spec);
    return { field: created, action: "created" };
  }

  // ── Meta API: Views ──────────────────────────────────────────────────────

  async createView(
    tableId: string,
    spec: Pick<ViewSpec, "name" | "type">
  ): Promise<{ id: string; name: string; type: string }> {
    return this.request<{ id: string; name: string; type: string }>(
      "post",
      `${META_BASE}/bases/${this.baseId}/tables/${tableId}/views`,
      spec
    );
  }

  // ── Data API: Records ────────────────────────────────────────────────────

  async listRecords<T extends Record<string, unknown>>(
    tableId: string,
    params: {
      fields?: string[];
      filterByFormula?: string;
      maxRecords?: number;
      pageSize?: number;
    } = {}
  ): Promise<Array<{ id: string; fields: T }>> {
    const records: Array<{ id: string; fields: T }> = [];
    let offset: string | undefined;

    do {
      const resp = await this.request<{
        records: Array<{ id: string; fields: T }>;
        offset?: string;
      }>("get", `${DATA_BASE}/${this.baseId}/${tableId}`, {
        params: { ...params, offset },
      });
      records.push(...resp.records);
      offset = resp.offset;
    } while (offset);

    return records;
  }

  async updateRecords(
    tableId: string,
    updates: Array<{ id: string; fields: Record<string, unknown> }>
  ): Promise<void> {
    // Airtable allows max 10 records per PATCH call
    const chunks: typeof updates[] = [];
    for (let i = 0; i < updates.length; i += 10) {
      chunks.push(updates.slice(i, i + 10));
    }

    for (const chunk of chunks) {
      await this.request(
        "patch",
        `${DATA_BASE}/${this.baseId}/${tableId}`,
        { records: chunk }
      );
    }
  }
}

export const client = new AirtableClient();
