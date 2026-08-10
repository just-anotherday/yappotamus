-- Controlled validation for migration 017. This test is read-only and ends
-- with ROLLBACK. It does not call net.http_post and cannot send an email.

BEGIN;

DO $test$
DECLARE
  expected_command CONSTANT TEXT := $command$
SELECT net.http_post(
  url := (
    SELECT decrypted_secret
    FROM vault.decrypted_secrets
    WHERE name = 'projects_supabase_url'
  ) || '/functions/v1/reminder-email-worker',
  headers := jsonb_build_object(
    'Content-Type', 'application/json',
    'apikey', (
      SELECT decrypted_secret
      FROM vault.decrypted_secrets
      WHERE name = 'projects_reminder_worker_api_key'
    )
  ),
  body := '{}'::jsonb,
  timeout_milliseconds := 30000
);
$command$;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron')
     OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_net')
     OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'supabase_vault') THEN
    RAISE EXCEPTION 'Migration 017 scheduler prerequisites are unavailable';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'projects_reminder_worker_api_key'
  ) OR NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'projects_supabase_url'
  ) THEN
    RAISE EXCEPTION 'Migration 017 required Vault secret names are missing';
  END IF;

  IF (
    SELECT count(*) FROM cron.job WHERE jobname = 'projects-reminder-email-worker'
  ) <> 1 OR NOT EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobname = 'projects-reminder-email-worker'
      AND active = true
      AND schedule = '* * * * *'
      AND command = expected_command
  ) THEN
    RAISE EXCEPTION 'Reminder email worker Cron job is missing, duplicated, or mismatched';
  END IF;

  IF EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobname = 'projects-reminder-email-worker'
      AND (
        command NOT LIKE '%/functions/v1/reminder-email-worker%'
        OR command NOT LIKE '%net.http_post%'
        OR command NOT LIKE '%vault.decrypted_secrets%'
        OR command NOT LIKE '%projects_reminder_worker_api_key%'
        OR command NOT LIKE '%projects_supabase_url%'
        OR command NOT LIKE '%apikey%'
        OR command LIKE '%sb_secret_%'
      )
  ) THEN
    RAISE EXCEPTION 'Reminder email worker Cron command violates the Vault request contract';
  END IF;

  IF (
    SELECT count(*) FROM cron.job WHERE jobname = 'projects-generate-task-due-notifications'
  ) <> 1 OR (
    SELECT count(*) FROM cron.job WHERE jobname = 'projects-generate-custom-reminders'
  ) <> 1 THEN
    RAISE EXCEPTION 'Existing Projects Cron jobs are missing or duplicated';
  END IF;
END
$test$;

ROLLBACK;
