-- Controlled validation for migration 018. Run as one transaction only.
-- Replace both placeholders with distinct, controlled existing auth.users IDs.

BEGIN;

SELECT set_config('app.shopping_stores_test_user_id', 'REPLACE_WITH_CONTROLLED_TEST_USER_UUID', true);
SELECT set_config('app.shopping_stores_test_other_user_id', 'REPLACE_WITH_SECOND_CONTROLLED_TEST_USER_UUID', true);

DO $test$
DECLARE
  test_user_id UUID;
  other_user_id UUID;
  shopping_project_id UUID;
  test_task_id UUID;
  null_task_id UUID;
  first_store_id UUID;
  other_store_id UUID;
  retained_user_id UUID;
  task_store_id_attnum SMALLINT;
  task_user_id_attnum SMALLINT;
  store_id_attnum SMALLINT;
  store_user_id_attnum SMALLINT;
BEGIN
  BEGIN
    test_user_id := current_setting('app.shopping_stores_test_user_id')::uuid;
    other_user_id := current_setting('app.shopping_stores_test_other_user_id')::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'Set both controlled shopping-store test user UUID settings';
  END;

  IF test_user_id = other_user_id
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = test_user_id)
     OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = other_user_id) THEN
    RAISE EXCEPTION 'Two distinct controlled existing auth.users accounts are required';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE oid = 'public.shopping_stores'::regclass AND relrowsecurity) THEN
    RAISE EXCEPTION 'shopping_stores RLS is not enabled';
  ELSIF (
    SELECT count(*) FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'shopping_stores'
  ) <> 6 OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'shopping_store_id' AND udt_name = 'uuid' AND is_nullable = 'YES'
  ) THEN
    RAISE EXCEPTION 'shopping store schema shape is incorrect';
  ELSIF (
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'public.shopping_stores'::regclass
  ) <> 5 OR (
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'public.shopping_stores'::regclass
      AND (conname, contype) IN (
        ('shopping_stores_pkey', 'p'),
        ('shopping_stores_user_id_fkey', 'f'),
        ('shopping_stores_name_length_check', 'c'),
        ('shopping_stores_sort_order_check', 'c'),
        ('shopping_stores_id_user_id_key', 'u')
      )
  ) <> 5 THEN
    RAISE EXCEPTION 'shopping store constraints are missing';
  ELSIF (
    SELECT count(*) FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'shopping_stores'
      AND policyname IN ('shopping_stores_select_own', 'shopping_stores_insert_own', 'shopping_stores_update_own', 'shopping_stores_delete_own')
  ) <> 4 THEN
    RAISE EXCEPTION 'shopping_stores ownership policies are missing';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_index AS index_row
    JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
    WHERE index_class.relname = 'shopping_stores_user_normalized_name_key'
      AND index_class.relnamespace = 'public'::regnamespace
      AND index_row.indisunique AND index_row.indnkeyatts = 2
      AND index_row.indpred IS NULL
      AND pg_get_indexdef(index_row.indexrelid, 1, true) = 'user_id'
      AND pg_get_indexdef(index_row.indexrelid, 2, true) = 'lower(btrim(name))'
  )
     OR NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'tasks' AND indexname = 'idx_tasks_shopping_store_grouping') THEN
    RAISE EXCEPTION 'shopping store indexes are missing';
  ELSIF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'public.shopping_stores'::regclass AND tgname = 'update_shopping_stores_updated_at' AND NOT tgisinternal) THEN
    RAISE EXCEPTION 'shopping_stores updated_at trigger is missing';
  END IF;

  INSERT INTO public.projects (user_id, name, description, kind)
  VALUES (test_user_id, '__migration_018_shopping__', 'Rollback-only fixture', 'shopping')
  RETURNING id INTO shopping_project_id;

  INSERT INTO public.tasks (project_id, user_id, title, completed, status, priority, is_pinned, is_archived, metadata, "order")
  VALUES
    (shopping_project_id, test_user_id, '__migration_018_assigned__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 1),
    (shopping_project_id, test_user_id, '__migration_018_unassigned__', false, 'TODO', 'MEDIUM', false, false, '{}'::jsonb, 2);
  SELECT id INTO test_task_id FROM public.tasks WHERE project_id = shopping_project_id AND title = '__migration_018_assigned__';
  SELECT id INTO null_task_id FROM public.tasks WHERE project_id = shopping_project_id AND title = '__migration_018_unassigned__';

  INSERT INTO public.shopping_stores (user_id, name, sort_order)
  VALUES (test_user_id, 'Costco', 0)
  RETURNING id INTO first_store_id;

  BEGIN
    INSERT INTO public.shopping_stores (user_id, name) VALUES (test_user_id, '  costco  ');
    RAISE EXCEPTION 'Normalized duplicate store name was accepted';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;

  INSERT INTO public.shopping_stores (user_id, name, sort_order)
  VALUES (other_user_id, 'Costco', 0)
  RETURNING id INTO other_store_id;

  UPDATE public.shopping_stores SET name = 'Costco Wholesale' WHERE id = first_store_id;

  UPDATE public.tasks SET shopping_store_id = first_store_id WHERE id = test_task_id;
  IF (SELECT shopping_store_id FROM public.tasks WHERE id = test_task_id) IS DISTINCT FROM first_store_id THEN
    RAISE EXCEPTION 'Owner store assignment was not retained';
  END IF;

  BEGIN
    UPDATE public.tasks SET shopping_store_id = other_store_id WHERE id = test_task_id;
    RAISE EXCEPTION 'Cross-user store assignment was accepted';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;

  IF (SELECT shopping_store_id FROM public.tasks WHERE id = null_task_id) IS NOT NULL THEN
    RAISE EXCEPTION 'Existing NULL assignment is not valid';
  END IF;

  DELETE FROM public.shopping_stores WHERE id = first_store_id;
  SELECT user_id INTO retained_user_id FROM public.tasks WHERE id = test_task_id;
  IF retained_user_id IS DISTINCT FROM test_user_id
     OR (SELECT shopping_store_id FROM public.tasks WHERE id = test_task_id) IS NOT NULL THEN
    RAISE EXCEPTION 'Deleting a store did not preserve task ownership and null only shopping_store_id';
  END IF;

  SELECT attnum INTO task_store_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.tasks'::regclass AND attname = 'shopping_store_id' AND NOT attisdropped;
  SELECT attnum INTO task_user_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.tasks'::regclass AND attname = 'user_id' AND NOT attisdropped;
  SELECT attnum INTO store_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.shopping_stores'::regclass AND attname = 'id' AND NOT attisdropped;
  SELECT attnum INTO store_user_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.shopping_stores'::regclass AND attname = 'user_id' AND NOT attisdropped;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.tasks'::regclass
      AND conname = 'tasks_shopping_store_owner_fkey'
      AND contype = 'f'
      AND confrelid = 'public.shopping_stores'::regclass
      AND conkey = ARRAY[task_store_id_attnum, task_user_id_attnum]::SMALLINT[]
      AND confkey = ARRAY[store_id_attnum, store_user_id_attnum]::SMALLINT[]
      AND confdeltype = 'n'
      AND confdelsetcols = ARRAY[task_store_id_attnum]::SMALLINT[]
  ) THEN
    RAISE EXCEPTION 'Owner-safe targeted task store foreign key is missing';
  END IF;
END
$test$;

ROLLBACK;
