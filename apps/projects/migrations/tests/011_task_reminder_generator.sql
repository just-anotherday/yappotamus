-- Controlled validation for migration 011.
--
-- This script is safe for the project's single live database only when run as
-- one complete transaction. It creates isolated rows for a controlled existing
-- test account and always ends with ROLLBACK. Do not replace ROLLBACK with
-- COMMIT. Do not use a customer or personal production account as the fixture
-- owner.

BEGIN;

-- Replace only this value with the UUID of a controlled existing test account.
-- The guard below prevents fixture creation until it is replaced.
SELECT set_config(
  'app.task_reminder_test_user_id',
  'REPLACE_WITH_CONTROLLED_TEST_USER_UUID',
  true
);

DO $test$
DECLARE
  test_user_id UUID;
  test_project_id UUID;
  due_today_task_id UUID;
  due_tomorrow_task_id UUID;
  overdue_task_id UUID;
  completed_task_id UUID;
  archived_task_id UUID;
  changed_date_task_id UUID;
  reopened_task_id UUID;
  dst_task_id UUID;
  null_timezone_task_id UUID;
  fixture_event_count INTEGER;
  fixture_notification_count INTEGER;
BEGIN
  BEGIN
    test_user_id := current_setting('app.task_reminder_test_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION
      'Set app.task_reminder_test_user_id to a controlled existing auth.users UUID';
  END;

  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id) THEN
    RAISE EXCEPTION 'Controlled test user does not exist';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'Controlled test user requires a user_settings row';
  END IF;

  -- This temporary setting is rolled back with every fixture and assertion.
  UPDATE public.user_settings
  SET timezone = 'America/New_York'
  WHERE user_id = test_user_id;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_011_fixture__', 'Rollback-only test fixture', 'board')
  RETURNING id INTO test_project_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_due_today__', '', false, 'TODO', 'MEDIUM', '2026-08-07', '2026-08-07T00:00:00Z', false, false, '{}'::jsonb, 1)
  RETURNING id INTO due_today_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_due_tomorrow__', '', false, 'TODO', 'MEDIUM', '2026-08-08', '2026-08-08T00:00:00Z', false, false, '{}'::jsonb, 2)
  RETURNING id INTO due_tomorrow_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_overdue__', '', false, 'TODO', 'MEDIUM', '2026-08-06', '2026-08-06T00:00:00Z', false, false, '{}'::jsonb, 3)
  RETURNING id INTO overdue_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_completed__', '', true, 'COMPLETED', 'MEDIUM', '2026-08-07', '2026-08-07T00:00:00Z', false, false, '{}'::jsonb, 4)
  RETURNING id INTO completed_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_archived__', '', false, 'TODO', 'MEDIUM', '2026-08-07', '2026-08-07T00:00:00Z', false, true, '{}'::jsonb, 5)
  RETURNING id INTO archived_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_changed_date__', '', false, 'TODO', 'MEDIUM', '2026-08-08', '2026-08-08T00:00:00Z', false, false, '{}'::jsonb, 6)
  RETURNING id INTO changed_date_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_reopened__', '', false, 'TODO', 'MEDIUM', '2026-08-07', '2026-08-07T00:00:00Z', false, false, '{}'::jsonb, 7)
  RETURNING id INTO reopened_task_id;

  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_dst__', '', false, 'TODO', 'MEDIUM', '2026-11-02', '2026-11-02T00:00:00Z', false, false, '{}'::jsonb, 8)
  RETURNING id INTO dst_task_id;

  -- New York local date is 2026-08-07 at this UTC instant.
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');

  SELECT count(*) INTO fixture_event_count
  FROM public.task_reminder_events
  WHERE task_id IN (
    due_today_task_id, due_tomorrow_task_id, overdue_task_id,
    completed_task_id, archived_task_id, changed_date_task_id, reopened_task_id
  );
  IF fixture_event_count <> 5 THEN
    RAISE EXCEPTION 'Expected five initial fixture ledger events, found %', fixture_event_count;
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.task_reminder_events
    WHERE task_id IN (completed_task_id, archived_task_id)
  ) THEN
    RAISE EXCEPTION 'Completed or archived fixture generated a reminder';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.task_reminder_events
    WHERE task_id = due_tomorrow_task_id
      AND reminder_type = 'task_due_soon'
      AND due_on = '2026-08-08'
  ) OR EXISTS (
    SELECT 1 FROM public.task_reminder_events
    WHERE task_id = due_tomorrow_task_id
      AND reminder_type = 'task_overdue'
  ) THEN
    RAISE EXCEPTION 'New York UTC/local-date boundary was not handled correctly';
  END IF;

  -- Repeat invocation must not create any additional fixture notifications.
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');
  SELECT count(*) INTO fixture_notification_count
  FROM public.notifications
  WHERE entity_id IN (
    due_today_task_id, due_tomorrow_task_id, overdue_task_id,
    changed_date_task_id, reopened_task_id
  );
  IF fixture_notification_count <> 5 THEN
    RAISE EXCEPTION 'Repeat invocation created duplicate fixture notifications';
  END IF;

  -- Read and archive do not alter lifecycle suppression.
  UPDATE public.notifications
  SET is_read = true
  WHERE entity_id = due_tomorrow_task_id;
  UPDATE public.notifications
  SET archived_at = clock_timestamp()
  WHERE entity_id = due_today_task_id;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');

  -- Permanent deletion must leave its ledger event and prevent regeneration.
  DELETE FROM public.notifications WHERE entity_id = due_today_task_id;
  IF NOT EXISTS (
    SELECT 1 FROM public.task_reminder_events
    WHERE task_id = due_today_task_id
      AND reminder_type = 'task_due_soon'
      AND due_on = '2026-08-07'
  ) THEN
    RAISE EXCEPTION 'Deleting a notification removed its ledger event';
  END IF;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');
  IF EXISTS (SELECT 1 FROM public.notifications WHERE entity_id = due_today_task_id) THEN
    RAISE EXCEPTION 'Deleted notification was regenerated';
  END IF;

  -- A changed calendar date receives a distinct reminder lifecycle.
  UPDATE public.tasks
  SET due_on = '2026-08-15', due_date = '2026-08-15T00:00:00Z'
  WHERE id = changed_date_task_id;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-14 12:00:00+00');
  SELECT count(*) INTO fixture_event_count
  FROM public.task_reminder_events
  WHERE task_id = changed_date_task_id
    AND reminder_type = 'task_due_soon';
  IF fixture_event_count <> 2 THEN
    RAISE EXCEPTION 'Changed due_on did not create a distinct lifecycle';
  END IF;

  -- Completion then reopen with unchanged due_on cannot recreate the old event.
  UPDATE public.tasks SET status = 'COMPLETED', completed = true WHERE id = reopened_task_id;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');
  UPDATE public.tasks SET status = 'TODO', completed = false WHERE id = reopened_task_id;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');
  SELECT count(*) INTO fixture_event_count
  FROM public.task_reminder_events
  WHERE task_id = reopened_task_id
    AND reminder_type = 'task_due_soon';
  IF fixture_event_count <> 1 THEN
    RAISE EXCEPTION 'Reopened task regenerated an existing lifecycle';
  END IF;

  -- DST is resolved from the IANA timezone, not a fixed UTC offset.
  PERFORM * FROM public.generate_task_due_notifications('2026-11-01 05:30:00+00');
  IF NOT EXISTS (
    SELECT 1 FROM public.task_reminder_events
    WHERE task_id = dst_task_id
      AND reminder_type = 'task_due_soon'
      AND due_on = '2026-11-02'
  ) THEN
    RAISE EXCEPTION 'DST boundary did not produce the expected due-soon event';
  END IF;

  -- A missing timezone suppresses reminder generation without guessing UTC.
  UPDATE public.user_settings SET timezone = NULL WHERE user_id = test_user_id;
  INSERT INTO public.tasks (
    project_id, user_id, title, description, completed, status, priority,
    due_on, due_date, is_pinned, is_archived, metadata, "order"
  ) VALUES
    (test_project_id, test_user_id, '__fixture_null_timezone__', '', false, 'TODO', 'MEDIUM', '2026-08-07', '2026-08-07T00:00:00Z', false, false, '{}'::jsonb, 9)
  RETURNING id INTO null_timezone_task_id;
  PERFORM * FROM public.generate_task_due_notifications('2026-08-08 02:30:00+00');
  IF EXISTS (
    SELECT 1 FROM public.task_reminder_events WHERE task_id = null_timezone_task_id
  ) THEN
    RAISE EXCEPTION 'NULL timezone generated a reminder';
  END IF;
END
$test$;

ROLLBACK;
