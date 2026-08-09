-- Migration 013 controlled validation, Part 2: worker claim and lease lifecycle.
-- Run as one transaction only. Replace both placeholders in the SQL Editor copy.

BEGIN;

SELECT set_config('app.reminder_email_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.reminder_email_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  board_project_id UUID;
  claim_task_id UUID;
  lease_task_id UUID;
  claim_reminder_id UUID;
  lease_reminder_id UUID;
  claim_delivery_id UUID;
  lease_delivery_id UUID;
  returned_delivery_id UUID;
  returned_reminder_id UUID;
  returned_user_id UUID;
  first_token UUID;
  replacement_token UUID;
  returned_attempt INTEGER;
  returned_subject TEXT;
  returned_body TEXT;
  now_instant TIMESTAMPTZ := clock_timestamp();
  local_date DATE;
  local_time TIME WITHOUT TIME ZONE;
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
  VALUES (test_user_id, '__migration_013_p2_board__', 'Rollback-only fixture', 'board')
  RETURNING id INTO board_project_id;
  INSERT INTO public.tasks (
    project_id, user_id, title, completed, status, priority,
    is_pinned, is_archived, metadata, "order"
  ) VALUES
    (board_project_id, test_user_id, '__migration_013_p2_claim__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (board_project_id, test_user_id, '__migration_013_p2_lease__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2);
  SELECT id INTO claim_task_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p2_claim__';
  SELECT id INTO lease_task_id FROM public.tasks WHERE project_id = board_project_id AND title = '__migration_013_p2_lease__';
  local_date := (now_instant AT TIME ZONE 'America/New_York')::date;
  local_time := (now_instant AT TIME ZONE 'America/New_York')::time;
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  claim_reminder_id := public.create_or_replace_custom_reminder(
    'task', claim_task_id, local_date, local_time, 'America/New_York', now_instant, false, true
  );
  lease_reminder_id := public.create_or_replace_custom_reminder(
    'task', lease_task_id, local_date, local_time, 'America/New_York', now_instant, false, true
  );
  PERFORM * FROM public.generate_custom_reminders(now_instant + interval '1 minute');
  SELECT id INTO claim_delivery_id FROM public.reminder_deliveries WHERE reminder_id = claim_reminder_id;
  SELECT id INTO lease_delivery_id FROM public.reminder_deliveries WHERE reminder_id = lease_reminder_id;
  UPDATE public.reminder_deliveries
  SET next_attempt_at = CASE reminder_id
    WHEN claim_reminder_id THEN now_instant + interval '2 minutes'
    WHEN lease_reminder_id THEN now_instant + interval '3 minutes'
    ELSE next_attempt_at
  END
  WHERE reminder_id IN (claim_reminder_id, lease_reminder_id);

  SELECT delivery_id, reminder_id, user_id, lock_token, attempt_count, subject, text_body
  INTO returned_delivery_id, returned_reminder_id, returned_user_id, first_token, returned_attempt, returned_subject, returned_body
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '2 minutes');
  IF returned_delivery_id <> claim_delivery_id
     OR returned_reminder_id <> claim_reminder_id
     OR returned_user_id <> test_user_id
     OR first_token IS NULL
     OR returned_attempt <> 1
     OR returned_subject <> 'Task reminder: __migration_013_p2_claim__'
     OR returned_body <> E'You asked to be reminded about this task.\n\n__migration_013_p2_claim__'
     OR NOT EXISTS (
       SELECT 1 FROM public.reminder_deliveries
       WHERE id = claim_delivery_id AND status = 'processing'
         AND locked_at = now_instant + interval '2 minutes'
         AND locked_until = now_instant + interval '7 minutes'
     ) THEN
    RAISE EXCEPTION 'Claim did not return or persist the expected five-minute lease';
  END IF;
  IF EXISTS (SELECT 1 FROM public.claim_reminder_email_deliveries(1, now_instant + interval '2 minutes')) THEN
    RAISE EXCEPTION 'A second worker claimed an active lease';
  END IF;
  IF public.complete_reminder_email_delivery(claim_delivery_id, gen_random_uuid(), 'wrong-token') THEN
    RAISE EXCEPTION 'Stale token completed a delivery';
  END IF;
  IF NOT public.complete_reminder_email_delivery(claim_delivery_id, first_token, 'provider-message-p2')
     OR NOT EXISTS (
       SELECT 1 FROM public.reminder_deliveries
       WHERE id = claim_delivery_id AND status = 'sent'
         AND sent_at IS NOT NULL AND provider_message_id = 'provider-message-p2'
     ) THEN
    RAISE EXCEPTION 'Correct token did not complete a delivery';
  END IF;

  SELECT delivery_id, lock_token
  INTO returned_delivery_id, first_token
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '3 minutes');
  IF returned_delivery_id <> lease_delivery_id THEN
    RAISE EXCEPTION 'Expected lease fixture was not claimed';
  END IF;
  SELECT delivery_id, lock_token, attempt_count
  INTO returned_delivery_id, replacement_token, returned_attempt
  FROM public.claim_reminder_email_deliveries(1, now_instant + interval '8 minutes');
  IF returned_delivery_id <> lease_delivery_id
     OR replacement_token = first_token
     OR returned_attempt <> 2
     OR public.complete_reminder_email_delivery(lease_delivery_id, first_token, 'stale') THEN
    RAISE EXCEPTION 'Expired lease was not reclaimed with a fresh token';
  END IF;
  IF NOT public.record_reminder_email_delivery_failure(
    lease_delivery_id, replacement_token, false, repeat('x', 1200)
  ) OR NOT EXISTS (
    SELECT 1 FROM public.reminder_deliveries
    WHERE id = lease_delivery_id AND status = 'failed'
      AND next_attempt_at IS NULL AND char_length(last_error) = 1000
  ) THEN
    RAISE EXCEPTION 'Terminal failure did not preserve bounded error state';
  END IF;
END
$test$;

ROLLBACK;
