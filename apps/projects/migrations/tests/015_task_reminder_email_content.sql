-- Controlled validation for migration 015. Run as one transaction only after
-- migration 015. Replace the placeholder with a controlled, non-production account.

BEGIN;

SELECT set_config('app.task_reminder_email_content_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  board_project_id UUID;
  moved_project_id UUID;
  shopping_project_id UUID;
  recipe_book_id UUID;
  due_task_id UUID;
  no_due_task_id UUID;
  in_app_task_id UUID;
  boundary_task_id UUID;
  recipe_id UUID;
  due_reminder_id UUID;
  no_due_reminder_id UUID;
  in_app_reminder_id UUID;
  boundary_reminder_id UUID;
  shopping_reminder_id UUID;
  recipe_reminder_id UUID;
  due_subject TEXT;
  due_body TEXT;
  no_due_body TEXT;
  due_url TEXT;
  no_due_url TEXT;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
BEGIN
  BEGIN
    test_user_id := current_setting('app.task_reminder_email_content_test_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set a controlled task-reminder email-content test user UUID';
  END;
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'Controlled test user and user_settings row are required';
  END IF;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_015_board__', 'Rollback-only fixture', 'board'),
         (test_user_id, '__migration_015_moved__', 'Rollback-only fixture', 'board'),
         (test_user_id, '__migration_015_shopping__', 'Rollback-only fixture', 'shopping');
  SELECT id INTO board_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_015_board__';
  SELECT id INTO moved_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_015_moved__';
  SELECT id INTO shopping_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_015_shopping__';
  INSERT INTO public.recipe_books (user_id, name, description) VALUES (test_user_id, '__migration_015_book__', 'Rollback-only fixture') RETURNING id INTO recipe_book_id;
  INSERT INTO public.recipes (recipe_book_id, user_id, name) VALUES (recipe_book_id, test_user_id, '__migration_015_recipe__') RETURNING id INTO recipe_id;
  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order", due_on)
  VALUES (board_project_id, test_user_id, '__migration_015_due__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1, DATE '2026-08-14'),
         (board_project_id, test_user_id, '__migration_015_no_due__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2, NULL),
         (board_project_id, test_user_id, '__migration_015_in_app__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 3, NULL),
         (board_project_id, test_user_id, repeat('x', 300), false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 4, DATE '2026-08-14');
  SELECT id INTO due_task_id FROM public.tasks WHERE user_id = test_user_id AND title = '__migration_015_due__';
  SELECT id INTO no_due_task_id FROM public.tasks WHERE user_id = test_user_id AND title = '__migration_015_no_due__';
  SELECT id INTO in_app_task_id FROM public.tasks WHERE user_id = test_user_id AND title = '__migration_015_in_app__';
  SELECT id INTO boundary_task_id FROM public.tasks WHERE user_id = test_user_id AND title = repeat('x', 300);

  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  due_reminder_id := public.create_or_replace_custom_reminder('task', due_task_id, local_date, local_time, 'America/New_York', now_instant, true, true);
  no_due_reminder_id := public.create_or_replace_custom_reminder('task', no_due_task_id, local_date, local_time, 'America/New_York', now_instant, false, true);
  in_app_reminder_id := public.create_or_replace_custom_reminder('task', in_app_task_id, local_date, local_time, 'America/New_York', now_instant, true, false);
  boundary_reminder_id := public.create_or_replace_custom_reminder('task', boundary_task_id, local_date, local_time, 'America/New_York', now_instant, false, true);
  shopping_reminder_id := public.create_or_replace_custom_reminder('shopping_project', shopping_project_id, local_date, local_time, 'America/New_York', now_instant, true, true);
  recipe_reminder_id := public.create_or_replace_custom_reminder('recipe', recipe_id, local_date, local_time, 'America/New_York', now_instant, true, true);

  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  SELECT subject, text_body INTO due_subject, due_body FROM public.reminder_deliveries WHERE reminder_id = due_reminder_id AND channel = 'email';
  SELECT text_body INTO no_due_body FROM public.reminder_deliveries WHERE reminder_id = no_due_reminder_id AND channel = 'email';
  due_url := 'https://projects.yapvibes.com/?board=projects&project=' || board_project_id::text || '&task=' || due_task_id::text;
  no_due_url := 'https://projects.yapvibes.com/?board=projects&project=' || board_project_id::text || '&task=' || no_due_task_id::text;
  IF due_subject <> 'Task reminder: __migration_015_due__'
     OR due_body <> 'You asked to be reminded about this task.' || E'\n\n' || '__migration_015_due__' || E'\n\nDue: Aug 14, 2026\n\nView task:\n' || due_url
     OR char_length(due_body) - char_length(replace(due_body, due_url, '')) <> char_length(due_url)
     OR position(chr(91) || 'https://' IN due_body) <> 0 THEN
    RAISE EXCEPTION 'Due-date task email content did not match the immutable contract';
  END IF;
  IF no_due_body <> 'You asked to be reminded about this task.' || E'\n\n' || '__migration_015_no_due__' || E'\n\nView task:\n' || no_due_url
     OR no_due_body LIKE '%Due:%'
     OR char_length(no_due_body) - char_length(replace(no_due_body, no_due_url, '')) <> char_length(no_due_url)
     OR position(chr(91) || 'https://' IN no_due_body) <> 0 THEN
    RAISE EXCEPTION 'Null task due_on email content did not omit the Due line';
  END IF;
  IF EXISTS (SELECT 1 FROM public.reminder_deliveries WHERE reminder_id = in_app_reminder_id)
     OR NOT EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', in_app_reminder_id))
     OR NOT EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', due_reminder_id)) THEN
    RAISE EXCEPTION 'In-app-only or dual-channel durable artifacts regressed';
  END IF;
  IF (SELECT text_body FROM public.reminder_deliveries WHERE reminder_id = shopping_reminder_id) <> 'You asked to be reminded about this shopping list.' || E'\n\n' || '__migration_015_shopping__'
     OR (SELECT text_body FROM public.reminder_deliveries WHERE reminder_id = recipe_reminder_id) <> 'You asked to be reminded about this recipe.' || E'\n\n' || '__migration_015_recipe__' THEN
    RAISE EXCEPTION 'Shopping or recipe email content changed';
  END IF;
  IF (SELECT metadata->>'due_on' FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', due_reminder_id)) <> '2026-08-14' THEN
    RAISE EXCEPTION 'Migration 014 task due_on notification metadata regressed';
  END IF;
  IF EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', in_app_reminder_id) AND metadata ? 'due_on') THEN
    RAISE EXCEPTION 'Null task due_on notification metadata was not null-stripped';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.notifications
    WHERE dedupe_key IN (format('custom-reminder:%s', shopping_reminder_id), format('custom-reminder:%s', recipe_reminder_id))
      AND metadata ? 'due_on'
  ) THEN
    RAISE EXCEPTION 'Shopping or recipe notification received task due_on metadata';
  END IF;

  UPDATE public.tasks SET title = '__migration_015_changed__', due_on = DATE '2026-08-20', project_id = moved_project_id WHERE id = due_task_id;
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '2 minutes');
  IF (SELECT subject FROM public.reminder_deliveries WHERE reminder_id = due_reminder_id) <> due_subject
     OR (SELECT text_body FROM public.reminder_deliveries WHERE reminder_id = due_reminder_id) <> due_body THEN
    RAISE EXCEPTION 'Existing delivery content was rewritten after task mutation';
  END IF;
  IF (SELECT count(*) FROM public.reminder_deliveries WHERE reminder_id IN (due_reminder_id, no_due_reminder_id, shopping_reminder_id, recipe_reminder_id)) <> 4
     OR (SELECT count(*) FROM public.notifications WHERE dedupe_key IN (format('custom-reminder:%s', due_reminder_id), format('custom-reminder:%s', in_app_reminder_id), format('custom-reminder:%s', shopping_reminder_id), format('custom-reminder:%s', recipe_reminder_id))) <> 4 THEN
    RAISE EXCEPTION 'Generator rerun was not idempotent';
  END IF;
  IF char_length(due_body) > 4000 THEN
    RAISE EXCEPTION 'Task email body exceeds reminder_deliveries length constraint';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.reminder_deliveries AS delivery_row
    JOIN public.reminders AS reminder_row ON reminder_row.id = delivery_row.reminder_id
    WHERE reminder_row.task_id = boundary_task_id
      AND char_length(delivery_row.subject) <= 160
      AND char_length(delivery_row.text_body) <= 4000
  ) THEN
    RAISE EXCEPTION 'Maximum-length task title did not produce constraint-safe email content';
  END IF;
END
$test$;

ROLLBACK;
