// ─────────────────────────────────────────────────────────────────────────────
// Airtable REST API types (Meta API for schema manipulation)
// ─────────────────────────────────────────────────────────────────────────────

export type AirtableFieldType =
  | "singleLineText"
  | "multilineText"
  | "richText"
  | "number"
  | "currency"
  | "percent"
  | "rating"
  | "formula"
  | "rollup"
  | "count"
  | "lookup"
  | "singleSelect"
  | "multipleSelects"
  | "checkbox"
  | "date"
  | "dateTime"
  | "duration"
  | "email"
  | "url"
  | "phoneNumber"
  | "multipleAttachments"
  | "multipleRecordLinks"
  | "autoNumber"
  | "createdTime"
  | "lastModifiedTime"
  | "createdBy"
  | "lastModifiedBy"
  | "collaborator"
  | "multipleCollaborators"
  | "barcode"
  | "externalSyncSource"
  | "button";

export interface FieldOptions {
  formula?: string;
  result?: {
    type: AirtableFieldType;
    options?: Record<string, unknown>;
  };
  precision?: number;
  symbol?: string;
  format?: string;
  choices?: Array<{ name: string; color?: string }>;
  linkedTableId?: string;
  prefersSingleRecordLink?: boolean;
}

export interface FieldSpec {
  name: string;
  type: AirtableFieldType;
  description?: string;
  options?: FieldOptions;
}

export interface ViewSpec {
  name: string;
  type: "grid" | "gallery" | "kanban" | "calendar" | "form";
  filterByFormula?: string;
  sorts?: Array<{ fieldId?: string; fieldName?: string; direction: "asc" | "desc" }>;
  description?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Airtable REST API response shapes
// ─────────────────────────────────────────────────────────────────────────────

export interface AirtableField {
  id: string;
  name: string;
  type: AirtableFieldType;
  description?: string;
  options?: Record<string, unknown>;
}

export interface AirtableTable {
  id: string;
  name: string;
  fields: AirtableField[];
  views: Array<{ id: string; name: string; type: string }>;
}

export interface AirtableBaseSchema {
  id: string;
  name: string;
  tables: AirtableTable[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Script result types
// ─────────────────────────────────────────────────────────────────────────────

export type ActionStatus = "created" | "updated" | "skipped" | "dry-run" | "error";

export interface FieldResult {
  table: string;
  field: string;
  status: ActionStatus;
  error?: string;
}

export interface ViewResult {
  table: string;
  view: string;
  status: ActionStatus;
  error?: string;
}
