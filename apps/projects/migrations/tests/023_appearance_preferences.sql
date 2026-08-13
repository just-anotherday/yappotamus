-- Controlled validation for migration 023. Run as one transaction only.
-- Replace both placeholders with distinct, controlled existing auth.users IDs.

BEGIN;
SELECT set_config('app.appearance_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.appearance_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $preflight$
DECLARE test_user_id UUID; other_user_id UUID;
BEGIN
  BEGIN
    test_user_id := current_setting('app.appearance_test_user_id')::uuid;
    other_user_id := current_setting('app.appearance_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled appearance test user UUIDs';
  END;
  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = other_user_id) THEN
    RAISE EXCEPTION 'Two controlled users with user_settings rows are required';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'appearance' AND udt_name = 'jsonb' AND is_nullable = 'YES'
  ) THEN
    RAISE EXCEPTION 'Migration 023 appearance column is missing or incompatible';
  ELSIF NOT has_column_privilege('authenticated', 'public.user_settings', 'appearance', 'UPDATE') THEN
    RAISE EXCEPTION 'Authenticated users lack appearance update permission';
  END IF;
END
$preflight$;

SET LOCAL ROLE authenticated;

DO $appearance$
DECLARE
  test_user_id UUID := current_setting('app.appearance_test_user_id')::uuid;
  other_user_id UUID := current_setting('app.appearance_test_other_user_id')::uuid;
  affected_rows INTEGER;
BEGIN
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  UPDATE public.user_settings
  SET appearance = '{"version":1,"preset":"forest","colors":{"cardBackground":"#4a2c63"}}'::jsonb
  WHERE user_id = test_user_id;
  IF (SELECT appearance->>'preset' FROM public.user_settings WHERE user_id = test_user_id) <> 'forest' THEN
    RAISE EXCEPTION 'Appearance JSON object was not persisted';
  END IF;

  BEGIN
    UPDATE public.user_settings SET appearance = '[]'::jsonb WHERE user_id = test_user_id;
    RAISE EXCEPTION 'Appearance array unexpectedly passed the object constraint';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  PERFORM set_config('request.jwt.claim.sub', other_user_id::text, true);
  UPDATE public.user_settings SET appearance = '{"preset":"sunset"}'::jsonb WHERE user_id = test_user_id;
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> 0 THEN
    RAISE EXCEPTION 'Other user could update appearance preferences';
  END IF;
END
$appearance$;

RESET ROLE;
ROLLBACK;
