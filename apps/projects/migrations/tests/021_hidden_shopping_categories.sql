-- Controlled validation for migration 021. Run as one transaction only.
-- Replace both placeholders with distinct, controlled existing auth.users IDs.

BEGIN;

SELECT set_config('app.hidden_categories_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.hidden_categories_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $preflight$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
BEGIN
  BEGIN
    test_user_id := current_setting('app.hidden_categories_test_user_id')::uuid;
    other_user_id := current_setting('app.hidden_categories_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled hidden-category test user UUID settings';
  END;
  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM public.user_settings WHERE user_id = other_user_id) THEN
    RAISE EXCEPTION 'Two distinct controlled users with settings rows are required';
  END IF;
END
$preflight$;

SET LOCAL ROLE authenticated;

DO $rls$
DECLARE
  test_user_id UUID := current_setting('app.hidden_categories_test_user_id')::uuid;
  other_user_id UUID := current_setting('app.hidden_categories_test_other_user_id')::uuid;
  original_theme TEXT;
  original_workspace TEXT;
  affected_rows INTEGER;
BEGIN
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  SELECT theme, last_workspace INTO original_theme, original_workspace
  FROM public.user_settings WHERE user_id = test_user_id;

  UPDATE public.user_settings SET hidden_shopping_categories = NULL WHERE user_id = test_user_id;
  IF (SELECT hidden_shopping_categories IS NOT NULL FROM public.user_settings WHERE user_id = test_user_id) THEN
    RAISE EXCEPTION 'NULL hidden category preference was not accepted';
  END IF;
  UPDATE public.user_settings SET hidden_shopping_categories = ARRAY[]::TEXT[] WHERE user_id = test_user_id;
  IF (SELECT hidden_shopping_categories FROM public.user_settings WHERE user_id = test_user_id) <> ARRAY[]::TEXT[] THEN
    RAISE EXCEPTION 'Empty hidden category preference was not accepted';
  END IF;
  UPDATE public.user_settings SET hidden_shopping_categories = ARRAY['Frozen', 'Pantry']::TEXT[] WHERE user_id = test_user_id;
  IF (SELECT hidden_shopping_categories FROM public.user_settings WHERE user_id = test_user_id) <> ARRAY['Frozen', 'Pantry']::TEXT[] THEN
    RAISE EXCEPTION 'String-array hidden category preference was not accepted';
  ELSIF (SELECT theme FROM public.user_settings WHERE user_id = test_user_id) <> original_theme
     OR (SELECT last_workspace FROM public.user_settings WHERE user_id = test_user_id) <> original_workspace THEN
    RAISE EXCEPTION 'Partial preference update overwrote unrelated settings';
  END IF;

  PERFORM set_config('request.jwt.claim.sub', other_user_id::text, true);
  UPDATE public.user_settings SET hidden_shopping_categories = ARRAY['Other']::TEXT[] WHERE user_id = test_user_id;
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> 0 THEN
    RAISE EXCEPTION 'Other user could update owner hidden category preference';
  END IF;
END
$rls$;

RESET ROLE;
ROLLBACK;
