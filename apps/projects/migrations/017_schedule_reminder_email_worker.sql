-- Migration 017: schedule the authenticated reminder email worker.
--
-- Deployment prerequisites (created manually, never by this migration):
--   vault.secrets.name = projects_reminder_worker_api_key
--   vault.secrets.name = projects_supabase_url

BEGIN;

DO $migration_017$
DECLARE
  expected_job_name CONSTANT TEXT := 'projects-reminder-email-worker';
  expected_schedule CONSTANT TEXT := '* * * * *';
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
  existing_job RECORD;
  task_due_job RECORD;
  custom_reminder_job RECORD;
BEGIN
  -- Infrastructure is owned by Supabase/project operations. This migration
  -- only verifies it; it never attempts to enable extensions.
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron')
     OR to_regnamespace('cron') IS NULL
     OR to_regclass('cron.job') IS NULL
     OR to_regprocedure('cron.schedule(text,text,text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 017 requires usable pg_cron infrastructure';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_net')
     OR to_regnamespace('net') IS NULL
     OR to_regprocedure('net.http_post(text,jsonb,jsonb,jsonb,integer)') IS NULL
     OR to_regclass('net._http_response') IS NULL THEN
    RAISE EXCEPTION 'Migration 017 requires usable pg_net infrastructure';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'supabase_vault')
     OR to_regnamespace('vault') IS NULL
     OR to_regclass('vault.secrets') IS NULL
     OR to_regclass('vault.decrypted_secrets') IS NULL
     OR NOT has_table_privilege(current_user, 'vault.decrypted_secrets', 'SELECT') THEN
    RAISE EXCEPTION 'Migration 017 requires usable Supabase Vault infrastructure';
  END IF;

  -- Check encrypted metadata only. Decrypted values are resolved exclusively
  -- inside the scheduled command when pg_net submits the request.
  IF NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'projects_reminder_worker_api_key'
  ) OR NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'projects_supabase_url'
  ) THEN
    RAISE EXCEPTION 'Migration 017 requires named Vault secrets projects_reminder_worker_api_key and projects_supabase_url';
  END IF;

  SELECT jobid, jobname, schedule, command, active
  INTO task_due_job
  FROM cron.job
  WHERE jobname = 'projects-generate-task-due-notifications';
  IF NOT FOUND OR (
    SELECT count(*) FROM cron.job WHERE jobname = 'projects-generate-task-due-notifications'
  ) <> 1 THEN
    RAISE EXCEPTION 'Migration 017 requires exactly one existing projects-generate-task-due-notifications Cron job';
  END IF;

  SELECT jobid, jobname, schedule, command, active
  INTO custom_reminder_job
  FROM cron.job
  WHERE jobname = 'projects-generate-custom-reminders';
  IF NOT FOUND OR (
    SELECT count(*) FROM cron.job WHERE jobname = 'projects-generate-custom-reminders'
  ) <> 1 THEN
    RAISE EXCEPTION 'Migration 017 requires exactly one existing projects-generate-custom-reminders Cron job';
  END IF;

  SELECT jobid, jobname, schedule, command, active
  INTO existing_job
  FROM cron.job
  WHERE jobname = expected_job_name;

  IF FOUND THEN
    IF (
      SELECT count(*) FROM cron.job WHERE jobname = expected_job_name
    ) <> 1
       OR existing_job.schedule <> expected_schedule
       OR existing_job.command <> expected_command
       OR existing_job.active IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'Migration 017 found conflicting Cron job %', expected_job_name;
    END IF;
  ELSE
    PERFORM cron.schedule(expected_job_name, expected_schedule, expected_command);
  END IF;

  IF (
    SELECT count(*) FROM cron.job WHERE jobname = expected_job_name
  ) <> 1 OR NOT EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobname = expected_job_name
      AND schedule = expected_schedule
      AND command = expected_command
      AND active = true
  ) THEN
    RAISE EXCEPTION 'Migration 017 postflight failed: reminder email worker Cron job mismatch';
  END IF;

  -- Exact command equality proves no decrypted credential was persisted. The
  -- additional checks make the intended contract explicit for release review.
  IF EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobname = expected_job_name
      AND (
        command NOT LIKE '%/functions/v1/reminder-email-worker%'
        OR command NOT LIKE '%vault.decrypted_secrets%'
        OR command NOT LIKE '%projects_reminder_worker_api_key%'
        OR command NOT LIKE '%projects_supabase_url%'
        OR command NOT LIKE '%net.http_post%'
        OR command NOT LIKE '%apikey%'
        OR command LIKE '%sb_secret_%'
        OR command LIKE '%RESEND_API_KEY%'
      )
  ) THEN
    RAISE EXCEPTION 'Migration 017 postflight failed: persisted Cron command security contract mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobid = task_due_job.jobid
      AND jobname = task_due_job.jobname
      AND schedule = task_due_job.schedule
      AND command = task_due_job.command
      AND active IS NOT DISTINCT FROM task_due_job.active
  ) OR NOT EXISTS (
    SELECT 1 FROM cron.job
    WHERE jobid = custom_reminder_job.jobid
      AND jobname = custom_reminder_job.jobname
      AND schedule = custom_reminder_job.schedule
      AND command = custom_reminder_job.command
      AND active IS NOT DISTINCT FROM custom_reminder_job.active
  ) THEN
    RAISE EXCEPTION 'Migration 017 postflight failed: existing Projects Cron job changed';
  END IF;
END
$migration_017$;

COMMIT;
