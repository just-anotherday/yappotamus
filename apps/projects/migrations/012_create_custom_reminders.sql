-- Migration 012: user-selected, exact-time, in-app custom reminders.
--
-- This migration intentionally has no email state, outbox, provider integration,
-- or cron registration. Migration 013 owns those concerns atomically.

BEGIN;

DO $migration_012_preflight$
DECLARE
  notification_type_definition TEXT;
BEGIN
  IF to_regclass('public.tasks') IS NULL
     OR to_regclass('public.projects') IS NULL
     OR to_regclass('public.recipes') IS NULL
     OR to_regclass('public.user_settings') IS NULL
     OR to_regclass('public.notifications') IS NULL THEN
    RAISE EXCEPTION 'Migration 012 requires tasks, projects, recipes, user_settings, and notifications';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires tasks.id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires tasks.user_id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'project_id' AND udt_name = 'uuid' AND is_nullable = 'YES') THEN
    -- Parentless tasks are valid legacy rows. The target trigger, not global
    -- column nullability, proves that a reminded task belongs to a board.
    RAISE EXCEPTION 'Migration 012 requires tasks.project_id UUID NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'title' AND udt_name = 'text' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires tasks.title TEXT NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'status' AND udt_name = 'text' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires tasks.status TEXT NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tasks' AND column_name = 'is_archived' AND udt_name = 'bool' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires tasks.is_archived BOOLEAN NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires projects.id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires projects.user_id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'kind' AND udt_name = 'text' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires projects.kind TEXT NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'name' AND udt_name = 'text' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires projects.name TEXT NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'recipes' AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires recipes.id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'recipes' AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires recipes.user_id UUID NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'recipes' AND column_name = 'name' AND udt_name = 'text' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires recipes.name TEXT NOT NULL';
  ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'recipes' AND column_name = 'is_archived' AND udt_name = 'bool' AND is_nullable = 'NO') THEN
    RAISE EXCEPTION 'Migration 012 requires recipes.is_archived BOOLEAN NOT NULL';
  END IF;

  IF to_regclass('public.reminders') IS NOT NULL
     OR to_regprocedure('public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone)') IS NOT NULL
     OR to_regprocedure('public.cancel_custom_reminder(uuid)') IS NOT NULL
     OR to_regprocedure('public.generate_custom_reminders(timestamp with time zone)') IS NOT NULL THEN
    RAISE EXCEPTION 'Migration 012 found existing custom reminder infrastructure';
  END IF;

  SELECT pg_get_constraintdef(oid, true)
  INTO notification_type_definition
  FROM pg_constraint
  WHERE conrelid = 'public.notifications'::regclass
    AND conname = 'notifications_type_check';

  IF notification_type_definition IS NULL
     OR notification_type_definition NOT LIKE '%system_message%'
     OR notification_type_definition NOT LIKE '%task_due_soon%'
     OR notification_type_definition NOT LIKE '%task_overdue%'
     OR notification_type_definition NOT LIKE '%shopping_date_upcoming%'
     OR notification_type_definition LIKE '%custom_reminder%' THEN
    RAISE EXCEPTION 'Migration 012 requires the baseline notifications_type_check';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_workspace_check'
      AND pg_get_constraintdef(oid, true) LIKE '%projects%'
      AND pg_get_constraintdef(oid, true) LIKE '%shopping%'
      AND pg_get_constraintdef(oid, true) LIKE '%recipes%'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_entity_type_check'
      AND pg_get_constraintdef(oid, true) LIKE '%task%'
      AND pg_get_constraintdef(oid, true) LIKE '%shopping_list%'
      AND pg_get_constraintdef(oid, true) LIKE '%recipe%'
  ) THEN
    RAISE EXCEPTION 'Migration 012 requires the baseline notification workspace/entity constraints';
  END IF;
END
$migration_012_preflight$;

-- Composite ownership foreign keys need a unique referenced key. recipes
-- already has one from migration 006; tasks and projects do not.
DO $migration_012_owner_keys$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_index
    WHERE indrelid = 'public.tasks'::regclass
      AND indisunique
      AND indpred IS NULL
      AND indexprs IS NULL
      AND indnkeyatts = 2
      AND array_to_string(indkey::SMALLINT[], ' ') = format(
        '%s %s',
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.tasks'::regclass AND attname = 'id' AND NOT attisdropped),
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.tasks'::regclass AND attname = 'user_id' AND NOT attisdropped)
      )
  ) THEN
    ALTER TABLE public.tasks
      ADD CONSTRAINT tasks_id_user_id_key UNIQUE (id, user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_index
    WHERE indrelid = 'public.projects'::regclass
      AND indisunique
      AND indpred IS NULL
      AND indexprs IS NULL
      AND indnkeyatts = 2
      AND array_to_string(indkey::SMALLINT[], ' ') = format(
        '%s %s',
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.projects'::regclass AND attname = 'id' AND NOT attisdropped),
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.projects'::regclass AND attname = 'user_id' AND NOT attisdropped)
      )
  ) THEN
    ALTER TABLE public.projects
      ADD CONSTRAINT projects_id_user_id_key UNIQUE (id, user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_index
    WHERE indrelid = 'public.recipes'::regclass
      AND indisunique
      AND indpred IS NULL
      AND indexprs IS NULL
      AND indnkeyatts = 2
      AND array_to_string(indkey::SMALLINT[], ' ') = format(
        '%s %s',
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.recipes'::regclass AND attname = 'id' AND NOT attisdropped),
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.recipes'::regclass AND attname = 'user_id' AND NOT attisdropped)
      )
  ) THEN
    RAISE EXCEPTION 'Migration 012 requires recipes(id, user_id) uniqueness';
  END IF;
END
$migration_012_owner_keys$;

CREATE TABLE public.reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  task_id UUID NULL,
  shopping_project_id UUID NULL,
  recipe_id UUID NULL,
  remind_at TIMESTAMPTZ NOT NULL,
  timezone TEXT NOT NULL,
  in_app_enabled BOOLEAN NOT NULL DEFAULT true,
  status TEXT NOT NULL DEFAULT 'scheduled',
  fired_at TIMESTAMPTZ NULL,
  cancelled_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT reminders_one_target_check
    CHECK (num_nonnulls(task_id, shopping_project_id, recipe_id) = 1),
  -- Migration 013 replaces this scheduled-channel check with
  -- (in_app_enabled OR email_enabled) after it introduces email_enabled.
  CONSTRAINT reminders_scheduled_in_app_check
    CHECK (status <> 'scheduled' OR in_app_enabled),
  CONSTRAINT reminders_status_check
    CHECK (status IN ('scheduled', 'sent', 'cancelled')),
  CONSTRAINT reminders_status_timestamps_check
    CHECK (
      (status = 'scheduled' AND fired_at IS NULL AND cancelled_at IS NULL)
      OR (status = 'sent' AND fired_at IS NOT NULL AND cancelled_at IS NULL)
      OR (status = 'cancelled' AND fired_at IS NULL AND cancelled_at IS NOT NULL)
    ),
  CONSTRAINT reminders_task_owner_fkey
    FOREIGN KEY (task_id, user_id)
    REFERENCES public.tasks(id, user_id) ON DELETE CASCADE,
  CONSTRAINT reminders_shopping_project_owner_fkey
    FOREIGN KEY (shopping_project_id, user_id)
    REFERENCES public.projects(id, user_id) ON DELETE CASCADE,
  CONSTRAINT reminders_recipe_owner_fkey
    FOREIGN KEY (recipe_id, user_id)
    REFERENCES public.recipes(id, user_id) ON DELETE CASCADE
);

CREATE INDEX idx_reminders_due
  ON public.reminders (remind_at, id)
  WHERE status = 'scheduled';

CREATE UNIQUE INDEX uq_reminders_active_task
  ON public.reminders (user_id, task_id)
  WHERE task_id IS NOT NULL AND status = 'scheduled';

CREATE UNIQUE INDEX uq_reminders_active_shopping_project
  ON public.reminders (user_id, shopping_project_id)
  WHERE shopping_project_id IS NOT NULL AND status = 'scheduled';

CREATE UNIQUE INDEX uq_reminders_active_recipe
  ON public.reminders (user_id, recipe_id)
  WHERE recipe_id IS NOT NULL AND status = 'scheduled';

CREATE FUNCTION public.validate_reminder_row()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_timezone_names WHERE name = NEW.timezone
  ) THEN
    RAISE EXCEPTION 'Invalid PostgreSQL timezone: %', NEW.timezone
      USING ERRCODE = '22023';
  END IF;

  IF NEW.task_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row ON project_row.id = task_row.project_id
    WHERE task_row.id = NEW.task_id
      AND task_row.user_id = NEW.user_id
      AND project_row.user_id = NEW.user_id
      AND project_row.kind = 'board'
  ) THEN
    RAISE EXCEPTION 'Reminder task target must be an owned Task Board task'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.shopping_project_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.projects AS project_row
    WHERE project_row.id = NEW.shopping_project_id
      AND project_row.user_id = NEW.user_id
      AND project_row.kind = 'shopping'
  ) THEN
    RAISE EXCEPTION 'Reminder shopping target must be an owned Shopping List project'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.recipe_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.recipes AS recipe_row
    WHERE recipe_row.id = NEW.recipe_id
      AND recipe_row.user_id = NEW.user_id
  ) THEN
    RAISE EXCEPTION 'Reminder recipe target must be owned by the reminder user'
      USING ERRCODE = '23514';
  END IF;

  RETURN NEW;
END;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public.validate_reminder_row()
  FROM PUBLIC, anon, authenticated;

CREATE TRIGGER validate_reminder_row
  BEFORE INSERT OR UPDATE OF user_id, task_id, shopping_project_id, recipe_id, timezone, status, fired_at, cancelled_at
  ON public.reminders
  FOR EACH ROW EXECUTE FUNCTION public.validate_reminder_row();

CREATE TRIGGER update_reminders_updated_at
  BEFORE UPDATE ON public.reminders
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;

CREATE POLICY reminders_select_own
  ON public.reminders
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

REVOKE ALL PRIVILEGES ON TABLE public.reminders FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.reminders TO authenticated;

ALTER TABLE public.notifications
  DROP CONSTRAINT notifications_type_check;

ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_type_check
  CHECK (
    type IN (
      'system_message',
      'task_due_soon',
      'task_overdue',
      'shopping_date_upcoming',
      'custom_reminder'
    )
  );

CREATE FUNCTION public.create_or_replace_custom_reminder(
  p_target_kind TEXT,
  p_target_id UUID,
  p_local_date DATE,
  p_local_time TIME WITHOUT TIME ZONE,
  p_timezone TEXT,
  p_remind_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_user_id UUID := auth.uid();
  v_reminder_id UUID;
  v_round_trip TIMESTAMP WITHOUT TIME ZONE;
BEGIN
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'Authentication is required' USING ERRCODE = '42501';
  END IF;
  IF p_target_kind NOT IN ('task', 'shopping_project', 'recipe')
     OR p_target_id IS NULL
     OR p_local_date IS NULL
     OR p_local_time IS NULL
     OR p_timezone IS NULL
     OR btrim(p_timezone) = ''
     OR p_remind_at IS NULL THEN
    RAISE EXCEPTION 'A complete reminder target, local date/time, timezone, and instant are required'
      USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = p_timezone) THEN
    RAISE EXCEPTION 'Invalid PostgreSQL timezone: %', p_timezone USING ERRCODE = '22023';
  END IF;

  v_round_trip := p_remind_at AT TIME ZONE p_timezone;
  IF v_round_trip::date <> p_local_date
     OR v_round_trip::time <> p_local_time THEN
    RAISE EXCEPTION 'Reminder instant does not match the requested local date and time'
      USING ERRCODE = '22023';
  END IF;

  -- Five minutes tolerates an ordinary submit/network race without allowing
  -- the API to silently turn a materially old reminder into a new one.
  IF p_remind_at < clock_timestamp() - interval '5 minutes' THEN
    RAISE EXCEPTION 'A reminder cannot be scheduled materially in the past'
      USING ERRCODE = '22023';
  END IF;

  -- All browser changes use this serial per-target lock; it complements the
  -- partial unique indexes and gives replace semantics under concurrent tabs.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_target_kind || ':' || p_target_id::text, 0));

  UPDATE public.reminders AS reminder_row
  SET remind_at = p_remind_at,
      timezone = p_timezone,
      in_app_enabled = true
  WHERE reminder_row.user_id = v_user_id
    AND reminder_row.status = 'scheduled'
    AND (
      (p_target_kind = 'task' AND reminder_row.task_id = p_target_id)
      OR (p_target_kind = 'shopping_project' AND reminder_row.shopping_project_id = p_target_id)
      OR (p_target_kind = 'recipe' AND reminder_row.recipe_id = p_target_id)
    )
  RETURNING reminder_row.id INTO v_reminder_id;

  IF v_reminder_id IS NULL THEN
    INSERT INTO public.reminders (
      user_id, task_id, shopping_project_id, recipe_id,
      remind_at, timezone, in_app_enabled
    ) VALUES (
      v_user_id,
      CASE WHEN p_target_kind = 'task' THEN p_target_id END,
      CASE WHEN p_target_kind = 'shopping_project' THEN p_target_id END,
      CASE WHEN p_target_kind = 'recipe' THEN p_target_id END,
      p_remind_at, p_timezone, true
    )
    RETURNING id INTO v_reminder_id;
  END IF;

  RETURN v_reminder_id;
END;
$function$;

CREATE FUNCTION public.cancel_custom_reminder(p_reminder_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_user_id UUID := auth.uid();
BEGIN
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'Authentication is required' USING ERRCODE = '42501';
  END IF;

  UPDATE public.reminders
  SET status = 'cancelled',
      cancelled_at = clock_timestamp()
  WHERE id = p_reminder_id
    AND user_id = v_user_id
    AND status = 'scheduled';

  RETURN FOUND;
END;
$function$;

CREATE FUNCTION public.generate_custom_reminders(
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  in_app_created BIGINT,
  cancelled_invalid BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_cancelled_invalid BIGINT := 0;
  v_in_app_created BIGINT := 0;
BEGIN
  -- A task is no longer actionable when completed or archived. Recipes have
  -- is_archived. Projects have no archive column in this repository, so only
  -- their target kind is checked here.
  WITH invalid AS (
    UPDATE public.reminders AS reminder_row
    SET status = 'cancelled',
        cancelled_at = p_now
    WHERE reminder_row.status = 'scheduled'
      AND (
        (reminder_row.task_id IS NOT NULL AND NOT EXISTS (
          SELECT 1
          FROM public.tasks AS task_row
          JOIN public.projects AS project_row ON project_row.id = task_row.project_id
          WHERE task_row.id = reminder_row.task_id
            AND project_row.kind = 'board'
            AND task_row.status <> 'COMPLETED'
            AND task_row.is_archived = false
        ))
        OR (reminder_row.shopping_project_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.projects AS project_row
          WHERE project_row.id = reminder_row.shopping_project_id
            AND project_row.kind = 'shopping'
        ))
        OR (reminder_row.recipe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.recipes AS recipe_row
          WHERE recipe_row.id = reminder_row.recipe_id
            AND recipe_row.is_archived = false
        ))
      )
    RETURNING reminder_row.id
  )
  SELECT count(*) INTO v_cancelled_invalid FROM invalid;

  WITH claimed AS (
    SELECT reminder_row.id,
           reminder_row.user_id,
           reminder_row.task_id,
           reminder_row.shopping_project_id,
           reminder_row.recipe_id,
           task_row.title AS task_title,
           shopping_project.name AS shopping_project_name,
           recipe_row.name AS recipe_name
    FROM public.reminders AS reminder_row
    LEFT JOIN public.tasks AS task_row ON task_row.id = reminder_row.task_id
    LEFT JOIN public.projects AS task_project ON task_project.id = task_row.project_id
    LEFT JOIN public.projects AS shopping_project ON shopping_project.id = reminder_row.shopping_project_id
    LEFT JOIN public.recipes AS recipe_row ON recipe_row.id = reminder_row.recipe_id
    WHERE reminder_row.status = 'scheduled'
      AND reminder_row.in_app_enabled
      AND reminder_row.remind_at <= p_now
      AND (
        (reminder_row.task_id IS NOT NULL
          AND task_project.kind = 'board'
          AND task_row.status <> 'COMPLETED'
          AND task_row.is_archived = false)
        OR (reminder_row.shopping_project_id IS NOT NULL
          AND shopping_project.kind = 'shopping')
        OR (reminder_row.recipe_id IS NOT NULL
          AND recipe_row.is_archived = false)
      )
    ORDER BY reminder_row.remind_at, reminder_row.id
    FOR UPDATE OF reminder_row SKIP LOCKED
  ), inserted_notifications AS (
    INSERT INTO public.notifications (
      user_id, type, title, message, workspace, entity_type, entity_id,
      metadata, dedupe_key, expires_at
    )
    SELECT
      claimed.user_id,
      'custom_reminder',
      CASE
        WHEN claimed.task_id IS NOT NULL THEN 'Task reminder'
        WHEN claimed.shopping_project_id IS NOT NULL THEN 'Shopping reminder'
        ELSE 'Recipe reminder'
      END,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN format('"%s"', left(claimed.task_title, 1900))
        WHEN claimed.shopping_project_id IS NOT NULL THEN format('"%s"', left(claimed.shopping_project_name, 1900))
        ELSE format('"%s"', left(claimed.recipe_name, 1900))
      END,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN 'projects'
        WHEN claimed.shopping_project_id IS NOT NULL THEN 'shopping'
        ELSE 'recipes'
      END,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN 'task'
        WHEN claimed.recipe_id IS NOT NULL THEN 'recipe'
        ELSE NULL
      END,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN claimed.task_id
        WHEN claimed.recipe_id IS NOT NULL THEN claimed.recipe_id
        ELSE NULL
      END,
      jsonb_strip_nulls(jsonb_build_object(
        'reminder_id', claimed.id,
        'shopping_project_id', claimed.shopping_project_id
      )),
      format('custom-reminder:%s', claimed.id),
      NULL
    FROM claimed
    ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
    RETURNING dedupe_key
  ), sent AS (
    UPDATE public.reminders AS reminder_row
    SET status = 'sent', fired_at = p_now
    FROM inserted_notifications
    WHERE inserted_notifications.dedupe_key = format('custom-reminder:%s', reminder_row.id)
    RETURNING reminder_row.id
  )
  SELECT count(*) INTO v_in_app_created FROM sent;

  RETURN QUERY SELECT v_in_app_created, v_cancelled_invalid;
END;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.cancel_custom_reminder(UUID)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.generate_custom_reminders(TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ)
  TO authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_custom_reminder(UUID)
  TO authenticated;

DO $migration_012_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.reminders'::regclass
      AND relkind = 'r' AND relrowsecurity
  ) OR (
    SELECT count(*) FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
  ) <> 13 OR (
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname IN (
        'reminders_pkey', 'reminders_user_id_fkey', 'reminders_one_target_check',
        'reminders_scheduled_in_app_check', 'reminders_status_check',
        'reminders_status_timestamps_check', 'reminders_task_owner_fkey',
        'reminders_shopping_project_owner_fkey', 'reminders_recipe_owner_fkey'
      )
  ) <> 9 OR NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.reminders'::regclass AND tgname = 'validate_reminder_row'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.reminders'::regclass AND tgname = 'update_reminders_updated_at'
  ) THEN
    RAISE EXCEPTION 'Migration 012 postflight failed: reminder table infrastructure mismatch';
  END IF;

  IF to_regclass('public.idx_reminders_due') IS NULL
     OR to_regclass('public.uq_reminders_active_task') IS NULL
     OR to_regclass('public.uq_reminders_active_shopping_project') IS NULL
     OR to_regclass('public.uq_reminders_active_recipe') IS NULL THEN
    RAISE EXCEPTION 'Migration 012 postflight failed: reminder indexes missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reminders'
      AND policyname = 'reminders_select_own' AND cmd = 'SELECT'
      AND roles::TEXT = '{authenticated}'
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reminders'
      AND cmd <> 'SELECT'
  ) OR has_table_privilege('authenticated', 'public.reminders', 'INSERT')
     OR has_table_privilege('authenticated', 'public.reminders', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.reminders', 'DELETE') THEN
    RAISE EXCEPTION 'Migration 012 postflight failed: reminder browser write boundary mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_type_check'
      AND pg_get_constraintdef(oid, true) LIKE '%custom_reminder%'
      AND pg_get_constraintdef(oid, true) LIKE '%task_due_soon%'
      AND pg_get_constraintdef(oid, true) LIKE '%task_overdue%'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.generate_custom_reminders(timestamptz)'::regprocedure
      AND prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) OR has_function_privilege('authenticated', 'public.generate_custom_reminders(timestamptz)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 012 postflight failed: notification or generator security mismatch';
  END IF;
END
$migration_012_postflight$;

COMMIT;

-- Deliberately not executed or registered by this migration:
-- SELECT cron.schedule(
--   'projects-generate-custom-reminders',
--   '* * * * *',
--   $$SELECT * FROM public.generate_custom_reminders();$$
-- );
