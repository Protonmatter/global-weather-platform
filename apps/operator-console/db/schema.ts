import { index, integer, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const sourceRecords = sqliteTable(
  "source_records",
  {
    digest: text("digest").primaryKey(),
    objectKey: text("object_key").notNull(),
    byteLength: integer("byte_length").notNull(),
    contentType: text("content_type").notNull(),
    receivedAt: text("received_at").notNull(),
    createdBy: text("created_by").notNull(),
  },
  (table) => [index("source_records_received_at_idx").on(table.receivedAt)],
);

export const observations = sqliteTable(
  "observations",
  {
    id: text("id").primaryKey(),
    schemaVersion: text("schema_version").notNull().default("1.0.0"),
    phenomenon: text("phenomenon").notNull(),
    value: real("value"),
    unit: text("unit").notNull(),
    uncertainty: real("uncertainty"),
    longitude: real("longitude").notNull(),
    latitude: real("latitude").notNull(),
    observedAt: text("observed_at").notNull(),
    ingestedAt: text("ingested_at").notNull(),
    qualityDisposition: text("quality_disposition").notNull(),
    qualityFlags: text("quality_flags").notNull().default("[]"),
    sourceId: text("source_id").notNull(),
    sourceDigest: text("source_digest")
      .notNull()
      .references(() => sourceRecords.digest),
    decoderVersion: text("decoder_version").notNull(),
    recordIndex: integer("record_index").notNull().default(0),
    contentDigest: text("content_digest").notNull().default(""),
    createdBy: text("created_by").notNull(),
  },
  (table) => [
    index("observations_phenomenon_idx").on(table.phenomenon),
    index("observations_observed_at_idx").on(table.observedAt),
    index("observations_source_digest_idx").on(table.sourceDigest),
  ],
);

export const auditEvents = sqliteTable(
  "audit_events",
  {
    id: text("id").primaryKey(),
    actor: text("actor").notNull(),
    action: text("action").notNull(),
    resourceType: text("resource_type").notNull(),
    resourceId: text("resource_id").notNull(),
    occurredAt: text("occurred_at").notNull(),
    detail: text("detail").notNull().default("{}"),
  },
  (table) => [
    index("audit_events_occurred_at_idx").on(table.occurredAt),
    index("audit_events_resource_idx").on(
      table.resourceType,
      table.resourceId,
    ),
  ],
);

export const modelCycles = sqliteTable(
  "model_cycles",
  {
    id: text("id").primaryKey(),
    modelId: text("model_id").notNull(),
    modelVersion: text("model_version").notNull(),
    guidanceOrigin: text("guidance_origin").notNull(),
    initializedAt: text("initialized_at").notNull(),
    sourceRevision: text("source_revision").notNull(),
    completeness: text("completeness").notNull(),
    availableFieldCount: integer("available_field_count").notNull(),
    expectedFieldCount: integer("expected_field_count").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [
    index("model_cycles_model_id_idx").on(table.modelId),
    index("model_cycles_initialized_at_idx").on(table.initializedAt),
  ],
);
