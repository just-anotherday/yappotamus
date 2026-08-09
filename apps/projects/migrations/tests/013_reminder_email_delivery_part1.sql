-- Migration 013 controlled validation, Part 1: channels and generator.
-- Run as one transaction only. Replace both placeholders in the SQL Editor copy.

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
  recipe_id UUID;
  in_app_reminder_id UUID;
  shopping_reminder_id UUID;
  recipe_reminder_id UUID;
  cancel_reminder_id UUID;
  invalid_reminder_id UUID;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
  future_date DATE;
  future_time TIME WITHOUT TIME ZONE;
  generated_in_app BIGINT;
  generated_cancelled BIGINT;
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
  VALUES
    (test_user_id, '__migration_013_p1_board__', 'Rollback-only fixture', 'board'),
    (test_user_id, '__migration_013_p1_shopping__', 'Rollback-only fixture', 'shopping');
  SELECT id INTO board_project_id FROM public.projects
  WHERE user_id = test_user_id AND name = '__migration_013_p1_board__';
  SELECT id INTO shopping_project_id FROM public.projects
  WHERE user_id = test_user_id AND name = '__migration_013_p1_shopping__';
  INSERT INTO public.recipe_books (user_id, name, description)
  VALUES (test_user_id, '__migration_013_p1_book__', 'Rollback-only fixture')
  RETURNING id INTO recipe_book_id;
  INSERT INTO public.recipes (recipe_book_id, user_id, name)
  VALUES (recipe_book_id, test_user_id, '__migration_013_p1_recipe__')
  RETURNING id INTO recipe_id;
  INSERT INTO public.tasks (
    project_id, user_id, title, completed, status, priority,
    is_pinned, is_archived, metadata, "order"
  ) VALUES
    (board_project_id, test_user_id, '__migration_013_p1_in_app__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (board_project_id, test_user_id, '__migration_013_p1_legacy__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2),
    (board_project_id, test_user_id, '__migration_013_p1_cancel__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 3),
    (board_project_id, test_user_id, '__migration_013_p1_invalid__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 4);
  SELECT id INTO task_in_app_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p1_in_app__';
  SELECT id INTO task_legacy_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p1_legacy__';
  SELECT id INTO task_cancel_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p1_cancel__';
  SELECT id INTO task_invalid_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p1_invalid__';

  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  future_date := ((now_instant + interval '1 day') AT TIME ZONE 'America/New_York')::date;
  future_time := ((now_instant + interval '1 day') AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);

  PERFORM public.create_or_replace_custom_reminder(
    'task', task_legacy_id, future_date, future_time, 'America/New_York', now_instant + interval '1 day'
  );
  IF NOT EXISTS (
    SELECT 1 FROM public.reminders
    WHERE task_id = task_legacy_id AND in_app_enabled AND NOT email_enabled
  ) THEN RAISE EXCEPTION 'Legacy six-argument RPC lost in-app-only behavior'; END IF;

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
      'task', task_cancel_id, future_date, future_time, 'America/New_York', now_instant + interval '1 day', false, false
    );
    RAISE EXCEPTION 'Neither-channel schedule was accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;
  cancel_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_cancel_id, future_date, future_time, 'America/New_York', now_instant + interval '1 day', false, true
  );
  IF NOT public.cancel_custom_reminder(cancel_reminder_id) THEN
    RAISE EXCEPTION 'Scheduled reminder cancellation failed';
  END IF;
  invalid_reminder_id := public.create_or_replace_custom_reminder(
    'task', task_invalid_id, local_date, local_time, 'America/New_York', now_instant, true, true
  );
  UPDATE public.tasks SET status = 'COMPLETED', completed = true WHERE id = task_invalid_id;

  SELECT in_app_created, cancelled_invalid INTO generated_in_app, generated_cancelled
  FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  IF generated_in_app <> 2 OR generated_cancelled <> 1 THEN
    RAISE EXCEPTION 'Unexpected generator counts: in-app %, cancelled %', generated_in_app, generated_cancelled;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', in_app_reminder_id))
     OR EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = in_app_reminder_id)
     OR EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', shopping_reminder_id))
     OR NOT EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = shopping_reminder_id AND status = 'queued')
     OR NOT EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', recipe_reminder_id))
     OR NOT EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = recipe_reminder_id AND status = 'queued') THEN
    RAISE EXCEPTION 'Selected channel dispatch did not match expected durable artifacts';
  END IF;
  IF EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', cancel_reminder_id))
     OR EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = cancel_reminder_id)
     OR NOT EXISTS (SELECT 1 FROM public.reminders WHERE id = invalid_reminder_id AND status = 'cancelled')
     OR EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = invalid_reminder_id) THEN
    RAISE EXCEPTION 'Cancelled or invalid reminder dispatched work';
  END IF;
  IF (
    SELECT count(*) FROM public.reminders
    WHERE id IN (in_app_reminder_id, shopping_reminder_id, recipe_reminder_id)
      AND status = 'sent' AND fired_at IS NOT NULL
  ) <> 3 THEN
    RAISE EXCEPTION 'Dispatched reminders were not marked sent after durable work existed';
  END IF;
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '2 minutes');
  IF (SELECT count(*) FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', recipe_reminder_id)) <> 1
     OR (SELECT count(*) FROM public.reminder_deliveries WHERE reminder_id = recipe_reminder_id) <> 1 THEN
    RAISE EXCEPTION 'Generator repeat created duplicate channel work';
  END IF;
  BEGIN
    INSERT INTO public.reminder_deliveries (reminder_id, channel, status, attempt_count, next_attempt_at, subject, text_body)
    VALUES (shopping_reminder_id, 'email', 'queued', 0, now_instant, 'Duplicate', 'Duplicate');
    RAISE EXCEPTION 'Delivery uniqueness was not enforced';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
  IF has_table_privilege('anon', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'DELETE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'DELETE')
     OR has_function_privilege('anon', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Browser delivery security boundary changed';
  END IF;
END
$test$;

ROLLBACK;
