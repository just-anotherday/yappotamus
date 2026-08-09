-- Migration 013: durable, provider-independent email delivery work for custom
-- reminders. This migration does not contact an email provider or register a
-- worker Cron job.

BEGIN;

DO $migration_013_preflight$
DECLARE
  v_channel_constraint TEXT;
BEGIN
  IF to_regclass('public.reminders') IS NULL THEN
    RAISE EXCEPTION 'Migration 013 requires public.reminders';
  ELSIF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'reminders'
      AND column_name = 'email_enabled'
  ) THEN
    RAISE EXCEPTION 'Migration 013 requires public.reminders.email_enabled to be absent';
  ELSIF (
    SELECT count(*)
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
  ) <> 13 THEN
    RAISE EXCEPTION 'Migration 013 found incompatible public.reminders column count';
  ELSIF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'in_app_enabled' AND udt_name = 'bool' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'status' AND udt_name = 'text' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'remind_at' AND udt_name = 'timestamptz' AND is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'Migration 013 found incompatible public.reminders core column shape';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname = 'reminders_one_target_check'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname = 'reminders_status_check'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname = 'reminders_status_timestamps_check'
      AND pg_get_constraintdef(oid, true) LIKE '%scheduled%'
      AND pg_get_constraintdef(oid, true) LIKE '%sent%'
      AND pg_get_constraintdef(oid, true) LIKE '%cancelled%'
  ) THEN
    RAISE EXCEPTION 'Migration 013 requires Migration 012 reminder target and lifecycle constraints';
  END IF;

  SELECT pg_get_constraintdef(oid, true)
  INTO v_channel_constraint
  FROM pg_constraint
  WHERE conrelid = 'public.reminders'::regclass
    AND conname = 'reminders_scheduled_in_app_check';

  IF v_channel_constraint IS NULL
     OR v_channel_constraint NOT LIKE '%in_app_enabled%'
     OR v_channel_constraint NOT LIKE '%scheduled%'
     OR v_channel_constraint LIKE '%email_enabled%' THEN
    RAISE EXCEPTION 'Migration 013 found incompatible reminders channel constraint';
  END IF;

  IF to_regclass('public.reminder_deliveries') IS NOT NULL THEN
    RAISE EXCEPTION 'Migration 013 found an existing public.reminder_deliveries table';
  END IF;

  IF to_regprocedure('public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone)') IS NULL THEN
    RAISE EXCEPTION 'Migration 013 found incompatible create_or_replace_custom_reminder signature';
  ELSIF to_regprocedure('public.cancel_custom_reminder(uuid)') IS NULL THEN
    RAISE EXCEPTION 'Migration 013 requires cancel_custom_reminder(uuid)';
  ELSIF to_regprocedure('public.generate_custom_reminders(timestamp with time zone)') IS NULL THEN
    RAISE EXCEPTION 'Migration 013 requires generate_custom_reminders(timestamptz)';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_proc AS procedure_row
    JOIN pg_namespace AS namespace_row ON namespace_row.oid = procedure_row.pronamespace
    WHERE namespace_row.nspname = 'public'
      AND procedure_row.proname IN (
        'claim_reminder_email_deliveries',
        'complete_reminder_email_delivery',
        'record_reminder_email_delivery_failure'
      )
  ) THEN
    RAISE EXCEPTION 'Migration 013 found existing reminder email worker functions';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_type_check'
      AND pg_get_constraintdef(oid, true) LIKE '%custom_reminder%'
      AND pg_get_constraintdef(oid, true) LIKE '%task_due_soon%'
      AND pg_get_constraintdef(oid, true) LIKE '%task_overdue%'
  ) THEN
    RAISE EXCEPTION 'Migration 013 requires Migration 012 custom notification support';
  END IF;

  IF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
    RAISE EXCEPTION 'Migration 013 requires public.update_updated_at_column()';
  END IF;
END
$migration_013_preflight$;

ALTER TABLE public.reminders
  ADD COLUMN email_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.reminders
  DROP CONSTRAINT reminders_scheduled_in_app_check;

ALTER TABLE public.reminders
  ADD CONSTRAINT reminders_scheduled_channel_check
  CHECK (status <> 'scheduled' OR in_app_enabled OR email_enabled);

CREATE TABLE public.reminder_deliveries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reminder_id UUID NOT NULL
    REFERENCES public.reminders(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NULL,
  locked_at TIMESTAMPTZ NULL,
  locked_until TIMESTAMPTZ NULL,
  lock_token UUID NULL,
  subject TEXT NOT NULL,
  text_body TEXT NOT NULL,
  provider_message_id TEXT NULL,
  last_error TEXT NULL,
  sent_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT reminder_deliveries_channel_check
    CHECK (channel = 'email'),
  CONSTRAINT reminder_deliveries_status_check
    CHECK (status IN ('queued', 'processing', 'sent', 'failed')),
  CONSTRAINT reminder_deliveries_attempt_count_check
    CHECK (attempt_count >= 0),
  CONSTRAINT reminder_deliveries_subject_check
    CHECK (char_length(btrim(subject)) BETWEEN 1 AND 160),
  CONSTRAINT reminder_deliveries_text_body_check
    CHECK (char_length(btrim(text_body)) BETWEEN 1 AND 4000),
  CONSTRAINT reminder_deliveries_provider_message_id_check
    CHECK (provider_message_id IS NULL OR char_length(provider_message_id) <= 255),
  CONSTRAINT reminder_deliveries_last_error_check
    CHECK (last_error IS NULL OR char_length(last_error) <= 1000),
  CONSTRAINT reminder_deliveries_state_check
    CHECK (
      (status = 'queued'
        AND next_attempt_at IS NOT NULL
        AND locked_at IS NULL
        AND locked_until IS NULL
        AND lock_token IS NULL
        AND sent_at IS NULL)
      OR (status = 'processing'
        AND next_attempt_at IS NULL
        AND locked_at IS NOT NULL
        AND locked_until IS NOT NULL
        AND locked_until > locked_at
        AND lock_token IS NOT NULL
        AND sent_at IS NULL)
      OR (status = 'sent'
        AND next_attempt_at IS NULL
        AND locked_at IS NULL
        AND locked_until IS NULL
        AND lock_token IS NULL
        AND sent_at IS NOT NULL)
      OR (status = 'failed'
        AND next_attempt_at IS NULL
        AND locked_at IS NULL
        AND locked_until IS NULL
        AND lock_token IS NULL
        AND sent_at IS NULL)
    ),
  CONSTRAINT reminder_deliveries_reminder_channel_key
    UNIQUE (reminder_id, channel)
);

CREATE INDEX idx_reminder_deliveries_claim
  ON public.reminder_deliveries (next_attempt_at, id)
  WHERE status = 'queued';

CREATE INDEX idx_reminder_deliveries_expired_lock
  ON public.reminder_deliveries (locked_until, id)
  WHERE status = 'processing';

CREATE TRIGGER update_reminder_deliveries_updated_at
  BEFORE UPDATE ON public.reminder_deliveries
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.reminder_deliveries ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.reminder_deliveries
  FROM PUBLIC, anon, authenticated;

-- The eight-argument function is the channel-aware API. The existing six-
-- argument function below remains the deployed frontend compatibility API.
CREATE FUNCTION public.create_or_replace_custom_reminder(
  p_target_kind TEXT,
  p_target_id UUID,
  p_local_date DATE,
  p_local_time TIME WITHOUT TIME ZONE,
  p_timezone TEXT,
  p_remind_at TIMESTAMPTZ,
  p_in_app_enabled BOOLEAN,
  p_email_enabled BOOLEAN
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
     OR p_remind_at IS NULL
     OR p_in_app_enabled IS NULL
     OR p_email_enabled IS NULL THEN
    RAISE EXCEPTION 'A complete reminder target, local date/time, timezone, instant, and channel selection are required'
      USING ERRCODE = '22023';
  END IF;
  IF NOT p_in_app_enabled AND NOT p_email_enabled THEN
    RAISE EXCEPTION 'Choose at least one reminder delivery channel'
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
  IF p_remind_at < clock_timestamp() - interval '5 minutes' THEN
    RAISE EXCEPTION 'A reminder cannot be scheduled materially in the past'
      USING ERRCODE = '22023';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_target_kind || ':' || p_target_id::text, 0));

  UPDATE public.reminders AS reminder_row
  SET remind_at = p_remind_at,
      timezone = p_timezone,
      in_app_enabled = p_in_app_enabled,
      email_enabled = p_email_enabled
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
      remind_at, timezone, in_app_enabled, email_enabled
    ) VALUES (
      v_user_id,
      CASE WHEN p_target_kind = 'task' THEN p_target_id END,
      CASE WHEN p_target_kind = 'shopping_project' THEN p_target_id END,
      CASE WHEN p_target_kind = 'recipe' THEN p_target_id END,
      p_remind_at, p_timezone, p_in_app_enabled, p_email_enabled
    )
    RETURNING id INTO v_reminder_id;
  END IF;

  RETURN v_reminder_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.create_or_replace_custom_reminder(
  p_target_kind TEXT,
  p_target_id UUID,
  p_local_date DATE,
  p_local_time TIME WITHOUT TIME ZONE,
  p_timezone TEXT,
  p_remind_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  SELECT public.create_or_replace_custom_reminder(
    p_target_kind,
    p_target_id,
    p_local_date,
    p_local_time,
    p_timezone,
    p_remind_at,
    true,
    false
  );
$function$;

CREATE OR REPLACE FUNCTION public.generate_custom_reminders(
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
           reminder_row.in_app_enabled,
           reminder_row.email_enabled,
           task_row.title AS task_title,
           shopping_project.name AS shopping_project_name,
           recipe_row.name AS recipe_name
    FROM public.reminders AS reminder_row
    LEFT JOIN public.tasks AS task_row ON task_row.id = reminder_row.task_id
    LEFT JOIN public.projects AS task_project ON task_project.id = task_row.project_id
    LEFT JOIN public.projects AS shopping_project ON shopping_project.id = reminder_row.shopping_project_id
    LEFT JOIN public.recipes AS recipe_row ON recipe_row.id = reminder_row.recipe_id
    WHERE reminder_row.status = 'scheduled'
      AND reminder_row.remind_at <= p_now
      AND (reminder_row.in_app_enabled OR reminder_row.email_enabled)
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
    WHERE claimed.in_app_enabled
    ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
    RETURNING dedupe_key
  ), inserted_deliveries AS (
    INSERT INTO public.reminder_deliveries (
      reminder_id, channel, status, attempt_count, next_attempt_at,
      subject, text_body
    )
    SELECT
      claimed.id,
      'email',
      'queued',
      0,
      p_now,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN format(
          'Task reminder: %s',
          left(coalesce(nullif(btrim(claimed.task_title), ''), 'Untitled'), 128)
        )
        WHEN claimed.shopping_project_id IS NOT NULL THEN format(
          'Shopping reminder: %s',
          left(coalesce(nullif(btrim(claimed.shopping_project_name), ''), 'Untitled'), 128)
        )
        ELSE format(
          'Recipe reminder: %s',
          left(coalesce(nullif(btrim(claimed.recipe_name), ''), 'Untitled'), 128)
        )
      END,
      CASE
        WHEN claimed.task_id IS NOT NULL THEN format(
          'You asked to be reminded about this task.%s%s',
          E'\n\n', left(coalesce(nullif(btrim(claimed.task_title), ''), 'Untitled'), 128)
        )
        WHEN claimed.shopping_project_id IS NOT NULL THEN format(
          'You asked to be reminded about this shopping list.%s%s',
          E'\n\n', left(coalesce(nullif(btrim(claimed.shopping_project_name), ''), 'Untitled'), 128)
        )
        ELSE format(
          'You asked to be reminded about this recipe.%s%s',
          E'\n\n', left(coalesce(nullif(btrim(claimed.recipe_name), ''), 'Untitled'), 128)
        )
      END
    FROM claimed
    WHERE claimed.email_enabled
    ON CONFLICT (reminder_id, channel) DO NOTHING
    RETURNING reminder_id
  ), notification_ready AS (
    SELECT dedupe_key FROM inserted_notifications
    UNION
    SELECT notification_row.dedupe_key
    FROM public.notifications AS notification_row
    JOIN claimed ON notification_row.user_id = claimed.user_id
      AND notification_row.dedupe_key = format('custom-reminder:%s', claimed.id)
    WHERE claimed.in_app_enabled
  ), delivery_ready AS (
    SELECT reminder_id FROM inserted_deliveries
    UNION
    SELECT delivery_row.reminder_id
    FROM public.reminder_deliveries AS delivery_row
    JOIN claimed ON delivery_row.reminder_id = claimed.id
      AND delivery_row.channel = 'email'
    WHERE claimed.email_enabled
  ), sent AS (
    UPDATE public.reminders AS reminder_row
    SET status = 'sent',
        fired_at = p_now
    FROM claimed
    WHERE reminder_row.id = claimed.id
      AND (NOT claimed.in_app_enabled OR EXISTS (
        SELECT 1 FROM notification_ready
        WHERE dedupe_key = format('custom-reminder:%s', claimed.id)
      ))
      AND (NOT claimed.email_enabled OR EXISTS (
        SELECT 1 FROM delivery_ready
        WHERE reminder_id = claimed.id
      ))
    RETURNING reminder_row.id
  )
  SELECT count(*) INTO v_in_app_created FROM inserted_notifications;

  RETURN QUERY SELECT v_in_app_created, v_cancelled_invalid;
END;
$function$;

CREATE FUNCTION public.claim_reminder_email_deliveries(
  p_limit INTEGER,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  delivery_id UUID,
  reminder_id UUID,
  user_id UUID,
  lock_token UUID,
  attempt_count INTEGER,
  subject TEXT,
  text_body TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
    RAISE EXCEPTION 'Delivery claim limit must be between 1 and 100'
      USING ERRCODE = '22023';
  END IF;

  -- A worker which dies after its fifth claim has exhausted the bounded retry
  -- budget. It is terminally failed rather than left leased forever.
  UPDATE public.reminder_deliveries AS delivery_row
  SET status = 'failed',
      next_attempt_at = NULL,
      locked_at = NULL,
      locked_until = NULL,
      lock_token = NULL,
      last_error = coalesce(delivery_row.last_error, 'delivery lease expired after maximum attempts'),
      updated_at = p_now
  WHERE delivery_row.status = 'processing'
    AND delivery_row.locked_until <= p_now
    AND delivery_row.attempt_count >= 5;

  RETURN QUERY
  WITH candidates AS (
    SELECT delivery_row.id
    FROM public.reminder_deliveries AS delivery_row
    WHERE (
      delivery_row.status = 'queued'
      AND delivery_row.next_attempt_at <= p_now
      AND delivery_row.attempt_count < 5
    ) OR (
      delivery_row.status = 'processing'
      AND delivery_row.locked_until <= p_now
      AND delivery_row.attempt_count < 5
    )
    ORDER BY coalesce(delivery_row.next_attempt_at, delivery_row.locked_until), delivery_row.id
    FOR UPDATE SKIP LOCKED
    LIMIT p_limit
  ), claimed AS (
    UPDATE public.reminder_deliveries AS delivery_row
    SET status = 'processing',
        attempt_count = delivery_row.attempt_count + 1,
        next_attempt_at = NULL,
        locked_at = p_now,
        locked_until = p_now + interval '5 minutes',
        lock_token = gen_random_uuid(),
        updated_at = p_now
    FROM candidates
    WHERE delivery_row.id = candidates.id
    RETURNING delivery_row.id,
              delivery_row.reminder_id,
              delivery_row.lock_token,
              delivery_row.attempt_count,
              delivery_row.subject,
              delivery_row.text_body
  )
  SELECT claimed.id,
         claimed.reminder_id,
         reminder_row.user_id,
         claimed.lock_token,
         claimed.attempt_count,
         claimed.subject,
         claimed.text_body
  FROM claimed
  JOIN public.reminders AS reminder_row ON reminder_row.id = claimed.reminder_id;
END;
$function$;

CREATE FUNCTION public.complete_reminder_email_delivery(
  p_delivery_id UUID,
  p_lock_token UUID,
  p_provider_message_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF p_delivery_id IS NULL OR p_lock_token IS NULL THEN
    RAISE EXCEPTION 'A delivery ID and lock token are required' USING ERRCODE = '22023';
  END IF;

  UPDATE public.reminder_deliveries
  SET status = 'sent',
      next_attempt_at = NULL,
      locked_at = NULL,
      locked_until = NULL,
      lock_token = NULL,
      provider_message_id = left(nullif(btrim(p_provider_message_id), ''), 255),
      last_error = NULL,
      sent_at = clock_timestamp()
  WHERE id = p_delivery_id
    AND status = 'processing'
    AND lock_token = p_lock_token;

  RETURN FOUND;
END;
$function$;

CREATE FUNCTION public.record_reminder_email_delivery_failure(
  p_delivery_id UUID,
  p_lock_token UUID,
  p_retryable BOOLEAN,
  p_safe_error TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  v_safe_error TEXT;
BEGIN
  IF p_delivery_id IS NULL OR p_lock_token IS NULL OR p_retryable IS NULL THEN
    RAISE EXCEPTION 'A delivery ID, lock token, and retry classification are required'
      USING ERRCODE = '22023';
  END IF;

  v_safe_error := left(coalesce(nullif(btrim(p_safe_error), ''), 'email delivery failed'), 1000);

  UPDATE public.reminder_deliveries AS delivery_row
  SET status = CASE
        WHEN NOT p_retryable OR delivery_row.attempt_count >= 5 THEN 'failed'
        ELSE 'queued'
      END,
      next_attempt_at = CASE
        WHEN NOT p_retryable OR delivery_row.attempt_count >= 5 THEN NULL
        WHEN delivery_row.attempt_count = 1 THEN v_now + interval '1 minute'
        WHEN delivery_row.attempt_count = 2 THEN v_now + interval '5 minutes'
        WHEN delivery_row.attempt_count = 3 THEN v_now + interval '15 minutes'
        ELSE v_now + interval '60 minutes'
      END,
      locked_at = NULL,
      locked_until = NULL,
      lock_token = NULL,
      last_error = v_safe_error,
      sent_at = NULL,
      updated_at = v_now
  WHERE delivery_row.id = p_delivery_id
    AND delivery_row.status = 'processing'
    AND delivery_row.lock_token = p_lock_token;

  RETURN FOUND;
END;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ, BOOLEAN, BOOLEAN)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.cancel_custom_reminder(UUID)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.generate_custom_reminders(TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.claim_reminder_email_deliveries(INTEGER, TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.complete_reminder_email_delivery(UUID, UUID, TEXT)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.record_reminder_email_delivery_failure(UUID, UUID, BOOLEAN, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ)
  TO authenticated;
GRANT EXECUTE ON FUNCTION public.create_or_replace_custom_reminder(TEXT, UUID, DATE, TIME WITHOUT TIME ZONE, TEXT, TIMESTAMPTZ, BOOLEAN, BOOLEAN)
  TO authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_custom_reminder(UUID)
  TO authenticated;

DO $migration_013_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminders'
      AND column_name = 'email_enabled' AND udt_name = 'bool'
      AND is_nullable = 'NO' AND column_default = 'false'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname = 'reminders_scheduled_channel_check'
      AND pg_get_constraintdef(oid, true) LIKE '%in_app_enabled%'
      AND pg_get_constraintdef(oid, true) LIKE '%email_enabled%'
  ) OR EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.reminders'::regclass
      AND conname = 'reminders_scheduled_in_app_check'
  ) THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: reminders email channel extension mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.reminder_deliveries'::regclass
      AND relkind = 'r' AND relrowsecurity
  ) OR (
    SELECT count(*) FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'reminder_deliveries'
  ) <> 16 OR (
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'public.reminder_deliveries'::regclass
      AND conname IN (
        'reminder_deliveries_pkey',
        'reminder_deliveries_reminder_id_fkey',
        'reminder_deliveries_channel_check',
        'reminder_deliveries_status_check',
        'reminder_deliveries_attempt_count_check',
        'reminder_deliveries_subject_check',
        'reminder_deliveries_text_body_check',
        'reminder_deliveries_provider_message_id_check',
        'reminder_deliveries_last_error_check',
        'reminder_deliveries_state_check',
        'reminder_deliveries_reminder_channel_key'
      )
  ) <> 11 OR NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.reminder_deliveries'::regclass
      AND tgname = 'update_reminder_deliveries_updated_at'
      AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: reminder delivery table mismatch';
  END IF;

  IF to_regclass('public.idx_reminder_deliveries_claim') IS NULL
     OR to_regclass('public.idx_reminder_deliveries_expired_lock') IS NULL
     OR EXISTS (
       SELECT 1 FROM pg_policies
       WHERE schemaname = 'public' AND tablename = 'reminder_deliveries'
     ) OR has_table_privilege('anon', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'DELETE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'DELETE') THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: delivery queue security mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone,boolean,boolean)'::regprocedure
      AND prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone)'::regprocedure
      AND prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) OR NOT has_function_privilege(
    'authenticated',
    'public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone)',
    'EXECUTE'
  ) OR NOT has_function_privilege(
    'authenticated',
    'public.create_or_replace_custom_reminder(text,uuid,date,time without time zone,text,timestamp with time zone,boolean,boolean)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: create/replace RPC compatibility mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = 'public.generate_custom_reminders(timestamptz)'::regprocedure
      AND prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) OR has_function_privilege('authenticated', 'public.generate_custom_reminders(timestamptz)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: custom reminder generator security mismatch';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid IN (
      'public.claim_reminder_email_deliveries(integer,timestamptz)'::regprocedure,
      'public.complete_reminder_email_delivery(uuid,uuid,text)'::regprocedure,
      'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)'::regprocedure
    )
      AND (NOT prosecdef OR NOT (proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]))
  ) OR has_function_privilege('anon', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 013 postflight failed: worker RPC security mismatch';
  END IF;
END
$migration_013_postflight$;

COMMIT;

-- Deliberately not executed or registered by this migration:
-- SELECT cron.schedule(
--   'projects-send-reminder-emails',
--   '* * * * *',
--   $$SELECT ... trusted worker invocation only ...$$
-- );
