-- Controlled validation for migration 019. Run as one transaction only.
-- Replace both placeholders with distinct, controlled existing auth.users IDs.
-- This verifies RPC ownership logic under simulated JWT claims; it is not a
-- substitute for a browser-authenticated RLS integration test.

BEGIN;

SELECT set_config('app.shopping_trip_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.shopping_trip_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  shopping_project_a_id UUID;
  shopping_project_b_id UUID;
  other_shopping_project_id UUID;
  board_project_id UUID;
  recipe_project_id UUID;
  costco_id UUID;
  publix_id UUID;
  other_costco_id UUID;
  deleted_count INTEGER;
BEGIN
  BEGIN
    test_user_id := current_setting('app.shopping_trip_test_user_id')::uuid;
    other_user_id := current_setting('app.shopping_trip_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled shopping-trip test user UUID settings';
  END;

  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id) THEN
    RAISE EXCEPTION 'Two distinct controlled existing auth.users accounts are required';
  END IF;

  IF to_regprocedure('public.finish_shopping_trip(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'finish_shopping_trip(uuid,uuid) is missing';
  END IF;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_019_trip_a__', 'Rollback-only fixture', 'shopping')
  RETURNING id INTO shopping_project_a_id;
  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_019_trip_b__', 'Rollback-only fixture', 'shopping')
  RETURNING id INTO shopping_project_b_id;
  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_019_board__', 'Rollback-only fixture', 'board')
  RETURNING id INTO board_project_id;
  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_019_recipes__', 'Rollback-only fixture', 'recipes')
  RETURNING id INTO recipe_project_id;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (other_user_id, '__migration_019_other_trip__', 'Rollback-only fixture', 'shopping')
  RETURNING id INTO other_shopping_project_id;

  INSERT INTO public.shopping_stores (user_id, name, sort_order) VALUES
    (test_user_id, '__migration_019_costco__', 0),
    (test_user_id, '__migration_019_publix__', 1),
    (other_user_id, '__migration_019_costco__', 0);
  SELECT id INTO costco_id FROM public.shopping_stores WHERE user_id = test_user_id AND name = '__migration_019_costco__';
  SELECT id INTO publix_id FROM public.shopping_stores WHERE user_id = test_user_id AND name = '__migration_019_publix__';
  SELECT id INTO other_costco_id FROM public.shopping_stores WHERE user_id = other_user_id AND name = '__migration_019_costco__';

  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order", shopping_store_id) VALUES
    (shopping_project_a_id, test_user_id, '__migration_019_checked_costco_a__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 1, costco_id),
    (shopping_project_a_id, test_user_id, '__migration_019_checked_costco_b__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 2, costco_id),
    (shopping_project_a_id, test_user_id, '__migration_019_unchecked_costco__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 3, costco_id),
    (shopping_project_a_id, test_user_id, '__migration_019_checked_publix__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 4, publix_id),
    (shopping_project_a_id, test_user_id, '__migration_019_checked_unassigned__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 5, NULL),
    (shopping_project_b_id, test_user_id, '__migration_019_checked_other_project__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 1, costco_id),
    (shopping_project_a_id, test_user_id, '__migration_019_moved_to_publix__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 6, publix_id),
    (shopping_project_a_id, test_user_id, '__migration_019_unchecked_before_finish__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 7, costco_id),
    (other_shopping_project_id, other_user_id, '__migration_019_other_user_checked_costco__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 1, other_costco_id);

  PERFORM set_config('request.jwt.claim.sub', test_user_id::text, true);
  deleted_count := public.finish_shopping_trip(shopping_project_a_id, costco_id);
  IF deleted_count <> 2 THEN
    RAISE EXCEPTION 'Expected 2 deleted Costco tasks, got %', deleted_count;
  END IF;

  IF EXISTS (SELECT 1 FROM public.tasks WHERE title IN ('__migration_019_checked_costco_a__', '__migration_019_checked_costco_b__'))
     OR (
       SELECT count(*)
       FROM public.tasks
       WHERE title IN (
         '__migration_019_unchecked_costco__', '__migration_019_checked_publix__',
         '__migration_019_checked_unassigned__', '__migration_019_checked_other_project__',
         '__migration_019_moved_to_publix__', '__migration_019_unchecked_before_finish__',
         '__migration_019_other_user_checked_costco__'
       )
     ) <> 7 THEN
    RAISE EXCEPTION 'Finish-trip delete scope did not preserve current project/store/completion boundaries';
  END IF;

  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order", shopping_store_id) VALUES
    (shopping_project_a_id, test_user_id, '__migration_019_null_completed__', NULL, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 8, costco_id),
    (NULL, test_user_id, '__migration_019_null_project__', true, 'COMPLETED', 'MEDIUM', false, false, '{}'::jsonb, 9, costco_id);

  deleted_count := public.finish_shopping_trip(shopping_project_a_id, costco_id);
  IF deleted_count <> 0
     OR NOT EXISTS (SELECT 1 FROM public.tasks WHERE title = '__migration_019_null_completed__')
     OR NOT EXISTS (SELECT 1 FROM public.tasks WHERE title = '__migration_019_null_project__') THEN
    RAISE EXCEPTION 'NULL completed or NULL project task was incorrectly deleted';
  END IF;

  BEGIN
    PERFORM public.finish_shopping_trip(shopping_project_a_id, other_costco_id);
    RAISE EXCEPTION 'Mixed-owner project/store combination was accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    PERFORM public.finish_shopping_trip(board_project_id, costco_id);
    RAISE EXCEPTION 'Board project was accepted as a shopping trip';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    PERFORM public.finish_shopping_trip(recipe_project_id, costco_id);
    RAISE EXCEPTION 'Recipe project was accepted as a shopping trip';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    PERFORM public.finish_shopping_trip(NULL, costco_id);
    RAISE EXCEPTION 'NULL store/project target was accepted';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;

  PERFORM set_config('request.jwt.claim.sub', other_user_id::text, true);
  BEGIN
    PERFORM public.finish_shopping_trip(shopping_project_a_id, costco_id);
    RAISE EXCEPTION 'Cross-user project/store invocation was accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;

  PERFORM set_config('request.jwt.claim.sub', '', true);
  BEGIN
    PERFORM public.finish_shopping_trip(shopping_project_a_id, costco_id);
    RAISE EXCEPTION 'Unauthenticated invocation was accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END
$test$;

ROLLBACK;
