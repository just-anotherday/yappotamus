-- Migration 013 controlled validation, Part 3: retry progression.
-- Run as one transaction only. Replace both placeholders in the SQL Editor copy.

BEGIN;

SELECT set_config('app.reminder_email_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.reminder_email_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  board_project_id UUID;
  retry_task_id UUID;
  terminal_task_id UUID;
  retry_reminder_id UUID;
  terminal_reminder_id UUID;
  retry_delivery_id UUID;
  terminal_delivery_id UUID;
  returned_delivery_id UUID;
  lock_token UUID;
  terminal_lock_token UUID;
  returned_attempt INTEGER;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
  next_retry_at TIMESTAMPTZ;
  before_failure TIMESTAMPTZ;
  after_failure TIMESTAMPTZ;
  expected_attempt INTEGER;
  expected_backoff INTERVAL;
BEGIN
  BEGIN
    test_user_id := current_setting('app.reminder_email_test_user_id')::uuid;
    other_user_id := current_setting('app.reminder_email_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled reminder email test user UUID settings';
  END;
  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'Two controlled users and a primary user_settings row are required';
  END IF;

  UPDATE public.user_settings SET timezone = 'America/New_York' WHERE user_id = test_user_id;
  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_013_p3_board__', 'Rollback-only fixture', 'board')
  RETURNING id INTO board_project_id;
  INSERT INTO public.tasks (
    project_id, user_id, title, completed, status, priority,
    is_pinned, is_archived, metadata, "order"
  ) VALUES
    (board_project_id, test_user_id, '__migration_013_p3_retry__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (board_project_id, test_user_id, '__migration_013_p3_terminal__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2);
  SELECT id INTO retry_task_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p3_retry__';
  SELECT id INTO terminal_task_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p3_terminal__';
  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  retry_reminder_id := public.create_or_replace_custom_reminder(
    'task', retry_task_id, local_date, local_time, 'America/New_York', now_instant, false, true
  );
  terminal_reminder_id := public.create_or_replace_custom_reminder(
    'task',
    terminal_task_id,
    local_date,
    local_time,
    'America/New_York', now_instant, false, true
  );
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  SELECT id INTO retry_delivery_id FROM public.reminder_deliveries WHERE reminder_id = retry_reminder_id;
  SELECT id INTO terminal_delivery_id FROM public.reminder_deliveries WHERE reminder_id = terminal_reminder_id;
  IF terminal_delivery_id IS NULL THEN
    RAISE EXCEPTION 'Terminal email delivery fixture was not generated';
  END IF;
  UPDATE public.reminder_deliveries
  SET next_attempt_at = CASE id
    WHEN retry_delivery_id THEN now_instant + interval '2 minutes'
    WHEN terminal_delivery_id THEN now_instant + interval '2 days'
    ELSE next_attempt_at
  END
  WHERE id IN (retry_delivery_id, terminal_delivery_id);

  FOR expected_attempt IN 1..5 LOOP
    SELECT claimed.delivery_id, claimed.lock_token, claimed.attempt_count
    INTO returned_delivery_id, lock_token, returned_attempt
    FROM public.claim_reminder_email_deliveries(
      1,
      CASE WHEN expected_attempt = 1 THEN now_instant + interval '2 minutes' ELSE next_retry_at END
    ) AS claimed;
    IF returned_delivery_id <> retry_delivery_id OR returned_attempt <> expected_attempt THEN
      RAISE EXCEPTION 'Retry claim did not produce attempt %', expected_attempt;
    END IF;
    expected_backoff := CASE expected_attempt
      WHEN 1 THEN interval '1 minute'
      WHEN 2 THEN interval '5 minutes'
      WHEN 3 THEN interval '15 minutes'
      ELSE interval '60 minutes'
    END;
    before_failure := clock_timestamp();
    IF NOT public.record_reminder_email_delivery_failure(
      retry_delivery_id, lock_token, true, format('retry %s', expected_attempt)
    ) THEN
      RAISE EXCEPTION 'Retryable failure did not update the claimed delivery';
    END IF;
    after_failure := clock_timestamp();
    SELECT next_attempt_at INTO next_retry_at FROM public.reminder_deliveries WHERE id = retry_delivery_id;
    IF expected_attempt < 5 THEN
      IF NOT EXISTS (
        SELECT 1 FROM public.reminder_deliveries AS delivery_row
        WHERE delivery_row.id = retry_delivery_id AND delivery_row.status = 'queued'
          AND delivery_row.locked_at IS NULL
          AND delivery_row.locked_until IS NULL
          AND delivery_row.lock_token IS NULL
      ) OR next_retry_at < before_failure + expected_backoff - interval '1 second'
        OR next_retry_at > after_failure + expected_backoff + interval '1 second' THEN
        RAISE EXCEPTION 'Retry backoff did not match attempt %', expected_attempt;
      END IF;
    ELSIF NOT EXISTS (
      SELECT 1 FROM public.reminder_deliveries
      WHERE id = retry_delivery_id AND status = 'failed' AND next_attempt_at IS NULL
    ) THEN
      RAISE EXCEPTION 'Fifth retryable attempt was not terminally failed';
    END IF;
  END LOOP;

  terminal_lock_token := gen_random_uuid();
  UPDATE public.reminder_deliveries
  SET status = 'processing',
      attempt_count = 1,
      next_attempt_at = NULL,
      locked_at = now_instant + interval '2 days',
      locked_until = now_instant + interval '2 days 5 minutes',
      lock_token = terminal_lock_token,
      sent_at = NULL
  WHERE id = terminal_delivery_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Terminal email delivery fixture could not enter processing';
  END IF;
  IF NOT public.record_reminder_email_delivery_failure(
    terminal_delivery_id, terminal_lock_token, false, 'recipient unavailable'
  ) THEN
    RAISE EXCEPTION 'Non-retryable failure RPC rejected the fixture processing token';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.reminder_deliveries AS terminal_delivery
    WHERE terminal_delivery.id = terminal_delivery_id
      AND terminal_delivery.status = 'failed'
      AND terminal_delivery.next_attempt_at IS NULL
      AND terminal_delivery.locked_at IS NULL
      AND terminal_delivery.locked_until IS NULL
      AND terminal_delivery.lock_token IS NULL
      AND terminal_delivery.sent_at IS NULL
      AND terminal_delivery.last_error = 'recipient unavailable'
  ) THEN
    RAISE EXCEPTION 'Non-retryable failure did not leave the fixture delivery terminal';
  END IF;
END;
$test$;

ROLLBACK;
