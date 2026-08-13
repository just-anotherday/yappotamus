-- Controlled validation for migration 024. Run as one transaction only.
-- Replace the placeholder with a controlled existing auth.users ID.

BEGIN;
SELECT set_config('app.light_dark_theme_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);

DO $preflight$
DECLARE test_user_id UUID; constraint_definition TEXT;
BEGIN
  BEGIN
    test_user_id := current_setting('app.light_dark_theme_test_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set a controlled Light/Dark theme test user UUID';
  END;
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'A controlled user with a user_settings row is required';
  END IF;
  SELECT pg_get_constraintdef(oid) INTO constraint_definition
  FROM pg_constraint WHERE conrelid = 'public.user_settings'::regclass AND conname = 'user_settings_theme_check';
  IF constraint_definition IS NULL
     OR constraint_definition NOT LIKE '%light%'
     OR constraint_definition NOT LIKE '%dark%'
     OR constraint_definition NOT LIKE '%forest%'
     OR constraint_definition NOT LIKE '%midnight%'
     OR constraint_definition NOT LIKE '%sunset%' THEN
    RAISE EXCEPTION 'Migration 024 theme constraint does not allow all five presets';
  END IF;
END
$preflight$;

SET LOCAL ROLE authenticated;

DO $light_dark$
DECLARE test_user_id UUID := current_setting('app.light_dark_theme_test_user_id')::uuid;
BEGIN
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  UPDATE public.user_settings SET theme = 'light' WHERE user_id = test_user_id;
  UPDATE public.user_settings SET theme = 'dark' WHERE user_id = test_user_id;
  IF (SELECT theme FROM public.user_settings WHERE user_id = test_user_id) <> 'dark' THEN
    RAISE EXCEPTION 'Traditional Dark preference was not persisted';
  END IF;
  BEGIN
    UPDATE public.user_settings SET theme = 'unsupported-theme' WHERE user_id = test_user_id;
    RAISE EXCEPTION 'Unsupported theme unexpectedly passed the constraint';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
END
$light_dark$;

RESET ROLE;
ROLLBACK;
