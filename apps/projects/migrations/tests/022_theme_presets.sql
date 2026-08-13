-- Controlled validation for migration 022. Run as one transaction only.
-- Replace the placeholder with a controlled existing auth.users ID.

BEGIN;
SELECT set_config('app.theme_presets_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);

DO $preflight$
DECLARE test_user_id UUID;
BEGIN
  BEGIN
    test_user_id := current_setting('app.theme_presets_test_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set a controlled theme-presets test user UUID';
  END;
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'A controlled user with a user_settings row is required';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'theme' AND column_default = '''forest''::text'
  ) THEN
    RAISE EXCEPTION 'Migration 022 theme default is not forest';
  END IF;
END
$preflight$;

SET LOCAL ROLE authenticated;

DO $theme_presets$
DECLARE
  test_user_id UUID := current_setting('app.theme_presets_test_user_id')::uuid;
  original_theme TEXT;
BEGIN
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  SELECT theme INTO original_theme FROM public.user_settings WHERE user_id = test_user_id;

  UPDATE public.user_settings SET theme = 'forest' WHERE user_id = test_user_id;
  UPDATE public.user_settings SET theme = 'midnight' WHERE user_id = test_user_id;
  UPDATE public.user_settings SET theme = 'sunset' WHERE user_id = test_user_id;
  IF (SELECT theme FROM public.user_settings WHERE user_id = test_user_id) <> 'sunset' THEN
    RAISE EXCEPTION 'Named theme preferences were not persisted';
  END IF;

  UPDATE public.user_settings SET theme = original_theme WHERE user_id = test_user_id;
END
$theme_presets$;

RESET ROLE;
ROLLBACK;
