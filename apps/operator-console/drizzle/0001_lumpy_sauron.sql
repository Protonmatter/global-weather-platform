CREATE TABLE `audit_events` (
	`id` text PRIMARY KEY NOT NULL,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`resource_type` text NOT NULL,
	`resource_id` text NOT NULL,
	`occurred_at` text NOT NULL,
	`detail` text DEFAULT '{}' NOT NULL
);
--> statement-breakpoint
CREATE INDEX `audit_events_occurred_at_idx` ON `audit_events` (`occurred_at`);--> statement-breakpoint
CREATE INDEX `audit_events_resource_idx` ON `audit_events` (`resource_type`,`resource_id`);--> statement-breakpoint
ALTER TABLE `observations` ADD `record_index` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE `observations` ADD `content_digest` text DEFAULT '' NOT NULL;