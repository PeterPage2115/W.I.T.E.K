-- Sprint 3: Auto-resolve attack reports after timeout
ALTER TABLE attack_reports ADD COLUMN auto_resolved BOOLEAN DEFAULT FALSE;
UPDATE attack_reports SET auto_resolved = FALSE WHERE auto_resolved IS NULL;
CREATE INDEX IF NOT EXISTS ix_attack_reports_status_unix ON attack_reports (status, attack_unix);
