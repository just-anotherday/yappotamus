-- Migration 014: preserve a task's calendar due date in custom-reminder
-- notification metadata at dispatch time. Existing notification history is not
-- rewritten.

BEGIN;

DO $migration_014_preflight$
BEGIN
  IF to_regprocedure('public.generate_custom_reminders(timestamp with time zone)') IS NULL THEN
    RAISE EXCEPTION 'Migration 014 requires generate_custom_reminders(timestamptz)';
  ELSIF to_regclass('public.reminder_deliveries') IS NULL THEN
    RAISE EXCEPTION 'Migration 014 requires Migration 013 reminder_deliveries';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'due_on' AND udt_name = 'date'
  ) THEN
    RAISE EXCEPTION 'Migration 014 requires public.tasks.due_on DATE';
  END IF;
END
$migration_014_preflight$;

CREATE OR REPLACE FUNCTION public.generate_custom_reminders(
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (in_app_created BIGINT, cancelled_invalid BIGINT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_cancelled_invalid BIGINT := 0;
  v_in_app_created BIGINT := 0;
BEGIN
  WITH invalid AS (
    UPDATE public.reminders AS reminder_row
    SET status = 'cancelled', cancelled_at = p_now
    WHERE reminder_row.status = 'scheduled'
      AND (
        (reminder_row.task_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.tasks AS task_row
          JOIN public.projects AS project_row ON project_row.id = task_row.project_id
          WHERE task_row.id = reminder_row.task_id AND project_row.kind = 'board'
            AND task_row.status <> 'COMPLETED' AND task_row.is_archived = false
        ))
        OR (reminder_row.shopping_project_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.projects AS project_row
          WHERE project_row.id = reminder_row.shopping_project_id AND project_row.kind = 'shopping'
        ))
        OR (reminder_row.recipe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.recipes AS recipe_row
          WHERE recipe_row.id = reminder_row.recipe_id AND recipe_row.is_archived = false
        ))
      )
    RETURNING reminder_row.id
  ) SELECT count(*) INTO v_cancelled_invalid FROM invalid;

  WITH claimed AS (
    SELECT reminder_row.id, reminder_row.user_id, reminder_row.task_id,
           reminder_row.shopping_project_id, reminder_row.recipe_id,
           reminder_row.in_app_enabled, reminder_row.email_enabled,
           task_row.title AS task_title, task_row.due_on AS task_due_on,
           shopping_project.name AS shopping_project_name, recipe_row.name AS recipe_name
    FROM public.reminders AS reminder_row
    LEFT JOIN public.tasks AS task_row ON task_row.id = reminder_row.task_id
    LEFT JOIN public.projects AS task_project ON task_project.id = task_row.project_id
    LEFT JOIN public.projects AS shopping_project ON shopping_project.id = reminder_row.shopping_project_id
    LEFT JOIN public.recipes AS recipe_row ON recipe_row.id = reminder_row.recipe_id
    WHERE reminder_row.status = 'scheduled' AND reminder_row.remind_at <= p_now
      AND (reminder_row.in_app_enabled OR reminder_row.email_enabled)
      AND (
        (reminder_row.task_id IS NOT NULL AND task_project.kind = 'board' AND task_row.status <> 'COMPLETED' AND task_row.is_archived = false)
        OR (reminder_row.shopping_project_id IS NOT NULL AND shopping_project.kind = 'shopping')
        OR (reminder_row.recipe_id IS NOT NULL AND recipe_row.is_archived = false)
      )
    ORDER BY reminder_row.remind_at, reminder_row.id
    FOR UPDATE OF reminder_row SKIP LOCKED
  ), inserted_notifications AS (
    INSERT INTO public.notifications (user_id, type, title, message, workspace, entity_type, entity_id, metadata, dedupe_key, expires_at)
    SELECT
      claimed.user_id, 'custom_reminder',
      CASE WHEN claimed.task_id IS NOT NULL THEN 'Task reminder' WHEN claimed.shopping_project_id IS NOT NULL THEN 'Shopping reminder' ELSE 'Recipe reminder' END,
      CASE WHEN claimed.task_id IS NOT NULL THEN format('"%s"', left(claimed.task_title, 1900)) WHEN claimed.shopping_project_id IS NOT NULL THEN format('"%s"', left(claimed.shopping_project_name, 1900)) ELSE format('"%s"', left(claimed.recipe_name, 1900)) END,
      CASE WHEN claimed.task_id IS NOT NULL THEN 'projects' WHEN claimed.shopping_project_id IS NOT NULL THEN 'shopping' ELSE 'recipes' END,
      CASE WHEN claimed.task_id IS NOT NULL THEN 'task' WHEN claimed.recipe_id IS NOT NULL THEN 'recipe' ELSE NULL END,
      CASE WHEN claimed.task_id IS NOT NULL THEN claimed.task_id WHEN claimed.recipe_id IS NOT NULL THEN claimed.recipe_id ELSE NULL END,
      jsonb_strip_nulls(jsonb_build_object('reminder_id', claimed.id, 'shopping_project_id', claimed.shopping_project_id, 'due_on', claimed.task_due_on)),
      format('custom-reminder:%s', claimed.id), NULL
    FROM claimed WHERE claimed.in_app_enabled
    ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
    RETURNING dedupe_key
  ), inserted_deliveries AS (
    INSERT INTO public.reminder_deliveries (reminder_id, channel, status, attempt_count, next_attempt_at, subject, text_body)
    SELECT claimed.id, 'email', 'queued', 0, p_now,
      CASE WHEN claimed.task_id IS NOT NULL THEN format('Task reminder: %s', left(coalesce(nullif(btrim(claimed.task_title), ''), 'Untitled'), 128)) WHEN claimed.shopping_project_id IS NOT NULL THEN format('Shopping reminder: %s', left(coalesce(nullif(btrim(claimed.shopping_project_name), ''), 'Untitled'), 128)) ELSE format('Recipe reminder: %s', left(coalesce(nullif(btrim(claimed.recipe_name), ''), 'Untitled'), 128)) END,
      CASE WHEN claimed.task_id IS NOT NULL THEN format('You asked to be reminded about this task.%s%s', E'\n\n', left(coalesce(nullif(btrim(claimed.task_title), ''), 'Untitled'), 128)) WHEN claimed.shopping_project_id IS NOT NULL THEN format('You asked to be reminded about this shopping list.%s%s', E'\n\n', left(coalesce(nullif(btrim(claimed.shopping_project_name), ''), 'Untitled'), 128)) ELSE format('You asked to be reminded about this recipe.%s%s', E'\n\n', left(coalesce(nullif(btrim(claimed.recipe_name), ''), 'Untitled'), 128)) END
    FROM claimed WHERE claimed.email_enabled
    ON CONFLICT (reminder_id, channel) DO NOTHING RETURNING reminder_id
  ), notification_ready AS (
    SELECT dedupe_key FROM inserted_notifications
    UNION
    SELECT notification_row.dedupe_key FROM public.notifications AS notification_row
    JOIN claimed ON notification_row.user_id = claimed.user_id AND notification_row.dedupe_key = format('custom-reminder:%s', claimed.id)
    WHERE claimed.in_app_enabled
  ), delivery_ready AS (
    SELECT reminder_id FROM inserted_deliveries
    UNION
    SELECT delivery_row.reminder_id FROM public.reminder_deliveries AS delivery_row
    JOIN claimed ON delivery_row.reminder_id = claimed.id AND delivery_row.channel = 'email'
    WHERE claimed.email_enabled
  ), sent AS (
    UPDATE public.reminders AS reminder_row SET status = 'sent', fired_at = p_now
    FROM claimed WHERE reminder_row.id = claimed.id
      AND (NOT claimed.in_app_enabled OR EXISTS (SELECT 1 FROM notification_ready WHERE dedupe_key = format('custom-reminder:%s', claimed.id)))
      AND (NOT claimed.email_enabled OR EXISTS (SELECT 1 FROM delivery_ready WHERE reminder_id = claimed.id))
    RETURNING reminder_row.id
  ) SELECT count(*) INTO v_in_app_created FROM inserted_notifications;

  RETURN QUERY SELECT v_in_app_created, v_cancelled_invalid;
END;
$function$;

DO $migration_014_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.generate_custom_reminders(timestamptz)'::regprocedure
      AND prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) THEN
    RAISE EXCEPTION 'Migration 014 postflight failed: generator security mismatch';
  END IF;
END
$migration_014_postflight$;

COMMIT;
