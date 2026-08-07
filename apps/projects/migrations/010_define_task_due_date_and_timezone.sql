-- Migration 010: Define calendar-date task deadlines and user timezones.
--
-- `due_on` is a user-local calendar date. `due_date` remains temporarily for
-- legacy browser compatibility and is interpreted only as a UTC-midnight date.

BEGIN;

DO $migration_010_preflight$
BEGIN
  IF to_regclass('public.tasks') IS NULL
     OR to_regclass('public.user_settings') IS NULL THEN
    RAISE EXCEPTION 'Migration 010 requires public.tasks and public.user_settings';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'due_on'
  ) OR EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND column_name = 'timezone'
  ) THEN
    RAISE EXCEPTION 'Migration 010 columns already exist';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'due_date'
      AND udt_name = 'timestamptz'
      AND is_nullable = 'YES'
  ) THEN
    RAISE EXCEPTION 'Migration 010 requires public.tasks.due_date TIMESTAMPTZ NULL';
  END IF;

  IF NOT has_column_privilege(
    'authenticated',
    'public.tasks',
    'due_date',
    'INSERT'
  ) OR NOT has_column_privilege(
    'authenticated',
    'public.tasks',
    'due_date',
    'UPDATE'
  ) THEN
    RAISE EXCEPTION 'Migration 010 requires authenticated due_date write privileges';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks
    WHERE due_date IS NOT NULL
      AND (due_date AT TIME ZONE 'UTC')::time <> time '00:00:00'
  ) THEN
    RAISE EXCEPTION 'Migration 010 found due_date values that are not UTC midnight';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_class
    WHERE oid = 'public.user_settings'::regclass
      AND relrowsecurity
  ) THEN
    RAISE EXCEPTION 'Migration 010 requires RLS on public.user_settings';
  END IF;
END
$migration_010_preflight$;

ALTER TABLE public.tasks
  ADD COLUMN due_on DATE NULL;

GRANT INSERT (due_on)
  ON TABLE public.tasks
  TO authenticated;

GRANT UPDATE (due_on)
  ON TABLE public.tasks
  TO authenticated;

UPDATE public.tasks
SET due_on = (due_date AT TIME ZONE 'UTC')::date
WHERE due_date IS NOT NULL
  AND due_on IS NULL;

CREATE FUNCTION public.sync_task_due_on_from_legacy_due_date()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
BEGIN
  NEW.due_on := CASE
    WHEN NEW.due_date IS NULL THEN NULL
    ELSE (NEW.due_date AT TIME ZONE 'UTC')::date
  END;
  RETURN NEW;
END;
$function$;

REVOKE ALL PRIVILEGES
  ON FUNCTION public.sync_task_due_on_from_legacy_due_date()
  FROM PUBLIC, anon, authenticated;

CREATE TRIGGER sync_tasks_due_on_from_legacy_due_date
  BEFORE INSERT OR UPDATE OF due_date
  ON public.tasks
  FOR EACH ROW
  EXECUTE FUNCTION public.sync_task_due_on_from_legacy_due_date();

ALTER TABLE public.user_settings
  ADD COLUMN timezone TEXT NULL;

CREATE FUNCTION public.validate_user_settings_timezone()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF NEW.timezone IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
       FROM pg_timezone_names
       WHERE name = NEW.timezone
     ) THEN
    RAISE EXCEPTION 'Invalid PostgreSQL timezone: %', NEW.timezone
      USING ERRCODE = '22023';
  END IF;
  RETURN NEW;
END;
$function$;

REVOKE ALL PRIVILEGES
  ON FUNCTION public.validate_user_settings_timezone()
  FROM PUBLIC, anon, authenticated;

CREATE TRIGGER validate_user_settings_timezone
  BEFORE INSERT OR UPDATE OF timezone
  ON public.user_settings
  FOR EACH ROW
  EXECUTE FUNCTION public.validate_user_settings_timezone();

REVOKE ALL PRIVILEGES (timezone)
  ON TABLE public.user_settings
  FROM PUBLIC, anon, authenticated;

GRANT INSERT (timezone)
  ON TABLE public.user_settings
  TO authenticated;

GRANT UPDATE (timezone)
  ON TABLE public.user_settings
  TO authenticated;

DO $migration_010_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'due_on'
      AND udt_name = 'date'
      AND is_nullable = 'YES'
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND column_name = 'timezone'
      AND udt_name = 'text'
      AND is_nullable = 'YES'
  ) THEN
    RAISE EXCEPTION 'Migration 010 postflight failed: expected columns missing';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks
    WHERE due_date IS NOT NULL
      AND due_on IS DISTINCT FROM (due_date AT TIME ZONE 'UTC')::date
  ) THEN
    RAISE EXCEPTION 'Migration 010 postflight failed: due_on backfill mismatch';
  END IF;

  IF to_regprocedure('public.sync_task_due_on_from_legacy_due_date()') IS NULL
     OR to_regprocedure('public.validate_user_settings_timezone()') IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM pg_trigger
       WHERE tgrelid = 'public.tasks'::regclass
         AND tgname = 'sync_tasks_due_on_from_legacy_due_date'
         AND NOT tgisinternal
         AND tgenabled <> 'D'
     ) OR NOT EXISTS (
       SELECT 1
       FROM pg_trigger
       WHERE tgrelid = 'public.user_settings'::regclass
         AND tgname = 'validate_user_settings_timezone'
         AND NOT tgisinternal
         AND tgenabled <> 'D'
     ) THEN
    RAISE EXCEPTION 'Migration 010 postflight failed: compatibility or validation trigger missing';
  END IF;

  IF NOT has_column_privilege(
    'authenticated',
    'public.user_settings',
    'timezone',
    'INSERT'
  ) OR NOT has_column_privilege(
    'authenticated',
    'public.user_settings',
    'timezone',
    'UPDATE'
  ) THEN
    RAISE EXCEPTION 'Migration 010 postflight failed: timezone grants missing';
  END IF;

  IF NOT has_column_privilege(
    'authenticated',
    'public.tasks',
    'due_on',
    'INSERT'
  ) OR NOT has_column_privilege(
    'authenticated',
    'public.tasks',
    'due_on',
    'UPDATE'
  ) THEN
    RAISE EXCEPTION 'Migration 010 postflight failed: due_on grants missing';
  END IF;
END
$migration_010_postflight$;

COMMIT;

-- Reminder generation and Cron are intentionally deferred to migration 011.
