-- Migration 011: Add task due-date reminder infrastructure.
--
-- This migration deliberately does not create a pg_cron job. Scheduling is an
-- approved, separate database-owner step after controlled validation.

BEGIN;

DO $migration_011_preflight$
BEGIN
  IF to_regclass('public.tasks') IS NULL
     OR to_regclass('public.user_settings') IS NULL
     OR to_regclass('public.notifications') IS NULL THEN
    RAISE EXCEPTION 'Migration 011 requires tasks, user_settings, and notifications';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'due_on' AND udt_name = 'date' AND is_nullable = 'YES'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'status' AND udt_name = 'text' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'is_archived' AND udt_name = 'bool' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'timezone' AND udt_name = 'text' AND is_nullable = 'YES'
  ) THEN
    RAISE EXCEPTION 'Migration 011 requires migration 010 task and timezone columns';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_type_check'
      AND pg_get_constraintdef(oid, true) LIKE '%task_due_soon%'
      AND pg_get_constraintdef(oid, true) LIKE '%task_overdue%'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_entity_type_check'
      AND pg_get_constraintdef(oid, true) LIKE '%task%'
  ) THEN
    RAISE EXCEPTION 'Migration 011 requires task notification types and entity support';
  END IF;

  IF to_regclass('public.task_reminder_events') IS NOT NULL
     OR to_regclass('public.idx_tasks_reminder_eligible_due_on') IS NOT NULL
     OR to_regprocedure('public.generate_task_due_notifications(timestamptz)') IS NOT NULL THEN
    RAISE EXCEPTION 'Migration 011 found existing reminder infrastructure';
  END IF;
END
$migration_011_preflight$;

CREATE TABLE public.task_reminder_events (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  task_id UUID NOT NULL,
  reminder_type TEXT NOT NULL,
  due_on DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT task_reminder_events_pkey PRIMARY KEY (id),
  CONSTRAINT task_reminder_events_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT task_reminder_events_task_id_fkey
    FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE,
  CONSTRAINT task_reminder_events_type_check
    CHECK (reminder_type IN ('task_due_soon', 'task_overdue')),
  CONSTRAINT task_reminder_events_lifecycle_key
    UNIQUE (user_id, task_id, reminder_type, due_on)
);

ALTER TABLE public.task_reminder_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.task_reminder_events
  FROM PUBLIC, anon, authenticated;

CREATE INDEX idx_tasks_reminder_eligible_due_on
  ON public.tasks (due_on, user_id)
  WHERE due_on IS NOT NULL
    AND status <> 'COMPLETED'
    AND is_archived = false;

CREATE FUNCTION public.generate_task_due_notifications(
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  due_soon_created BIGINT,
  overdue_created BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  RETURN QUERY
  WITH eligible AS (
    SELECT
      task_row.user_id,
      task_row.id AS task_id,
      task_row.project_id,
      task_row.title AS task_title,
      task_row.due_on,
      (p_now AT TIME ZONE settings_row.timezone)::date AS local_today
    FROM public.tasks AS task_row
    JOIN public.user_settings AS settings_row
      ON settings_row.user_id = task_row.user_id
    WHERE task_row.status <> 'COMPLETED'
      AND task_row.is_archived = false
      AND task_row.due_on IS NOT NULL
      AND settings_row.timezone IS NOT NULL
  ), candidates AS (
    SELECT
      user_id,
      task_id,
      project_id,
      task_title,
      due_on,
      local_today,
      'task_due_soon'::text AS reminder_type
    FROM eligible
    WHERE due_on >= local_today
      AND due_on <= local_today + 1

    UNION ALL

    SELECT
      user_id,
      task_id,
      project_id,
      task_title,
      due_on,
      local_today,
      'task_overdue'::text AS reminder_type
    FROM eligible
    WHERE due_on < local_today
  ), inserted_events AS (
    INSERT INTO public.task_reminder_events (
      user_id,
      task_id,
      reminder_type,
      due_on
    )
    SELECT user_id, task_id, reminder_type, due_on
    FROM candidates
    ON CONFLICT (user_id, task_id, reminder_type, due_on) DO NOTHING
    RETURNING user_id, task_id, reminder_type, due_on
  ), inserted_notifications AS (
    INSERT INTO public.notifications (
      user_id,
      type,
      title,
      message,
      workspace,
      entity_type,
      entity_id,
      metadata,
      dedupe_key,
      expires_at
    )
    SELECT
      event_row.user_id,
      event_row.reminder_type,
      CASE event_row.reminder_type
        WHEN 'task_due_soon' THEN 'Task due soon'
        ELSE 'Task overdue'
      END,
      CASE event_row.reminder_type
        WHEN 'task_due_soon' THEN format(
          '"%s" is due %s.',
          left(candidate_row.task_title, 1900),
          CASE
            WHEN candidate_row.due_on = candidate_row.local_today THEN 'today'
            ELSE 'tomorrow'
          END
        )
        ELSE format(
          '"%s" is overdue.',
          left(candidate_row.task_title, 1900)
        )
      END,
      'projects',
      'task',
      event_row.task_id,
      jsonb_build_object(
        'due_on', event_row.due_on::text,
        'project_id', candidate_row.project_id
      ),
      CASE event_row.reminder_type
        WHEN 'task_due_soon' THEN format(
          'task-due-soon:%s:%s', event_row.task_id, event_row.due_on
        )
        ELSE format(
          'task-overdue:%s:%s', event_row.task_id, event_row.due_on
        )
      END,
      NULL
    FROM inserted_events AS event_row
    JOIN candidates AS candidate_row
      ON candidate_row.user_id = event_row.user_id
      AND candidate_row.task_id = event_row.task_id
      AND candidate_row.reminder_type = event_row.reminder_type
      AND candidate_row.due_on = event_row.due_on
    RETURNING type
  )
  SELECT
    count(*) FILTER (WHERE type = 'task_due_soon')::bigint,
    count(*) FILTER (WHERE type = 'task_overdue')::bigint
  FROM inserted_notifications;
END;
$function$;

REVOKE ALL PRIVILEGES
  ON FUNCTION public.generate_task_due_notifications(TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;

DO $migration_011_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.task_reminder_events'::regclass
      AND relkind = 'r' AND relrowsecurity
  ) OR (
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'public.task_reminder_events'::regclass
      AND conname IN (
        'task_reminder_events_pkey',
        'task_reminder_events_user_id_fkey',
        'task_reminder_events_task_id_fkey',
        'task_reminder_events_type_check',
        'task_reminder_events_lifecycle_key'
      )
  ) <> 5 OR to_regclass('public.idx_tasks_reminder_eligible_due_on') IS NULL THEN
    RAISE EXCEPTION 'Migration 011 postflight failed: reminder ledger infrastructure missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.task_reminder_events'::regclass
      AND conname = 'task_reminder_events_user_id_fkey'
      AND confdeltype = 'c'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.task_reminder_events'::regclass
      AND conname = 'task_reminder_events_task_id_fkey'
      AND confdeltype = 'c'
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'task_reminder_events'
  ) OR EXISTS (
    SELECT 1 FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'task_reminder_events'
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
  ) OR EXISTS (
    SELECT 1 FROM information_schema.column_privileges
    WHERE table_schema = 'public'
      AND table_name = 'task_reminder_events'
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
  ) THEN
    RAISE EXCEPTION 'Migration 011 postflight failed: ledger access or foreign keys mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.generate_task_due_notifications(timestamptz)'::regprocedure
      AND prosecdef
      AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) OR EXISTS (
    SELECT 1 FROM information_schema.routine_privileges
    WHERE routine_schema = 'public'
      AND routine_name = 'generate_task_due_notifications'
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
  ) THEN
    RAISE EXCEPTION 'Migration 011 postflight failed: generator security mismatch';
  END IF;
END
$migration_011_postflight$;

COMMIT;

-- After controlled validation, the database owner may register the approved
-- hourly job separately. Do not execute this during migration application:
-- SELECT cron.schedule(
--   'projects-generate-task-due-notifications',
--   '17 * * * *',
--   $$SELECT * FROM public.generate_task_due_notifications();$$
-- );
