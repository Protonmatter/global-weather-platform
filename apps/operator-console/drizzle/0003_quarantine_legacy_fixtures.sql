UPDATE `observations`
SET
  `quality_disposition` = 'quarantine',
  `quality_flags` = '["synthetic_validation_fixture"]'
WHERE `source_id` LIKE 'validation-set/%';
--> statement-breakpoint
DELETE FROM `model_cycles`
WHERE `id` IN (
  'gefs-35-20260724t18z',
  'gfs-17-20260724t18z',
  'platform-calibration-20260724t12z'
);
