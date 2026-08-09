-- Controlled validation for migration 012. Run as one transaction only.
-- Replace both placeholder UUIDs with controlled, non-production test accounts.

BEGIN;

SELECT set_config('app.custom_reminder_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.custom_reminder_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  board_project_id UUID;
  shopping_project_id UUID;
  other_shopping_project_id UUID;
  recipe_book_id UUID;
  board_task_id UUID;
  shopping_task_id UUID;
  parentless_task_id UUID;
  recipe_id UUID;
  task_reminder_id UUID;
  shopping_reminder_id UUID;
  recipe_reminder_id UUID;
  now_instant TIMESTAMPTZ := clock_timestamp();
  replacement_at TIMESTAMPTZ;
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
  notification_id UUID;
  generated_count BIGINT;
  cancelled_count BIGINT;
BEGIN
  BEGIN
    test_user_id := current_setting('app.custom_reminder_test_user_id')::uuid;
    other_user_id := current_setting('app.custom_reminder_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled custom-reminder test user UUID settings';
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
    (test_user_id, '__migration_012_board__', 'Rollback-only fixture', 'board'),
    (test_user_id, '__migration_012_shopping__', 'Rollback-only fixture', 'shopping'),
    (other_user_id, '__migration_012_other_shopping__', 'Rollback-only fixture', 'shopping');

  -- The three IDs are read deterministically instead of relying on multi-row RETURNING order.
  SELECT id INTO board_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_012_board__';
  SELECT id INTO shopping_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_012_shopping__';
  SELECT id INTO other_shopping_project_id FROM public.projects WHERE user_id = other_user_id AND name = '__migration_012_other_shopping__';

  INSERT INTO public.recipe_books (user_id, name, description)
  VALUES (test_user_id, '__migration_012_book__', 'Rollback-only fixture')
  RETURNING id INTO recipe_book_id;
  INSERT INTO public.recipes (recipe_book_id, user_id, name)
  VALUES (recipe_book_id, test_user_id, '__migration_012_recipe__')
  RETURNING id INTO recipe_id;
  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order")
  VALUES
    (board_project_id, test_user_id, '__migration_012_task__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (shopping_project_id, test_user_id, '__migration_012_shopping_task__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2),
    (NULL, test_user_id, '__migration_012_parentless_task__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 3);
  SELECT id INTO board_task_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_012_task__';
  SELECT id INTO shopping_task_id FROM public.tasks WHERE project_id = shopping_project_id AND title = '__migration_012_shopping_task__';
  SELECT id INTO parentless_task_id FROM public.tasks WHERE project_id IS NULL AND title = '__migration_012_parentless_task__';

  local_date := ((now_instant + interval '20 minutes') AT TIME ZONE 'America/New_York')::date;
  local_time := ((now_instant + interval '20 minutes') AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);

  task_reminder_id := public.create_or_replace_custom_reminder(
    'task', board_task_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes'
  );
  IF task_reminder_id IS NULL THEN RAISE EXCEPTION 'Board task reminder was not created'; END IF;

  shopping_reminder_id := public.create_or_replace_custom_reminder(
    'shopping_project', shopping_project_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes'
  );
  recipe_reminder_id := public.create_or_replace_custom_reminder(
    'recipe', recipe_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes'
  );

  -- Replace preserves the active reminder ID and only the new schedule remains active.
  replacement_at := now_instant + interval '30 minutes';
  IF public.create_or_replace_custom_reminder(
    'task',
    board_task_id,
    (replacement_at AT TIME ZONE 'America/New_York')::date,
    (replacement_at AT TIME ZONE 'America/New_York')::time,
    'America/New_York',
    replacement_at
  ) <> task_reminder_id THEN RAISE EXCEPTION 'Scheduled reminder replace did not preserve its row'; END IF;

  BEGIN
    PERFORM public.create_or_replace_custom_reminder('task', shopping_task_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes');
    RAISE EXCEPTION 'Shopping task was incorrectly accepted as a Task Board task';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('task', parentless_task_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes');
    RAISE EXCEPTION 'Parentless task was incorrectly accepted as a Task Board task';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('shopping_project', board_project_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes');
    RAISE EXCEPTION 'Board project was incorrectly accepted as shopping target';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('shopping_project', other_shopping_project_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes');
    RAISE EXCEPTION 'Other-user target was incorrectly accepted';
  EXCEPTION WHEN check_violation OR foreign_key_violation THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('task', board_task_id, local_date, local_time, 'Not/A_Timezone', now_instant + interval '20 minutes');
    RAISE EXCEPTION 'Invalid timezone was incorrectly accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('task', board_task_id, local_date, local_time, 'America/New_York', now_instant + interval '20 minutes' + interval '1 hour');
    RAISE EXCEPTION 'Local date/time mismatch was incorrectly accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('task', board_task_id, '2026-03-08', '02:30', 'America/New_York', '2026-03-08 07:30:00+00');
    RAISE EXCEPTION 'Nonexistent spring-forward local time was incorrectly accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;
  PERFORM public.create_or_replace_custom_reminder('task', board_task_id, '2026-11-01', '01:30', 'America/New_York', '2026-11-01 05:30:00+00');
  BEGIN
    PERFORM public.create_or_replace_custom_reminder('recipe', recipe_id, local_date, local_time, 'America/New_York', now_instant - interval '6 minutes');
    RAISE EXCEPTION 'Materially past reminder was incorrectly accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;

  -- Near-now is allowed and is dispatched by the next generator run.
  PERFORM public.create_or_replace_custom_reminder(
    'shopping_project',
    shopping_project_id,
    (now_instant AT TIME ZONE 'America/New_York')::date,
    (now_instant AT TIME ZONE 'America/New_York')::time,
    'America/New_York',
    now_instant
  );

  SELECT in_app_created, cancelled_invalid INTO generated_count, cancelled_count
  FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  IF generated_count <> 1 OR cancelled_count <> 0 THEN RAISE EXCEPTION 'Expected one due notification, found % created and % cancelled', generated_count, cancelled_count; END IF;
  SELECT id INTO notification_id FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', shopping_reminder_id);
  IF notification_id IS NULL THEN RAISE EXCEPTION 'Shopping custom notification missing'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE id = shopping_reminder_id AND status = 'sent' AND fired_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Due reminder was not marked sent atomically';
  END IF;

  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '2 minutes');
  IF (SELECT count(*) FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', shopping_reminder_id)) <> 1 THEN
    RAISE EXCEPTION 'Repeat generator invocation created a duplicate';
  END IF;
  UPDATE public.notifications SET is_read = true WHERE id = notification_id;
  UPDATE public.notifications SET archived_at = clock_timestamp() WHERE id = notification_id;
  DELETE FROM public.notifications WHERE id = notification_id;
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '3 minutes');
  IF EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', shopping_reminder_id))
     OR NOT EXISTS (SELECT 1 FROM public.reminders WHERE id = shopping_reminder_id AND status = 'sent') THEN
    RAISE EXCEPTION 'Inbox lifecycle changed reminder execution state';
  END IF;

  UPDATE public.tasks SET status = 'COMPLETED', completed = true WHERE id = board_task_id;
  SELECT in_app_created, cancelled_invalid INTO generated_count, cancelled_count
  FROM public.generate_custom_reminders(now_instant + interval '40 minutes');
  IF cancelled_count < 1 OR NOT EXISTS (SELECT 1 FROM public.reminders WHERE id = task_reminder_id AND status = 'cancelled') THEN
    RAISE EXCEPTION 'Completed task did not cancel its scheduled reminder';
  END IF;
  IF NOT public.cancel_custom_reminder(recipe_reminder_id) OR NOT EXISTS (SELECT 1 FROM public.reminders WHERE id = recipe_reminder_id AND status = 'cancelled') THEN
    RAISE EXCEPTION 'Scheduled reminder cancellation failed';
  END IF;
  IF public.cancel_custom_reminder(shopping_reminder_id) THEN
    RAISE EXCEPTION 'Sent reminder was incorrectly editable through cancel RPC';
  END IF;
END
$test$;

ROLLBACK;
