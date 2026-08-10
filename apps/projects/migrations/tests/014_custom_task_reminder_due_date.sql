-- Controlled validation for migration 014. Run as one transaction only after
-- migration 014 and the migration 013 validation have been applied.
-- Replace the placeholder UUID with a controlled, non-production account.

BEGIN;

SELECT set_config('app.custom_reminder_due_date_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  board_project_id UUID;
  shopping_project_id UUID;
  recipe_book_id UUID;
  due_task_id UUID;
  no_due_task_id UUID;
  recipe_id UUID;
  due_reminder_id UUID;
  no_due_reminder_id UUID;
  shopping_reminder_id UUID;
  recipe_reminder_id UUID;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
BEGIN
  BEGIN
    test_user_id := current_setting('app.custom_reminder_due_date_test_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set a controlled custom-reminder due-date test user UUID';
  END;
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'Controlled test user and user_settings row are required';
  END IF;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_014_board__', 'Rollback-only fixture', 'board'),
         (test_user_id, '__migration_014_shopping__', 'Rollback-only fixture', 'shopping');
  SELECT id INTO board_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_014_board__';
  SELECT id INTO shopping_project_id FROM public.projects WHERE user_id = test_user_id AND name = '__migration_014_shopping__';
  INSERT INTO public.recipe_books (user_id, name, description)
  VALUES (test_user_id, '__migration_014_book__', 'Rollback-only fixture') RETURNING id INTO recipe_book_id;
  INSERT INTO public.recipes (recipe_book_id, user_id, name)
  VALUES (recipe_book_id, test_user_id, '__migration_014_recipe__') RETURNING id INTO recipe_id;
  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order", due_on)
  VALUES (board_project_id, test_user_id, '__migration_014_due__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1, DATE '2026-08-14'),
         (board_project_id, test_user_id, '__migration_014_no_due__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2, NULL);
  SELECT id INTO due_task_id FROM public.tasks WHERE title = '__migration_014_due__' AND user_id = test_user_id;
  SELECT id INTO no_due_task_id FROM public.tasks WHERE title = '__migration_014_no_due__' AND user_id = test_user_id;

  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  due_reminder_id := public.create_or_replace_custom_reminder('task', due_task_id, local_date, local_time, 'America/New_York', now_instant, true, false);
  no_due_reminder_id := public.create_or_replace_custom_reminder('task', no_due_task_id, local_date, local_time, 'America/New_York', now_instant, true, false);
  shopping_reminder_id := public.create_or_replace_custom_reminder('shopping_project', shopping_project_id, local_date, local_time, 'America/New_York', now_instant, true, false);
  recipe_reminder_id := public.create_or_replace_custom_reminder('recipe', recipe_id, local_date, local_time, 'America/New_York', now_instant, true, false);

  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  IF (SELECT metadata->>'due_on' FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', due_reminder_id)) <> '2026-08-14' THEN
    RAISE EXCEPTION 'Task custom reminder did not preserve its due_on calendar date';
  END IF;
  IF EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key = format('custom-reminder:%s', no_due_reminder_id) AND metadata ? 'due_on') THEN
    RAISE EXCEPTION 'Null task due_on was not null-stripped';
  END IF;
  IF EXISTS (SELECT 1 FROM public.notifications WHERE dedupe_key IN (format('custom-reminder:%s', shopping_reminder_id), format('custom-reminder:%s', recipe_reminder_id)) AND metadata ? 'due_on') THEN
    RAISE EXCEPTION 'Shopping or recipe reminder received task due_on metadata';
  END IF;
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '2 minutes');
  IF (SELECT count(*) FROM public.notifications WHERE dedupe_key IN (format('custom-reminder:%s', due_reminder_id), format('custom-reminder:%s', no_due_reminder_id), format('custom-reminder:%s', shopping_reminder_id), format('custom-reminder:%s', recipe_reminder_id))) <> 4 THEN
    RAISE EXCEPTION 'Generator rerun was not idempotent';
  END IF;
END
$test$;

ROLLBACK;
