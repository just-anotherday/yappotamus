-- Controlled validation for migration 013. Run as one transaction only.
-- Replace both placeholder UUIDs with controlled, non-production test accounts.

BEGIN;

SELECT set_config('app.reminder_email_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.reminder_email_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  board_project_id UUID;
  shopping_project_id UUID;
  recipe_book_id UUID;
  task_in_app_id UUID;
  task_legacy_id UUID;
  task_cancel_id UUID;
  task_invalid_id UUID;
  task_retry_id UUID;
  task_terminal_id UUID;
  recipe_id UUID;
  in_app_reminder_id UUID;
  legacy_reminder_id UUID;
  shopping_reminder_id UUID;
  recipe_reminder_id UUID;
  cancel_reminder_id UUID;
  invalid_reminder_id UUID;
  retry_reminder_id UUID;
  terminal_reminder_id UUID;
  shopping_delivery_id UUID;
  recipe_delivery_id UUID;
  retry_delivery_id UUID;
  terminal_delivery_id UUID;
  claim_delivery_id UUID;
  claim_reminder_id UUID;
  claim_user_id UUID;
  claim_lock_token UUID;
  stale_lock_token UUID;
  claim_attempt_count INTEGER;
  claim_subject TEXT;
  claim_body TEXT;
  generated_in_app BIGINT;
  generated_cancelled BIGINT;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
  future_date DATE;
  future_time TIME WITHOUT TIME ZONE;
  next_retry_at TIMESTAMPTZ;
  before_failure TIMESTAMPTZ;
  after_failure TIMESTAMPTZ;
  expected_attempt INTEGER;
  claimed_attempt INTEGER;
  large_error TEXT := repeat('x', 1200);
BEGIN
  BEGIN
    test_user_id := current_setting('app.reminder_email_test_user_id')::uuid;
    other_user_id := current_setting('app.reminder_email_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled reminder email test user UUID settings';
  END;

  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id) THEN
    RAISE EXCEPTION 'Two distinct controlled existing auth.users accounts are required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'Controlled test user requires a user_settings row';
  END IF;

  UPDATE public.user_settings SET timezone = 'America/New_York' WHERE user_id = test_user_id;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES
    (test_user_id, '__migration_013_board__', 'Rollback-only fixture', 'board'),
    (test_user_id, '__migration_013_shopping__', 'Rollback-only fixture', 'shopping');
  SELECT id INTO board_project_id
  FROM public.projects
  WHERE user_id = test_user_id AND name = '__migration_013_board__';
  SELECT id INTO shopping_project_id
  FROM public.projects
  WHERE user_id = test_user_id AND name = '__migration_013_shopping__';

  INSERT INTO public.recipe_books (user_id, name, description)
  VALUES (test_user_id, '__migration_013_book__', 'Rollback-only fixture')
  RETURNING id INTO recipe_book_id;
  INSERT INTO public.recipes (recipe_book_id, user_id, name)
  VALUES (recipe_book_id, test_user_id, '__migration_013_recipe__')
  RETURNING id INTO recipe_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, completed, status, priority,
    is_pinned, is_archived, metadata, "order"
  ) VALUES
    (board_project_id, test_user_id, '__migration_013_in_app__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (board_project_id, test_user_id, '__migration_013_legacy__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2),
    (board_project_id, test_user_id, '__migration_013_cancel__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 3),
    (board_project_id, test_user_id, '__migration_013_invalid__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 4),
    (board_project_id, test_user_id, '__migration_013_retry__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 5),
    (board_project_id, test_user_id, '__migration_013_terminal__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 6);
  SELECT id INTO task_in_app_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_in_app__';
  SELECT id INTO task_legacy_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_legacy__';
  SELECT id INTO task_cancel_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_cancel__';
  SELECT id INTO task_invalid_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_invalid__';
  SELECT id INTO task_retry_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_retry__';
  SELECT id INTO task_terminal_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_terminal__';

  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  future_date := ((now_instant + interval '1 day') AT TIME ZONE 'America/New_York')::date;
  future_time := ((now_instant + interval '1 day') AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);

  -- The deployed six-argument RPC remains an in-app-only compatibility path.
  legacy_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_legacy_id, future_date, future_time, 'America/New_York', now_instant + interval '1 day'
  );
  IF NOT EXISTS (
    SELECT 1 FROM public.reminders
    WHERE id = legacy_reminder_id AND in_app_enabled AND NOT email_enabled
  ) THEN
    RAISE EXCEPTION 'Legacy six-argument reminder RPC no longer creates in-app-only reminders';
  END IF;

  -- The three supported targets exercise all three valid channel combinations.
  in_app_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_in_app_id, local_date, local_time, 'America/New_York', now_instant, true, false
  );
  shopping_reminder_id := public.create_or_replace_custom_reminder(
    'shopping_project', shopping_project_id, local_date, local_time, 'America/New_York', now_instant, false, true
  );
  recipe_reminder_id := public.create_or_replace_custom_reminder(
    'recipe', recipe_id, local_date, local_time, 'America/New_York', now_instant, true, true
  );

  BEGIN
    PERFORM public.create_or_replace_custom_reminder(
      'task', task_cancel_id, local_date, local_time, 'America/New_York', now_instant + interval '1 day', false, false
    );
    RAISE EXCEPTION 'Neither-channel reminder was incorrectly accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;

  cancel_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_cancel_id, future_date, future_time, 'America/New_York', now_instant + interval '1 day', false, true
  );
  IF NOT public.cancel_custom_reminder(cancel_reminder_id) THEN
    RAISE EXCEPTION 'Scheduled email reminder cancellation failed';
  END IF;

  invalid_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_invalid_id, local_date, local_time, 'America/New_York', now_instant, true, true
  );
  UPDATE public.tasks
  SET status = 'COMPLETED', completed = true
  WHERE id = task_invalid_id;

  retry_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_retry_id, local_date, local_time, 'America/New_York', now_instant, false, true
  );
  terminal_reminder_id := public.create_or_replace_custom_reminder(
    'task',
    task_terminal_id,
    ((now_instant + interval '30 minutes') AT TIME ZONE 'America/New_York')::date,
    ((now_instant + interval '30 minutes') AT TIME ZONE 'America/New_York')::time,
    'America/New_York',
    now_instant + interval '30 minutes',
    false,
    true
  );

  SELECT in_app_created, cancelled_invalid
  INTO generated_in_app, generated_cancelled
  FROM public.generate_custom_reminders(now_instant + interval '1 minute');

  IF generated_in_app <> 2 OR generated_cancelled <> 1 THEN
    RAISE EXCEPTION 'Unexpected generator counts: in-app %, cancelled %', generated_in_app, generated_cancelled;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.notifications
    WHERE dedupe_key = format('custom-reminder:%s', in_app_reminder_id)
  ) OR EXISTS (
    SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = in_app_reminder_id
  ) THEN
    RAISE EXCEPTION 'In-app-only dispatch did not create notification only';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.notifications
    WHERE dedupe_key = format('custom-reminder:%s', shopping_reminder_id)
  ) OR NOT EXISTS (
    SELECT 1 FROM public.reminder_deliveries
    WHERE reminder_id = shopping_reminder_id AND channel = 'email' AND status = 'queued'
  ) THEN
    RAISE EXCEPTION 'Email-only dispatch did not create delivery only';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.notifications
    WHERE dedupe_key = format('custom-reminder:%s', recipe_reminder_id)
  ) OR NOT EXISTS (
    SELECT 1 FROM public.reminder_deliveries
    WHERE reminder_id = recipe_reminder_id AND channel = 'email' AND status = 'queued'
  ) THEN
    RAISE EXCEPTION 'Both-channel dispatch did not create both durable artifacts';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.notifications
    WHERE dedupe_key = format('custom-reminder:%s', cancel_reminder_id)
  ) OR EXISTS (
    SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = cancel_reminder_id
  ) OR NOT EXISTS (
    SELECT 1 FROM public.reminders WHERE id = invalid_reminder_id AND status = 'cancelled'
  ) OR EXISTS (
    SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = invalid_reminder_id
  ) THEN
    RAISE EXCEPTION 'Cancelled or invalid reminder dispatched work';
  END IF;
  IF (
    SELECT count(*) FROM public.reminders
    WHERE id IN (in_app_reminder_id, shopping_reminder_id, recipe_reminder_id)
      AND status = 'sent' AND fired_at IS NOT NULL
  ) <> 3 THEN
    RAISE EXCEPTION 'Selected delivery work was not marked sent after durable dispatch';
  END IF;

  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '2 minutes');
  IF (SELECT count(*) FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', recipe_reminder_id)) <> 1
     OR (SELECT count(*) FROM public.reminder_deliveries WHERE reminder_id = recipe_reminder_id AND channel = 'email') <> 1 THEN
    RAISE EXCEPTION 'Repeat generator invocation created duplicate selected-channel work';
  END IF;

  SELECT id INTO shopping_delivery_id
  FROM public.reminder_deliveries WHERE reminder_id = shopping_reminder_id;
  SELECT id INTO recipe_delivery_id
  FROM public.reminder_deliveries WHERE reminder_id = recipe_reminder_id;
  SELECT id INTO retry_delivery_id
  FROM public.reminder_deliveries WHERE reminder_id = retry_reminder_id;
  SELECT id INTO terminal_delivery_id
  FROM public.reminder_deliveries WHERE reminder_id = terminal_reminder_id;

  -- Claim ordering is intentionally controlled below; production correctness
  -- comes from SKIP LOCKED, not any UUID ordering.
  UPDATE public.reminder_deliveries
  SET next_attempt_at = CASE reminder_id
    WHEN shopping_reminder_id THEN now_instant + interval '2 minutes'
    WHEN recipe_reminder_id THEN now_instant + interval '3 minutes'
    WHEN retry_reminder_id THEN now_instant + interval '9 minutes'
    ELSE next_attempt_at
  END
  WHERE reminder_id IN (shopping_reminder_id, recipe_reminder_id, retry_reminder_id);

  BEGIN
    INSERT INTO public.reminder_deliveries (
      reminder_id, channel, status, attempt_count, next_attempt_at, subject, text_body
    ) VALUES (
      shopping_reminder_id, 'email', 'queued', 0, now_instant, 'Duplicate', 'Duplicate'
    );
    RAISE EXCEPTION 'Duplicate reminder email delivery was incorrectly accepted';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;

  IF has_table_privilege('anon', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'DELETE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'DELETE') THEN
    RAISE EXCEPTION 'Browser role received reminder delivery table access';
  END IF;
  IF has_function_privilege('anon', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Browser role received reminder delivery worker RPC access';
  END IF;

  SELECT delivery_id, reminder_id, user_id, lock_token, attempt_count, subject, text_body
  INTO claim_delivery_id, claim_reminder_id, claim_user_id, claim_lock_token, claim_attempt_count, claim_subject, claim_body
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '2 minutes');
  IF claim_delivery_id <> shopping_delivery_id
     OR claim_reminder_id <> shopping_reminder_id
     OR claim_user_id <> test_user_id
     OR claim_lock_token IS NULL
     OR claim_attempt_count <> 1
     OR claim_subject <> 'Shopping reminder: __migration_013_shopping__'
     OR claim_body <> E'You asked to be reminded about this shopping list.\n\n__migration_013_shopping__' THEN
    RAISE EXCEPTION 'Delivery claim returned an invalid worker payload';
  END IF;
  IF EXISTS (SELECT 1 FROM public.claim_reminder_email_deliveries(1, now_instant + interval '2 minutes')) THEN
    RAISE EXCEPTION 'Second worker claim obtained an active delivery lease';
  END IF;
  IF public.complete_reminder_email_delivery(shopping_delivery_id, gen_random_uuid(), 'wrong-token') THEN
    RAISE EXCEPTION 'Stale delivery lock token completed work';
  END IF;
  IF NOT public.complete_reminder_email_delivery(shopping_delivery_id, claim_lock_token, 'provider-message-1')
     OR NOT EXISTS (
       SELECT 1 FROM public.reminder_deliveries
       WHERE id = shopping_delivery_id AND status = 'sent' AND sent_at IS NOT NULL
         AND provider_message_id = 'provider-message-1'
     ) THEN
    RAISE EXCEPTION 'Correct delivery lock token did not complete work';
  END IF;

  -- Reclaiming an expired processing lease replaces its token and increments
  -- attempts, so the abandoned worker can no longer complete it.
  SELECT delivery_id, lock_token
  INTO claim_delivery_id, stale_lock_token
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '3 minutes');
  IF claim_delivery_id <> recipe_delivery_id THEN
    RAISE EXCEPTION 'Expected recipe delivery to be claimed for lease recovery test';
  END IF;
  SELECT delivery_id, lock_token, attempt_count
  INTO claim_delivery_id, claim_lock_token, claim_attempt_count
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '8 minutes');
  IF claim_delivery_id <> recipe_delivery_id
     OR claim_lock_token = stale_lock_token
     OR claim_attempt_count <> 2
     OR public.complete_reminder_email_delivery(recipe_delivery_id, stale_lock_token, 'stale') THEN
    RAISE EXCEPTION 'Expired delivery lease was not safely reclaimed';
  END IF;
  IF NOT public.record_reminder_email_delivery_failure(recipe_delivery_id, claim_lock_token, false, large_error)
     OR NOT EXISTS (
       SELECT 1 FROM public.reminder_deliveries
       WHERE id = recipe_delivery_id AND status = 'failed'
         AND char_length(last_error) = 1000
     ) THEN
    RAISE EXCEPTION 'Terminal failure did not sanitize and persist error state';
  END IF;

  -- Retryable failures use the bounded 1/5/15/60 minute progression. The
  -- fifth claimed attempt is terminal even if the worker marks it retryable.
  FOR expected_attempt IN 1..5 LOOP
    SELECT delivery_id, lock_token, attempt_count
    INTO claim_delivery_id, claim_lock_token, claimed_attempt
    FROM public.claim_reminder_email_deliveries(
      1,
      CASE
        WHEN expected_attempt = 1 THEN now_instant + interval '9 minutes'
        ELSE next_retry_at
      END
    );
    IF claim_delivery_id <> retry_delivery_id OR claimed_attempt <> expected_attempt THEN
      RAISE EXCEPTION 'Retry delivery claim did not increment deterministically';
    END IF;
    before_failure := clock_timestamp();
    IF NOT public.record_reminder_email_delivery_failure(
      retry_delivery_id, claim_lock_token, true, format('retry %s', expected_attempt)
    ) THEN
      RAISE EXCEPTION 'Retryable delivery failure did not update claimed work';
    END IF;
    after_failure := clock_timestamp();
    SELECT next_attempt_at INTO next_retry_at
    FROM public.reminder_deliveries WHERE id = retry_delivery_id;
    IF expected_attempt < 5 THEN
      IF NOT EXISTS (
        SELECT 1 FROM public.reminder_deliveries
        WHERE id = retry_delivery_id AND status = 'queued'
          AND locked_at IS NULL AND locked_until IS NULL AND lock_token IS NULL
      ) OR next_retry_at NOT BETWEEN
        before_failure + CASE expected_attempt
          WHEN 1 THEN interval '1 minute'
          WHEN 2 THEN interval '5 minutes'
          WHEN 3 THEN interval '15 minutes'
          ELSE interval '60 minutes'
        END - interval '1 second'
        AND after_failure + CASE expected_attempt
          WHEN 1 THEN interval '1 minute'
          WHEN 2 THEN interval '5 minutes'
          WHEN 3 THEN interval '15 minutes'
          ELSE interval '60 minutes'
        END + interval '1 second' THEN
        RAISE EXCEPTION 'Retry backoff was not applied for attempt %', expected_attempt;
      END IF;
    ELSIF NOT EXISTS (
      SELECT 1 FROM public.reminder_deliveries
      WHERE id = retry_delivery_id AND status = 'failed' AND next_attempt_at IS NULL
    ) THEN
      RAISE EXCEPTION 'Fifth retryable attempt was not terminally failed';
    END IF;
  END LOOP;

  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '31 minutes');
  SELECT id INTO terminal_delivery_id
  FROM public.reminder_deliveries WHERE reminder_id = terminal_reminder_id;
  SELECT delivery_id, lock_token
  INTO claim_delivery_id, claim_lock_token
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '32 minutes');
  IF claim_delivery_id <> terminal_delivery_id
     OR NOT public.record_reminder_email_delivery_failure(terminal_delivery_id, claim_lock_token, false, 'recipient unavailable')
     OR NOT EXISTS (
       SELECT 1 FROM public.reminder_deliveries
       WHERE id = terminal_delivery_id AND status = 'failed' AND next_attempt_at IS NULL
     ) THEN
    RAISE EXCEPTION 'Non-retryable failure did not become terminal';
  END IF;
END
$test$;

ROLLBACK;
