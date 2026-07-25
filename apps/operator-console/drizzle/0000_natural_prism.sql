CREATE TABLE `model_cycles` (
	`id` text PRIMARY KEY NOT NULL,
	`model_id` text NOT NULL,
	`model_version` text NOT NULL,
	`guidance_origin` text NOT NULL,
	`initialized_at` text NOT NULL,
	`source_revision` text NOT NULL,
	`completeness` text NOT NULL,
	`available_field_count` integer NOT NULL,
	`expected_field_count` integer NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `model_cycles_model_id_idx` ON `model_cycles` (`model_id`);--> statement-breakpoint
CREATE INDEX `model_cycles_initialized_at_idx` ON `model_cycles` (`initialized_at`);--> statement-breakpoint
CREATE TABLE `observations` (
	`id` text PRIMARY KEY NOT NULL,
	`schema_version` text DEFAULT '1.0.0' NOT NULL,
	`phenomenon` text NOT NULL,
	`value` real,
	`unit` text NOT NULL,
	`uncertainty` real,
	`longitude` real NOT NULL,
	`latitude` real NOT NULL,
	`observed_at` text NOT NULL,
	`ingested_at` text NOT NULL,
	`quality_disposition` text NOT NULL,
	`quality_flags` text DEFAULT '[]' NOT NULL,
	`source_id` text NOT NULL,
	`source_digest` text NOT NULL,
	`decoder_version` text NOT NULL,
	`created_by` text NOT NULL,
	FOREIGN KEY (`source_digest`) REFERENCES `source_records`(`digest`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `observations_phenomenon_idx` ON `observations` (`phenomenon`);--> statement-breakpoint
CREATE INDEX `observations_observed_at_idx` ON `observations` (`observed_at`);--> statement-breakpoint
CREATE INDEX `observations_source_digest_idx` ON `observations` (`source_digest`);--> statement-breakpoint
CREATE TABLE `source_records` (
	`digest` text PRIMARY KEY NOT NULL,
	`object_key` text NOT NULL,
	`byte_length` integer NOT NULL,
	`content_type` text NOT NULL,
	`received_at` text NOT NULL,
	`created_by` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `source_records_received_at_idx` ON `source_records` (`received_at`);