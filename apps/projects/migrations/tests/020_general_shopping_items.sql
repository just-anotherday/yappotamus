-- Controlled validation for migration 020. Run as one transaction only.
-- Replace both placeholders with distinct, controlled existing auth.users IDs.

BEGIN;

SELECT set_config('app.general_shopping_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.general_shopping_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);
DO $fixtures$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  shopping_project_a_id UUID;
  shopping_project_b_id UUID;
  store_id UUID;
BEGIN
  BEGIN
    test_user_id := current_setting('app.general_shopping_test_user_id')::uuid;
    other_user_id := current_setting('app.general_shopping_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled General Shopping test user UUID settings';
  END;
  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id) THEN
    RAISE EXCEPTION 'Two distinct controlled existing auth.users accounts are required';
  END IF;

  INSERT INTO public.projects (user_id, name, description, kind) VALUES
    (test_user_id, '__migration_020_general_a__', 'Rollback-only fixture', 'shopping'),
    (test_user_id, '__migration_020_general_b__', 'Rollback-only fixture', 'shopping');
  SELECT id INTO shopping_project_a_id FROM public.projects
    WHERE user_id = test_user_id AND name = '__migration_020_general_a__';
  SELECT id INTO shopping_project_b_id FROM public.projects
    WHERE user_id = test_user_id AND name = '__migration_020_general_b__';

  INSERT INTO public.shopping_stores (user_id, name, sort_order)
  VALUES (test_user_id, '__migration_020_store__', 0)
  RETURNING id INTO store_id;
  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order", shopping_store_id)
  VALUES (shopping_project_a_id, test_user_id, '__migration_020_checked_store_task__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 0, store_id);

  IF shopping_project_a_id IS NULL OR shopping_project_b_id IS NULL THEN
    RAISE EXCEPTION 'General cross-project fixtures were not created';
  END IF;
END
$fixtures$;

-- Run user-facing CRUD checks as the authenticated database role; SQL-editor
-- ownership does not substitute for this RLS simulation.
SET LOCAL ROLE authenticated;

DO $rls$
DECLARE
  test_user_id UUID := current_setting('app.general_shopping_test_user_id')::uuid;
  other_user_id UUID := current_setting('app.general_shopping_test_other_user_id')::uuid;
  general_item_id UUID;
  affected_rows INTEGER;
BEGIN
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  INSERT INTO public.general_shopping_items (user_id, title, quantity, unit, category)
  VALUES (test_user_id, '__migration_020_general_item__', '2', 'pcs', 'Household')
  RETURNING id INTO general_item_id;
  INSERT INTO public.general_shopping_items (user_id, title)
  VALUES (test_user_id, '__migration_020_general_item__');
  IF (SELECT count(*) FROM public.general_shopping_items WHERE title = '__migration_020_general_item__') <> 2 THEN
    RAISE EXCEPTION 'General duplicate titles were unexpectedly rejected';
  END IF;
  IF general_item_id IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.general_shopping_items WHERE id = general_item_id AND completed = false
  ) THEN RAISE EXCEPTION 'Owner General insert/select failed'; END IF;

  UPDATE public.general_shopping_items SET completed = true WHERE id = general_item_id;
  IF NOT EXISTS (SELECT 1 FROM public.general_shopping_items WHERE id = general_item_id AND completed) THEN
    RAISE EXCEPTION 'Owner General completion update failed';
  END IF;
  UPDATE public.general_shopping_items SET completed = false, title = '__migration_020_general_item_updated__' WHERE id = general_item_id;

  PERFORM set_config('request.jwt.claim.sub', other_user_id::text, true);
  IF EXISTS (SELECT 1 FROM public.general_shopping_items WHERE id = general_item_id) THEN
    RAISE EXCEPTION 'Other user could select owner General item';
  END IF;
  UPDATE public.general_shopping_items SET title = 'forbidden' WHERE id = general_item_id;
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> 0 THEN RAISE EXCEPTION 'Other user could update owner General item'; END IF;
  DELETE FROM public.general_shopping_items WHERE id = general_item_id;
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> 0 THEN RAISE EXCEPTION 'Other user could delete owner General item'; END IF;

  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  UPDATE public.general_shopping_items SET completed = true WHERE id = general_item_id;
  DELETE FROM public.general_shopping_items WHERE id = general_item_id;
  IF EXISTS (SELECT 1 FROM public.general_shopping_items WHERE id = general_item_id) THEN
    RAISE EXCEPTION 'Owner General delete failed';
  END IF;

  INSERT INTO public.general_shopping_items (user_id, title, completed)
  VALUES (test_user_id, '__migration_020_finish_safe_general__', true);
END
$rls$;

RESET ROLE;

DO $safety$
DECLARE
  test_user_id UUID := current_setting('app.general_shopping_test_user_id')::uuid;
  shopping_project_a_id UUID;
  store_id UUID;
  deleted_count INTEGER;
BEGIN
  SELECT id INTO shopping_project_a_id FROM public.projects
    WHERE user_id = test_user_id AND name = '__migration_020_general_a__';
  SELECT id INTO store_id FROM public.shopping_stores
    WHERE user_id = test_user_id AND name = '__migration_020_store__';
  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  deleted_count := public.finish_shopping_trip(shopping_project_a_id, store_id);
  IF deleted_count <> 1
     OR EXISTS (SELECT 1 FROM public.tasks WHERE title = '__migration_020_checked_store_task__')
     OR NOT EXISTS (SELECT 1 FROM public.general_shopping_items WHERE user_id = test_user_id AND title = '__migration_020_finish_safe_general__' AND completed) THEN
    RAISE EXCEPTION 'Finish Trip did not preserve the General safety boundary';
  END IF;

  DELETE FROM public.shopping_stores WHERE id = store_id;
  IF NOT EXISTS (SELECT 1 FROM public.general_shopping_items WHERE user_id = test_user_id AND title = '__migration_020_finish_safe_general__') THEN
    RAISE EXCEPTION 'Store deletion affected General item';
  END IF;
  DELETE FROM public.projects WHERE id = shopping_project_a_id;
  IF NOT EXISTS (SELECT 1 FROM public.general_shopping_items WHERE user_id = test_user_id AND title = '__migration_020_finish_safe_general__') THEN
    RAISE EXCEPTION 'Project deletion affected General item';
  END IF;
END
$safety$;

-- Owner deletion is verified structurally by the migration postflight FK
-- catalog assertion; do not delete a real controlled auth.users row here.

ROLLBACK;
