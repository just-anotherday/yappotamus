-- Migration 006: Create dedicated Recipe Books tables and retain a guarded
-- compatibility backfill from generalized projects/tasks recipe records.
--
-- Prerequisites: migrations 004 and 005 must have completed successfully.
-- Preservation: generalized projects/tasks rows remain unchanged.
-- Scope: projects.kind = 'recipes' only; Task Boards and Shopping Lists are
-- excluded.
--
-- Deterministic child IDs:
-- Ingredient and step source arrays do not contain UUIDs. Backfill IDs are
-- deterministic UUID-formatted identifiers derived from recipe ID + child
-- type + zero-based array position. The built-in md5() function supplies
-- stable 128-bit input, and no extension is required. These identifiers are
-- not standards-compliant UUIDv5 values.

BEGIN;

DO $migration_006_preflight$
DECLARE
  required_task_columns TEXT[] := ARRAY[
    'id',
    'project_id',
    'user_id',
    'title',
    'description',
    'is_pinned',
    'is_archived',
    'created_at',
    'updated_at',
    'metadata'
  ];
  invalid_count INTEGER;
  numeric_key TEXT;
BEGIN
  IF to_regclass('public.projects') IS NULL
     OR to_regclass('public.tasks') IS NULL THEN
    RAISE EXCEPTION
      'Migration 006 requires public.projects and public.tasks';
  END IF;

  IF to_regclass('public.shopping_lists') IS NULL
     OR to_regclass('public.shopping_items') IS NULL THEN
    RAISE EXCEPTION
      'Migration 006 requires migration 005 Shopping List tables';
  END IF;

  WITH expected (
    table_name,
    column_name,
    udt_name,
    is_nullable,
    normalized_default,
    numeric_precision,
    numeric_scale
  ) AS (
    VALUES
      ('shopping_lists', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'description', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'shopping_date', 'date', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'store_name', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('shopping_lists', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),

      ('shopping_items', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'shopping_list_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'quantity_text', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'unit', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'category', 'text', 'NO', '''Other''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'notes', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'estimated_price', 'numeric', 'YES', '', 12, 2),
      ('shopping_items', 'actual_price', 'numeric', 'YES', '', 12, 2),
      ('shopping_items', 'is_purchased', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'priority', 'text', 'NO', '''MEDIUM''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'position', 'int4', 'NO', '0', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('shopping_items', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER)
  )
  SELECT count(*)
  INTO invalid_count
  FROM expected
  LEFT JOIN information_schema.columns AS actual
    ON actual.table_schema = 'public'
   AND actual.table_name = expected.table_name
   AND actual.column_name = expected.column_name
  WHERE actual.column_name IS NULL
     OR actual.udt_name <> expected.udt_name
     OR actual.is_nullable <> expected.is_nullable
     OR COALESCE(
          regexp_replace(actual.column_default, '\s', '', 'g'),
          ''
        ) <> expected.normalized_default
     OR (
       expected.numeric_precision IS NOT NULL
       AND actual.numeric_precision <> expected.numeric_precision
     )
     OR (
       expected.numeric_scale IS NOT NULL
       AND actual.numeric_scale <> expected.numeric_scale
     );

  IF invalid_count <> 0 OR (
    SELECT count(*)
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN ('shopping_lists', 'shopping_items')
  ) <> 25 THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 has % incompatible column definitions',
      invalid_count;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_lists'::regclass
      AND conname = 'shopping_lists_pkey'
      AND contype = 'p'
      AND pg_get_constraintdef(oid, true) = 'PRIMARY KEY (id)'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_lists'::regclass
      AND conname = 'shopping_lists_id_user_id_key'
      AND contype = 'u'
      AND pg_get_constraintdef(oid, true) = 'UNIQUE (id, user_id)'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_lists'::regclass
      AND conname = 'shopping_lists_user_id_fkey'
      AND contype = 'f'
      AND confrelid = 'auth.users'::regclass
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE'
  ) THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 shopping_lists keys are missing or incompatible';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_pkey'
      AND contype = 'p'
      AND pg_get_constraintdef(oid, true) = 'PRIMARY KEY (id)'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_user_id_fkey'
      AND contype = 'f'
      AND confrelid = 'auth.users'::regclass
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_list_owner_fkey'
      AND contype = 'f'
      AND confrelid = 'public.shopping_lists'::regclass
      AND confdeltype = 'c'
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (shopping_list_id, user_id) REFERENCES shopping_lists(id, user_id) ON DELETE CASCADE'
  ) THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 shopping_items keys are missing or incompatible';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_priority_check'
      AND contype = 'c'
      AND regexp_replace(
            lower(pg_get_constraintdef(oid, true)),
            '\s',
            '',
            'g'
          ) IN (
            'check(priority=any(array[''low''::text,''medium''::text,''high''::text]))',
            'check((priority=any(array[''low''::text,''medium''::text,''high''::text])))'
          )
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_position_check'
      AND contype = 'c'
      AND regexp_replace(
            lower(pg_get_constraintdef(oid, true)),
            '\s',
            '',
            'g'
          ) IN ('check(("position">=0))', 'check("position">=0)')
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_estimated_price_check'
      AND contype = 'c'
      AND regexp_replace(
            lower(pg_get_constraintdef(oid, true)),
            '\s',
            '',
            'g'
          ) LIKE '%estimated_price%>=0%'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname = 'shopping_items_actual_price_check'
      AND contype = 'c'
      AND regexp_replace(
            lower(pg_get_constraintdef(oid, true)),
            '\s',
            '',
            'g'
          ) LIKE '%actual_price%>=0%'
  ) THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 shopping_items checks are missing or incompatible';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_lists'::regclass
  ) <> 5 OR (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
  ) <> 12 THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 constraint counts are incompatible';
  END IF;

  WITH expected(table_name, index_name, normalized_definition) AS (
    VALUES
      ('shopping_lists', 'shopping_lists_pkey', 'createuniqueindexshopping_lists_pkeyonpublic.shopping_listsusingbtree(id)'),
      ('shopping_lists', 'shopping_lists_id_user_id_key', 'createuniqueindexshopping_lists_id_user_id_keyonpublic.shopping_listsusingbtree(id,user_id)'),
      ('shopping_lists', 'idx_shopping_lists_active', 'createindexidx_shopping_lists_activeonpublic.shopping_listsusingbtree(user_id,created_atdesc)where(is_archived=false)'),
      ('shopping_lists', 'idx_shopping_lists_date', 'createindexidx_shopping_lists_dateonpublic.shopping_listsusingbtree(user_id,shopping_date)where(shopping_dateisnotnull)'),
      ('shopping_items', 'shopping_items_pkey', 'createuniqueindexshopping_items_pkeyonpublic.shopping_itemsusingbtree(id)'),
      ('shopping_items', 'idx_shopping_items_archive_state', 'createindexidx_shopping_items_archive_stateonpublic.shopping_itemsusingbtree(user_id,is_archived)'),
      ('shopping_items', 'idx_shopping_items_category', 'createindexidx_shopping_items_categoryonpublic.shopping_itemsusingbtree(shopping_list_id,category)'),
      ('shopping_items', 'idx_shopping_items_ordering', 'createindexidx_shopping_items_orderingonpublic.shopping_itemsusingbtree(shopping_list_id,is_archived,is_purchased,"position",created_at)'),
      ('shopping_items', 'idx_shopping_items_ownership', 'createindexidx_shopping_items_ownershiponpublic.shopping_itemsusingbtree(user_id,shopping_list_id)'),
      ('shopping_items', 'idx_shopping_items_purchase_state', 'createindexidx_shopping_items_purchase_stateonpublic.shopping_itemsusingbtree(user_id,is_purchased)where(is_archived=false)')
  )
  SELECT count(*)
  INTO invalid_count
  FROM expected
  LEFT JOIN pg_indexes AS actual
    ON actual.schemaname = 'public'
   AND actual.tablename = expected.table_name
   AND actual.indexname = expected.index_name
   AND regexp_replace(lower(actual.indexdef), '\s', '', 'g')
         = expected.normalized_definition
  WHERE actual.indexname IS NULL;

  IF invalid_count <> 0 OR (
    SELECT count(*)
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename IN ('shopping_lists', 'shopping_items')
  ) <> 10 THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 has % missing or incompatible indexes',
      invalid_count;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_lists'::regclass
      AND tgname = 'update_shopping_lists_updated_at'
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true)
            LIKE 'CREATE TRIGGER update_shopping_lists_updated_at BEFORE UPDATE ON shopping_lists%EXECUTE FUNCTION update_updated_at_column()'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_items'::regclass
      AND tgname = 'update_shopping_items_updated_at'
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true)
            LIKE 'CREATE TRIGGER update_shopping_items_updated_at BEFORE UPDATE ON shopping_items%EXECUTE FUNCTION update_updated_at_column()'
  ) THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 updated_at triggers are missing or incompatible';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_class
    WHERE oid IN (
      'public.shopping_lists'::regclass,
      'public.shopping_items'::regclass
    )
      AND relrowsecurity
  ) <> 2 THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 RLS is not enabled on both tables';
  END IF;

  WITH expected(table_name, policy_name, command) AS (
    VALUES
      ('shopping_lists', 'shopping_lists_select_own', 'SELECT'),
      ('shopping_lists', 'shopping_lists_insert_own', 'INSERT'),
      ('shopping_lists', 'shopping_lists_update_own', 'UPDATE'),
      ('shopping_lists', 'shopping_lists_delete_own', 'DELETE'),
      ('shopping_items', 'shopping_items_select_own', 'SELECT'),
      ('shopping_items', 'shopping_items_insert_own', 'INSERT'),
      ('shopping_items', 'shopping_items_update_own', 'UPDATE'),
      ('shopping_items', 'shopping_items_delete_own', 'DELETE')
  )
  SELECT count(*)
  INTO invalid_count
  FROM expected
  LEFT JOIN pg_policies AS actual
    ON actual.schemaname = 'public'
   AND actual.tablename = expected.table_name
   AND actual.policyname = expected.policy_name
   AND actual.cmd = expected.command
   AND actual.roles = ARRAY['authenticated']::name[]
  WHERE actual.policyname IS NULL
     OR (
       expected.command IN ('SELECT', 'DELETE')
       AND (
         actual.qual IS NULL
         OR actual.with_check IS NOT NULL
         OR position('auth.uid()' IN actual.qual) = 0
         OR (
           expected.table_name = 'shopping_items'
           AND position('shopping_lists' IN actual.qual) = 0
         )
       )
     )
     OR (
       expected.command = 'INSERT'
       AND (
         actual.qual IS NOT NULL
         OR actual.with_check IS NULL
         OR position('auth.uid()' IN actual.with_check) = 0
         OR (
           expected.table_name = 'shopping_items'
           AND position('shopping_lists' IN actual.with_check) = 0
         )
       )
     )
     OR (
       expected.command = 'UPDATE'
       AND (
         actual.qual IS NULL
         OR actual.with_check IS NULL
         OR position('auth.uid()' IN actual.qual) = 0
         OR position('auth.uid()' IN actual.with_check) = 0
         OR (
           expected.table_name = 'shopping_items'
           AND (
             position('shopping_lists' IN actual.qual) = 0
             OR position('shopping_lists' IN actual.with_check) = 0
           )
         )
       )
     );

  IF invalid_count <> 0 OR (
    SELECT count(*)
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('shopping_lists', 'shopping_items')
  ) <> 8 THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: migration 005 has % missing or incompatible policies',
      invalid_count;
  END IF;

  IF has_table_privilege('anon', 'public.shopping_lists', 'SELECT')
     OR has_table_privilege('anon', 'public.shopping_lists', 'INSERT')
     OR has_table_privilege('anon', 'public.shopping_lists', 'UPDATE')
     OR has_table_privilege('anon', 'public.shopping_lists', 'DELETE')
     OR has_table_privilege('anon', 'public.shopping_lists', 'TRUNCATE')
     OR has_table_privilege('anon', 'public.shopping_lists', 'TRIGGER')
     OR has_table_privilege('anon', 'public.shopping_lists', 'REFERENCES')
     OR has_table_privilege('anon', 'public.shopping_items', 'SELECT')
     OR has_table_privilege('anon', 'public.shopping_items', 'INSERT')
     OR has_table_privilege('anon', 'public.shopping_items', 'UPDATE')
     OR has_table_privilege('anon', 'public.shopping_items', 'DELETE')
     OR has_table_privilege('anon', 'public.shopping_items', 'TRUNCATE')
     OR has_table_privilege('anon', 'public.shopping_items', 'TRIGGER')
     OR has_table_privilege('anon', 'public.shopping_items', 'REFERENCES') THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: anon has migration 005 table privileges';
  END IF;

  IF NOT (
    has_table_privilege('authenticated', 'public.shopping_lists', 'SELECT')
    AND has_table_privilege('authenticated', 'public.shopping_lists', 'INSERT')
    AND has_table_privilege('authenticated', 'public.shopping_lists', 'UPDATE')
    AND has_table_privilege('authenticated', 'public.shopping_lists', 'DELETE')
    AND has_table_privilege('authenticated', 'public.shopping_items', 'SELECT')
    AND has_table_privilege('authenticated', 'public.shopping_items', 'INSERT')
    AND has_table_privilege('authenticated', 'public.shopping_items', 'UPDATE')
    AND has_table_privilege('authenticated', 'public.shopping_items', 'DELETE')
  ) OR has_table_privilege('authenticated', 'public.shopping_lists', 'TRUNCATE')
     OR has_table_privilege('authenticated', 'public.shopping_lists', 'TRIGGER')
     OR has_table_privilege('authenticated', 'public.shopping_lists', 'REFERENCES')
     OR has_table_privilege('authenticated', 'public.shopping_items', 'TRUNCATE')
     OR has_table_privilege('authenticated', 'public.shopping_items', 'TRIGGER')
     OR has_table_privilege('authenticated', 'public.shopping_items', 'REFERENCES') THEN
    RAISE EXCEPTION
      'Migration 006 prerequisite failed: authenticated migration 005 grants are missing or excessive';
  END IF;

  IF to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'Migration 006 requires auth.users';
  END IF;

  IF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
    RAISE EXCEPTION
      'Migration 006 requires public.update_updated_at_column()';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'projects'
      AND column_name = 'kind'
      AND data_type = 'text'
      AND is_nullable = 'NO'
      AND regexp_replace(column_default, '\s', '', 'g') = '''board''::text'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.projects'::regclass
      AND conname = 'projects_kind_check'
      AND contype = 'c'
      AND lower(pg_get_constraintdef(oid, true)) LIKE '%board%'
      AND lower(pg_get_constraintdef(oid, true)) LIKE '%shopping%'
      AND lower(pg_get_constraintdef(oid, true)) LIKE '%recipes%'
  ) OR to_regclass('public.idx_projects_user_kind') IS NULL THEN
    RAISE EXCEPTION
      'Migration 006 requires the complete migration 004 projects.kind definition';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'metadata'
      AND data_type = 'jsonb'
      AND is_nullable = 'NO'
      AND regexp_replace(column_default, '\s', '', 'g') = '''{}''::jsonb'
  ) THEN
    RAISE EXCEPTION
      'Migration 006 requires migration 004 tasks.metadata';
  END IF;

  IF EXISTS (
    SELECT required.column_name
    FROM unnest(required_task_columns) AS required(column_name)
    LEFT JOIN information_schema.columns AS actual
      ON actual.table_schema = 'public'
     AND actual.table_name = 'tasks'
     AND actual.column_name = required.column_name
    WHERE actual.column_name IS NULL
  ) THEN
    RAISE EXCEPTION
      'Migration 006 is missing one or more required public.tasks source columns';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    LEFT JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: orphaned public.tasks rows must be resolved first';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND task_row.user_id <> project_row.user_id
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: recipe task/book ownership mismatch';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects
    WHERE kind = 'recipes'
      AND (
        char_length(btrim(name)) NOT BETWEEN 1 AND 200
        OR char_length(COALESCE(description, '')) > 10000
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a recipe book violates target text constraints';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND (
        char_length(btrim(task_row.title)) NOT BETWEEN 1 AND 300
        OR char_length(COALESCE(task_row.description, '')) > 20000
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a recipe violates target text constraints';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND jsonb_typeof(task_row.metadata) = 'object'
      AND (
        (
          task_row.metadata ? 'ingredients'
          AND task_row.metadata -> 'ingredients' <> 'null'::jsonb
          AND jsonb_typeof(task_row.metadata -> 'ingredients') <> 'array'
        )
        OR (
          task_row.metadata ? 'steps'
          AND task_row.metadata -> 'steps' <> 'null'::jsonb
          AND jsonb_typeof(task_row.metadata -> 'steps') <> 'array'
        )
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: ingredients or steps metadata is not an array';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    CROSS JOIN LATERAL jsonb_array_elements(
      CASE
        WHEN jsonb_typeof(task_row.metadata) = 'object'
         AND jsonb_typeof(task_row.metadata -> 'ingredients') = 'array'
          THEN task_row.metadata -> 'ingredients'
        ELSE '[]'::jsonb
      END
    ) AS ingredient(value)
    WHERE project_row.kind = 'recipes'
      AND (
        jsonb_typeof(ingredient.value) <> 'string'
        OR char_length(btrim(ingredient.value #>> '{}')) NOT BETWEEN 1 AND 300
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: an ingredient is not a valid nonempty string';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    CROSS JOIN LATERAL jsonb_array_elements(
      CASE
        WHEN jsonb_typeof(task_row.metadata) = 'object'
         AND jsonb_typeof(task_row.metadata -> 'steps') = 'array'
          THEN task_row.metadata -> 'steps'
        ELSE '[]'::jsonb
      END
    ) AS step(value)
    WHERE project_row.kind = 'recipes'
      AND (
        jsonb_typeof(step.value) <> 'string'
        OR char_length(btrim(step.value #>> '{}')) NOT BETWEEN 1 AND 20000
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a recipe step is not a valid nonempty string';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND jsonb_typeof(task_row.metadata) <> 'object'
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: recipe metadata must be a JSON object';
  END IF;

  FOREACH numeric_key IN ARRAY ARRAY[
    'prep_minutes',
    'cook_minutes',
    'servings'
  ]
  LOOP
    SELECT count(*)
    INTO invalid_count
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND task_row.metadata -> numeric_key IS NOT NULL
      AND task_row.metadata -> numeric_key <> 'null'::jsonb
      AND jsonb_typeof(task_row.metadata -> numeric_key)
            NOT IN ('number', 'string');

    IF invalid_count <> 0 THEN
      RAISE EXCEPTION
        'Recipe backfill aborted: metadata key % has % invalid rows in reason category unsupported_json_type',
        numeric_key,
        invalid_count;
    END IF;

    SELECT count(*)
    INTO invalid_count
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
      AND task_row.metadata -> numeric_key IS NOT NULL
      AND task_row.metadata -> numeric_key <> 'null'::jsonb
      AND jsonb_typeof(task_row.metadata -> numeric_key)
            IN ('number', 'string')
      AND task_row.metadata ->> numeric_key ~ '^-';

    IF invalid_count <> 0 THEN
      RAISE EXCEPTION
        'Recipe backfill aborted: metadata key % has % invalid rows in reason category negative_value',
        numeric_key,
        invalid_count;
    END IF;

    IF numeric_key IN ('prep_minutes', 'cook_minutes') THEN
      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata -> numeric_key IS NOT NULL
        AND task_row.metadata -> numeric_key <> 'null'::jsonb
        AND jsonb_typeof(task_row.metadata -> numeric_key)
              IN ('number', 'string')
        AND task_row.metadata ->> numeric_key
              ~ '^[0-9]+[.][0-9]*[1-9][0-9]*$';

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key % has % invalid rows in reason category fractional_integer',
          numeric_key,
          invalid_count;
      END IF;

      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata -> numeric_key IS NOT NULL
        AND task_row.metadata -> numeric_key <> 'null'::jsonb
        AND jsonb_typeof(task_row.metadata -> numeric_key)
              IN ('number', 'string')
        AND task_row.metadata ->> numeric_key
              !~ '^[0-9]+([.][0]+)?$';

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key % has % invalid rows in reason category unsupported_numeric_format',
          numeric_key,
          invalid_count;
      END IF;

      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata -> numeric_key IS NOT NULL
        AND task_row.metadata -> numeric_key <> 'null'::jsonb
        AND task_row.metadata ->> numeric_key ~ '^[0-9]+([.][0]+)?$'
        AND (
          char_length(
            COALESCE(
              NULLIF(
                ltrim(
                  split_part(task_row.metadata ->> numeric_key, '.', 1),
                  '0'
                ),
                ''
              ),
              '0'
            )
          ) > 10
          OR (
            char_length(
              COALESCE(
                NULLIF(
                  ltrim(
                    split_part(task_row.metadata ->> numeric_key, '.', 1),
                    '0'
                  ),
                  ''
                ),
                '0'
              )
            ) = 10
            AND COALESCE(
                  NULLIF(
                    ltrim(
                      split_part(task_row.metadata ->> numeric_key, '.', 1),
                      '0'
                    ),
                    ''
                  ),
                  '0'
                ) > '2147483647'
          )
        );

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key % has % invalid rows in reason category exceeds_integer_range',
          numeric_key,
          invalid_count;
      END IF;
    ELSE
      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata -> numeric_key IS NOT NULL
        AND task_row.metadata -> numeric_key <> 'null'::jsonb
        AND jsonb_typeof(task_row.metadata -> numeric_key)
              IN ('number', 'string')
        AND task_row.metadata ->> numeric_key
              !~ '^[0-9]+([.][0-9]+)?$';

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key servings has % invalid rows in reason category unsupported_numeric_format',
          invalid_count;
      END IF;

      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata ->> numeric_key
              ~ '^[0-9]+[.][0-9]{3,}$';

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key servings has % invalid rows in reason category unsupported_rounding',
          invalid_count;
      END IF;

      SELECT count(*)
      INTO invalid_count
      FROM public.tasks AS task_row
      JOIN public.projects AS project_row
        ON project_row.id = task_row.project_id
      WHERE project_row.kind = 'recipes'
        AND task_row.metadata ->> numeric_key
              ~ '^[0-9]+([.][0-9]{1,2})?$'
        AND char_length(
              COALESCE(
                NULLIF(
                  ltrim(
                    split_part(task_row.metadata ->> numeric_key, '.', 1),
                    '0'
                  ),
                  ''
                ),
                '0'
              )
            ) > 6;

      IF invalid_count <> 0 THEN
        RAISE EXCEPTION
          'Recipe backfill aborted: metadata key servings has % invalid rows in reason category exceeds_numeric_8_2_range',
          invalid_count;
      END IF;
    END IF;
  END LOOP;
  IF EXISTS (
    WITH generated_child_ids AS (
      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata -> 'ingredients') = 'array'
            THEN source_recipe.metadata -> 'ingredients'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS ingredient(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':ingredient:' ||
          (ingredient.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'

      UNION ALL

      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata -> 'steps') = 'array'
            THEN source_recipe.metadata -> 'steps'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS step(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':step:' ||
          (step.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM generated_child_ids
    GROUP BY id
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: deterministic child IDs collide within the source set';
  END IF;
END
$migration_006_preflight$;

DO $migration_006_tables$
BEGIN
  IF to_regclass('public.recipe_books') IS NULL THEN
    CREATE TABLE public.recipe_books (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      cover_label TEXT,
      is_archived BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT recipe_books_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT recipe_books_id_user_id_key
        UNIQUE (id, user_id),
      CONSTRAINT recipe_books_name_length_check
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
      CONSTRAINT recipe_books_description_length_check
        CHECK (char_length(description) <= 10000),
      CONSTRAINT recipe_books_cover_label_length_check
        CHECK (cover_label IS NULL OR char_length(cover_label) <= 200)
    );
  END IF;

  IF to_regclass('public.recipes') IS NULL THEN
    CREATE TABLE public.recipes (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      recipe_book_id UUID NOT NULL,
      user_id UUID NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL DEFAULT '',
      cuisine TEXT NOT NULL DEFAULT '',
      servings NUMERIC(8, 2),
      prep_minutes INTEGER,
      cook_minutes INTEGER,
      difficulty TEXT,
      notes TEXT NOT NULL DEFAULT '',
      source TEXT,
      is_favorite BOOLEAN NOT NULL DEFAULT false,
      is_archived BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT recipes_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT recipes_book_owner_fkey
        FOREIGN KEY (recipe_book_id, user_id)
        REFERENCES public.recipe_books (id, user_id)
        ON DELETE CASCADE,
      CONSTRAINT recipes_id_user_id_key
        UNIQUE (id, user_id),
      CONSTRAINT recipes_name_length_check
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 300),
      CONSTRAINT recipes_description_length_check
        CHECK (char_length(description) <= 20000),
      CONSTRAINT recipes_category_length_check
        CHECK (char_length(category) <= 100),
      CONSTRAINT recipes_cuisine_length_check
        CHECK (char_length(cuisine) <= 100),
      CONSTRAINT recipes_servings_check
        CHECK (servings IS NULL OR servings >= 0),
      CONSTRAINT recipes_prep_minutes_check
        CHECK (prep_minutes IS NULL OR prep_minutes >= 0),
      CONSTRAINT recipes_cook_minutes_check
        CHECK (cook_minutes IS NULL OR cook_minutes >= 0),
      CONSTRAINT recipes_difficulty_check
        CHECK (difficulty IS NULL OR difficulty IN ('EASY', 'MEDIUM', 'HARD')),
      CONSTRAINT recipes_notes_length_check
        CHECK (char_length(notes) <= 20000),
      CONSTRAINT recipes_source_length_check
        CHECK (source IS NULL OR char_length(source) <= 500)
    );
  END IF;

  IF to_regclass('public.recipe_ingredients') IS NULL THEN
    CREATE TABLE public.recipe_ingredients (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      recipe_id UUID NOT NULL,
      user_id UUID NOT NULL,
      name TEXT NOT NULL,
      quantity_text TEXT NOT NULL DEFAULT '',
      quantity_value NUMERIC(12, 4),
      unit TEXT NOT NULL DEFAULT '',
      preparation_note TEXT NOT NULL DEFAULT '',
      position INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT recipe_ingredients_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT recipe_ingredients_recipe_owner_fkey
        FOREIGN KEY (recipe_id, user_id)
        REFERENCES public.recipes (id, user_id)
        ON DELETE CASCADE,
      CONSTRAINT recipe_ingredients_name_length_check
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 300),
      CONSTRAINT recipe_ingredients_quantity_text_length_check
        CHECK (char_length(quantity_text) <= 100),
      CONSTRAINT recipe_ingredients_quantity_value_check
        CHECK (quantity_value IS NULL OR quantity_value >= 0),
      CONSTRAINT recipe_ingredients_unit_length_check
        CHECK (char_length(unit) <= 50),
      CONSTRAINT recipe_ingredients_preparation_note_length_check
        CHECK (char_length(preparation_note) <= 500),
      CONSTRAINT recipe_ingredients_position_check
        CHECK (position >= 0)
    );
  END IF;

  IF to_regclass('public.recipe_steps') IS NULL THEN
    CREATE TABLE public.recipe_steps (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      recipe_id UUID NOT NULL,
      user_id UUID NOT NULL,
      instruction TEXT NOT NULL,
      duration_minutes INTEGER,
      temperature_value NUMERIC(8, 2),
      temperature_unit TEXT,
      position INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT recipe_steps_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT recipe_steps_recipe_owner_fkey
        FOREIGN KEY (recipe_id, user_id)
        REFERENCES public.recipes (id, user_id)
        ON DELETE CASCADE,
      CONSTRAINT recipe_steps_instruction_length_check
        CHECK (char_length(btrim(instruction)) BETWEEN 1 AND 20000),
      CONSTRAINT recipe_steps_duration_check
        CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
      CONSTRAINT recipe_steps_temperature_value_check
        CHECK (temperature_value IS NULL OR temperature_value >= 0),
      CONSTRAINT recipe_steps_temperature_unit_check
        CHECK (temperature_unit IS NULL OR temperature_unit IN ('F', 'C')),
      CONSTRAINT recipe_steps_position_check
        CHECK (position >= 0)
    );
  END IF;
END
$migration_006_tables$;

DO $migration_006_schema_validation$
DECLARE
  mismatch_count INTEGER;
BEGIN
  WITH expected (
    table_name,
    column_name,
    udt_name,
    is_nullable,
    normalized_default,
    numeric_precision,
    numeric_scale
  ) AS (
    VALUES
      ('recipe_books', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'description', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'cover_label', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_books', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),

      ('recipes', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'recipe_book_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'description', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'category', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'cuisine', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'servings', 'numeric', 'YES', '', 8, 2),
      ('recipes', 'prep_minutes', 'int4', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'cook_minutes', 'int4', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'difficulty', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'notes', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'source', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'is_favorite', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('recipes', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),

      ('recipe_ingredients', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'recipe_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'quantity_text', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'quantity_value', 'numeric', 'YES', '', 12, 4),
      ('recipe_ingredients', 'unit', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'preparation_note', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'position', 'int4', 'NO', '0', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_ingredients', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),

      ('recipe_steps', 'id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'recipe_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'instruction', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'duration_minutes', 'int4', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'temperature_value', 'numeric', 'YES', '', 8, 2),
      ('recipe_steps', 'temperature_unit', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'position', 'int4', 'NO', '0', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('recipe_steps', 'updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER)
  )
  SELECT count(*)
  INTO mismatch_count
  FROM expected
  LEFT JOIN information_schema.columns AS actual
    ON actual.table_schema = 'public'
   AND actual.table_name = expected.table_name
   AND actual.column_name = expected.column_name
  WHERE actual.column_name IS NULL
     OR actual.udt_name <> expected.udt_name
     OR actual.is_nullable <> expected.is_nullable
     OR COALESCE(
          regexp_replace(actual.column_default, '\s', '', 'g'),
          ''
        ) <> expected.normalized_default
     OR (
       expected.numeric_precision IS NOT NULL
       AND actual.numeric_precision <> expected.numeric_precision
     )
     OR (
       expected.numeric_scale IS NOT NULL
       AND actual.numeric_scale <> expected.numeric_scale
     );

  IF mismatch_count <> 0 OR (
    SELECT count(*)
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN (
        'recipe_books',
        'recipes',
        'recipe_ingredients',
        'recipe_steps'
      )
  ) <> 46 THEN
    RAISE EXCEPTION
      'Incompatible dedicated Recipe Books column definitions';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.recipe_books'::regclass
  ) <> 6 OR (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.recipes'::regclass
  ) <> 14 OR (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.recipe_ingredients'::regclass
  ) <> 9 OR (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.recipe_steps'::regclass
  ) <> 8 THEN
    RAISE EXCEPTION
      'Missing, extra, or incompatible dedicated Recipe Books constraints';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.recipes'::regclass
      AND conname = 'recipes_book_owner_fkey'
      AND confrelid = 'public.recipe_books'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (recipe_book_id, user_id) REFERENCES recipe_books(id, user_id) ON DELETE CASCADE'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.recipe_ingredients'::regclass
      AND conname = 'recipe_ingredients_recipe_owner_fkey'
      AND confrelid = 'public.recipes'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (recipe_id, user_id) REFERENCES recipes(id, user_id) ON DELETE CASCADE'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.recipe_steps'::regclass
      AND conname = 'recipe_steps_recipe_owner_fkey'
      AND confrelid = 'public.recipes'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
      AND pg_get_constraintdef(oid, true)
        = 'FOREIGN KEY (recipe_id, user_id) REFERENCES recipes(id, user_id) ON DELETE CASCADE'
  ) THEN
    RAISE EXCEPTION
      'Dedicated Recipe Books composite ownership foreign keys are incompatible';
  END IF;
END
$migration_006_schema_validation$;

DO $migration_006_conflicts$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_book
    JOIN public.recipe_books AS target_book
      ON target_book.id = source_book.id
    WHERE source_book.kind = 'recipes'
      AND (
        target_book.user_id IS DISTINCT FROM source_book.user_id
        OR target_book.name IS DISTINCT FROM source_book.name
        OR target_book.description IS DISTINCT FROM COALESCE(
          source_book.description,
          ''
        )
        OR target_book.cover_label IS NOT NULL
        OR target_book.is_archived IS DISTINCT FROM false
        OR (
          source_book.created_at IS NOT NULL
          AND target_book.created_at IS DISTINCT FROM source_book.created_at
        )
        OR target_book.updated_at IS DISTINCT FROM COALESCE(
          source_book.created_at,
          target_book.created_at
        )
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: an existing recipe_books ID conflicts with transformed source content';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_book
    WHERE source_book.kind = 'recipes'
      AND (
        EXISTS (
          SELECT 1
          FROM public.recipes
          WHERE recipes.id = source_book.id
        )
        OR EXISTS (
          SELECT 1
          FROM public.recipe_ingredients
          WHERE recipe_ingredients.id = source_book.id
        )
        OR EXISTS (
          SELECT 1
          FROM public.recipe_steps
          WHERE recipe_steps.id = source_book.id
        )
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a source Recipe Book ID conflicts with another target entity role';
  END IF;

  IF EXISTS (
    WITH expected_recipes AS (
      SELECT
        source_recipe.id,
        source_recipe.project_id AS recipe_book_id,
        source_recipe.user_id,
        source_recipe.title AS name,
        COALESCE(source_recipe.description, '') AS description,
        CASE
          WHEN NOT source_recipe.metadata ? 'servings'
            OR source_recipe.metadata -> 'servings' = 'null'::jsonb
            THEN NULL
          ELSE (source_recipe.metadata ->> 'servings')::NUMERIC(8, 2)
        END AS servings,
        CASE
          WHEN NOT source_recipe.metadata ? 'prep_minutes'
            OR source_recipe.metadata -> 'prep_minutes' = 'null'::jsonb
            THEN NULL
          ELSE (source_recipe.metadata ->> 'prep_minutes')::NUMERIC::INTEGER
        END AS prep_minutes,
        CASE
          WHEN NOT source_recipe.metadata ? 'cook_minutes'
            OR source_recipe.metadata -> 'cook_minutes' = 'null'::jsonb
            THEN NULL
          ELSE (source_recipe.metadata ->> 'cook_minutes')::NUMERIC::INTEGER
        END AS cook_minutes,
        COALESCE(source_recipe.is_pinned, false) AS is_favorite,
        COALESCE(source_recipe.is_archived, false) AS is_archived,
        source_recipe.created_at AS source_created_at,
        source_recipe.updated_at AS source_updated_at
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM expected_recipes AS source_recipe
    JOIN public.recipes AS target_recipe
      ON target_recipe.id = source_recipe.id
    WHERE target_recipe.user_id IS DISTINCT FROM source_recipe.user_id
       OR target_recipe.recipe_book_id IS DISTINCT FROM source_recipe.recipe_book_id
       OR target_recipe.name IS DISTINCT FROM source_recipe.name
       OR target_recipe.description IS DISTINCT FROM source_recipe.description
       OR target_recipe.category IS DISTINCT FROM ''
       OR target_recipe.cuisine IS DISTINCT FROM ''
       OR target_recipe.servings IS DISTINCT FROM source_recipe.servings
       OR target_recipe.prep_minutes IS DISTINCT FROM source_recipe.prep_minutes
       OR target_recipe.cook_minutes IS DISTINCT FROM source_recipe.cook_minutes
       OR target_recipe.difficulty IS NOT NULL
       OR target_recipe.notes IS DISTINCT FROM ''
       OR target_recipe.source IS NOT NULL
       OR target_recipe.is_favorite IS DISTINCT FROM source_recipe.is_favorite
       OR target_recipe.is_archived IS DISTINCT FROM source_recipe.is_archived
       OR (
         source_recipe.source_created_at IS NOT NULL
         AND target_recipe.created_at IS DISTINCT FROM source_recipe.source_created_at
       )
       OR target_recipe.updated_at IS DISTINCT FROM COALESCE(
         source_recipe.source_updated_at,
         source_recipe.source_created_at,
         target_recipe.created_at
       )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: an existing recipes ID conflicts with transformed source content';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS source_recipe
    JOIN public.projects AS source_book
      ON source_book.id = source_recipe.project_id
    WHERE source_book.kind = 'recipes'
      AND (
        EXISTS (
          SELECT 1
          FROM public.recipe_books
          WHERE recipe_books.id = source_recipe.id
        )
        OR EXISTS (
          SELECT 1
          FROM public.recipe_ingredients
          WHERE recipe_ingredients.id = source_recipe.id
        )
        OR EXISTS (
          SELECT 1
          FROM public.recipe_steps
          WHERE recipe_steps.id = source_recipe.id
        )
      )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a source recipe ID conflicts with another target entity role';
  END IF;

  IF EXISTS (
    WITH generated_ingredients AS (
      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id,
        source_recipe.id AS recipe_id,
        source_recipe.user_id,
        ingredient.ordinality - 1 AS position,
        btrim(ingredient.value) AS name,
        source_recipe.created_at AS source_created_at,
        source_recipe.updated_at AS source_updated_at
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata) = 'object'
           AND jsonb_typeof(source_recipe.metadata -> 'ingredients') = 'array'
            THEN source_recipe.metadata -> 'ingredients'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS ingredient(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':ingredient:' ||
          (ingredient.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM generated_ingredients AS source_ingredient
    JOIN public.recipe_ingredients AS target_ingredient
      ON target_ingredient.id = source_ingredient.id
    WHERE target_ingredient.recipe_id IS DISTINCT FROM source_ingredient.recipe_id
       OR target_ingredient.user_id IS DISTINCT FROM source_ingredient.user_id
       OR target_ingredient.position IS DISTINCT FROM source_ingredient.position
       OR target_ingredient.name IS DISTINCT FROM source_ingredient.name
       OR target_ingredient.quantity_text IS DISTINCT FROM ''
       OR target_ingredient.quantity_value IS NOT NULL
       OR target_ingredient.unit IS DISTINCT FROM ''
       OR target_ingredient.preparation_note IS DISTINCT FROM ''
       OR (
         source_ingredient.source_created_at IS NOT NULL
         AND target_ingredient.created_at IS DISTINCT FROM source_ingredient.source_created_at
       )
       OR target_ingredient.updated_at IS DISTINCT FROM COALESCE(
         source_ingredient.source_updated_at,
         source_ingredient.source_created_at,
         target_ingredient.created_at
       )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a deterministic ingredient ID conflicts with transformed source content';
  END IF;

  IF EXISTS (
    WITH generated_ingredients AS (
      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata -> 'ingredients') = 'array'
            THEN source_recipe.metadata -> 'ingredients'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS ingredient(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':ingredient:' ||
          (ingredient.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM generated_ingredients
    WHERE EXISTS (
      SELECT 1 FROM public.recipe_books
      WHERE recipe_books.id = generated_ingredients.id
    ) OR EXISTS (
      SELECT 1 FROM public.recipes
      WHERE recipes.id = generated_ingredients.id
    ) OR EXISTS (
      SELECT 1 FROM public.recipe_steps
      WHERE recipe_steps.id = generated_ingredients.id
    )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a deterministic ingredient ID conflicts with another target entity role';
  END IF;

  IF EXISTS (
    WITH generated_steps AS (
      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id,
        source_recipe.id AS recipe_id,
        source_recipe.user_id,
        step.ordinality - 1 AS position,
        btrim(step.value) AS instruction,
        source_recipe.created_at AS source_created_at,
        source_recipe.updated_at AS source_updated_at
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata) = 'object'
           AND jsonb_typeof(source_recipe.metadata -> 'steps') = 'array'
            THEN source_recipe.metadata -> 'steps'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS step(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':step:' ||
          (step.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM generated_steps AS source_step
    JOIN public.recipe_steps AS target_step
      ON target_step.id = source_step.id
    WHERE target_step.recipe_id IS DISTINCT FROM source_step.recipe_id
       OR target_step.user_id IS DISTINCT FROM source_step.user_id
       OR target_step.position IS DISTINCT FROM source_step.position
       OR target_step.instruction IS DISTINCT FROM source_step.instruction
       OR target_step.duration_minutes IS NOT NULL
       OR target_step.temperature_value IS NOT NULL
       OR target_step.temperature_unit IS NOT NULL
       OR (
         source_step.source_created_at IS NOT NULL
         AND target_step.created_at IS DISTINCT FROM source_step.source_created_at
       )
       OR target_step.updated_at IS DISTINCT FROM COALESCE(
         source_step.source_updated_at,
         source_step.source_created_at,
         target_step.created_at
       )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a deterministic step ID conflicts with transformed source content';
  END IF;

  IF EXISTS (
    WITH generated_steps AS (
      SELECT
        (
          substr(hash_value, 1, 8) || '-' ||
          substr(hash_value, 9, 4) || '-5' ||
          substr(hash_value, 14, 3) || '-a' ||
          substr(hash_value, 18, 3) || '-' ||
          substr(hash_value, 21, 12)
        )::UUID AS id
      FROM public.tasks AS source_recipe
      JOIN public.projects AS source_book
        ON source_book.id = source_recipe.project_id
      CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
          WHEN jsonb_typeof(source_recipe.metadata -> 'steps') = 'array'
            THEN source_recipe.metadata -> 'steps'
          ELSE '[]'::jsonb
        END
      ) WITH ORDINALITY AS step(value, ordinality)
      CROSS JOIN LATERAL (
        SELECT md5(
          source_recipe.id::text || ':step:' ||
          (step.ordinality - 1)::text
        ) AS hash_value
      ) AS deterministic
      WHERE source_book.kind = 'recipes'
    )
    SELECT 1
    FROM generated_steps
    WHERE EXISTS (
      SELECT 1 FROM public.recipe_books
      WHERE recipe_books.id = generated_steps.id
    ) OR EXISTS (
      SELECT 1 FROM public.recipes
      WHERE recipes.id = generated_steps.id
    ) OR EXISTS (
      SELECT 1 FROM public.recipe_ingredients
      WHERE recipe_ingredients.id = generated_steps.id
    )
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill aborted: a deterministic step ID conflicts with another target entity role';
  END IF;


END
$migration_006_conflicts$;

CREATE INDEX IF NOT EXISTS idx_recipe_books_user
  ON public.recipe_books (user_id);

CREATE INDEX IF NOT EXISTS idx_recipe_books_archive
  ON public.recipe_books (user_id, is_archived);

CREATE INDEX IF NOT EXISTS idx_recipe_books_updated
  ON public.recipe_books (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recipes_parent_ordering
  ON public.recipes (recipe_book_id, is_archived, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recipes_favorites
  ON public.recipes (user_id, is_favorite)
  WHERE is_archived = false;

CREATE INDEX IF NOT EXISTS idx_recipes_archive
  ON public.recipes (user_id, is_archived);

CREATE INDEX IF NOT EXISTS idx_recipes_category
  ON public.recipes (user_id, category)
  WHERE category <> '';

CREATE INDEX IF NOT EXISTS idx_recipes_cuisine
  ON public.recipes (user_id, cuisine)
  WHERE cuisine <> '';

CREATE INDEX IF NOT EXISTS idx_recipes_ownership
  ON public.recipes (user_id, recipe_book_id);

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_parent_ordering
  ON public.recipe_ingredients (recipe_id, position, created_at);

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ownership
  ON public.recipe_ingredients (user_id, recipe_id);

CREATE INDEX IF NOT EXISTS idx_recipe_steps_parent_ordering
  ON public.recipe_steps (recipe_id, position, created_at);

CREATE INDEX IF NOT EXISTS idx_recipe_steps_ownership
  ON public.recipe_steps (user_id, recipe_id);

DO $migration_006_triggers$
DECLARE
  target_table TEXT;
  target_trigger TEXT;
BEGIN
  FOR target_table, target_trigger IN
    SELECT *
    FROM (
      VALUES
        ('recipe_books', 'update_recipe_books_updated_at'),
        ('recipes', 'update_recipes_updated_at'),
        ('recipe_ingredients', 'update_recipe_ingredients_updated_at'),
        ('recipe_steps', 'update_recipe_steps_updated_at')
    ) AS expected(table_name, trigger_name)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_trigger
      WHERE tgrelid = format('public.%I', target_table)::regclass
        AND tgname = target_trigger
        AND NOT tgisinternal
    ) THEN
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column()',
        target_trigger,
        target_table
      );
    END IF;
  END LOOP;

  IF (
    SELECT count(*)
    FROM pg_trigger
    WHERE tgrelid IN (
      'public.recipe_books'::regclass,
      'public.recipes'::regclass,
      'public.recipe_ingredients'::regclass,
      'public.recipe_steps'::regclass
    )
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true)
        LIKE '%EXECUTE FUNCTION update_updated_at_column()'
  ) <> 4 THEN
    RAISE EXCEPTION
      'Dedicated Recipe Books updated_at triggers are incompatible';
  END IF;
END
$migration_006_triggers$;

ALTER TABLE public.recipe_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recipe_ingredients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recipe_steps ENABLE ROW LEVEL SECURITY;

DO $migration_006_policies$
DECLARE
  policy_row RECORD;
  predicate TEXT;
  policy_mismatch_count INTEGER;
BEGIN
  FOR policy_row IN
    SELECT *
    FROM (
      VALUES
        ('recipe_books', 'recipe_books', 'user_id = auth.uid()'),
        (
          'recipes',
          'recipes',
          'user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.recipe_books AS parent_book WHERE parent_book.id = recipes.recipe_book_id AND parent_book.user_id = auth.uid() AND parent_book.user_id = recipes.user_id)'
        ),
        (
          'recipe_ingredients',
          'recipe_ingredients',
          'user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.recipes AS parent_recipe WHERE parent_recipe.id = recipe_ingredients.recipe_id AND parent_recipe.user_id = auth.uid() AND parent_recipe.user_id = recipe_ingredients.user_id)'
        ),
        (
          'recipe_steps',
          'recipe_steps',
          'user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.recipes AS parent_recipe WHERE parent_recipe.id = recipe_steps.recipe_id AND parent_recipe.user_id = auth.uid() AND parent_recipe.user_id = recipe_steps.user_id)'
        )
    ) AS expected(table_name, policy_prefix, ownership_predicate)
  LOOP
    predicate := policy_row.ownership_predicate;

    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = policy_row.table_name
        AND policyname = policy_row.policy_prefix || '_select_own'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (%s)',
        policy_row.policy_prefix || '_select_own',
        policy_row.table_name,
        predicate
      );
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = policy_row.table_name
        AND policyname = policy_row.policy_prefix || '_insert_own'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (%s)',
        policy_row.policy_prefix || '_insert_own',
        policy_row.table_name,
        predicate
      );
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = policy_row.table_name
        AND policyname = policy_row.policy_prefix || '_update_own'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (%s) WITH CHECK (%s)',
        policy_row.policy_prefix || '_update_own',
        policy_row.table_name,
        predicate,
        predicate
      );
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = policy_row.table_name
        AND policyname = policy_row.policy_prefix || '_delete_own'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (%s)',
        policy_row.policy_prefix || '_delete_own',
        policy_row.table_name,
        predicate
      );
    END IF;
  END LOOP;

  IF (
    SELECT count(*)
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN (
        'recipe_books',
        'recipes',
        'recipe_ingredients',
        'recipe_steps'
      )
      AND roles = ARRAY['authenticated']::name[]
      AND cmd IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
  ) <> 16 OR EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN (
        'recipe_books',
        'recipes',
        'recipe_ingredients',
        'recipe_steps'
      )
      AND (
        roles <> ARRAY['authenticated']::name[]
        OR cmd NOT IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
      )
  ) THEN
    RAISE EXCEPTION
      'Dedicated Recipe Books policies are missing or incompatible';
  END IF;

  WITH expected(table_name, policy_name, command, parent_table) AS (
    VALUES
      ('recipe_books', 'recipe_books_select_own', 'SELECT', NULL::TEXT),
      ('recipe_books', 'recipe_books_insert_own', 'INSERT', NULL::TEXT),
      ('recipe_books', 'recipe_books_update_own', 'UPDATE', NULL::TEXT),
      ('recipe_books', 'recipe_books_delete_own', 'DELETE', NULL::TEXT),
      ('recipes', 'recipes_select_own', 'SELECT', 'recipe_books'),
      ('recipes', 'recipes_insert_own', 'INSERT', 'recipe_books'),
      ('recipes', 'recipes_update_own', 'UPDATE', 'recipe_books'),
      ('recipes', 'recipes_delete_own', 'DELETE', 'recipe_books'),
      ('recipe_ingredients', 'recipe_ingredients_select_own', 'SELECT', 'recipes'),
      ('recipe_ingredients', 'recipe_ingredients_insert_own', 'INSERT', 'recipes'),
      ('recipe_ingredients', 'recipe_ingredients_update_own', 'UPDATE', 'recipes'),
      ('recipe_ingredients', 'recipe_ingredients_delete_own', 'DELETE', 'recipes'),
      ('recipe_steps', 'recipe_steps_select_own', 'SELECT', 'recipes'),
      ('recipe_steps', 'recipe_steps_insert_own', 'INSERT', 'recipes'),
      ('recipe_steps', 'recipe_steps_update_own', 'UPDATE', 'recipes'),
      ('recipe_steps', 'recipe_steps_delete_own', 'DELETE', 'recipes')
  )
  SELECT count(*)
  INTO policy_mismatch_count
  FROM expected
  LEFT JOIN pg_policies AS actual
    ON actual.schemaname = 'public'
   AND actual.tablename = expected.table_name
   AND actual.policyname = expected.policy_name
   AND actual.cmd = expected.command
   AND actual.roles = ARRAY['authenticated']::name[]
  WHERE actual.policyname IS NULL
     OR (
       expected.command IN ('SELECT', 'DELETE')
       AND (
         actual.qual IS NULL
         OR actual.with_check IS NOT NULL
         OR position('auth.uid()' IN actual.qual) = 0
         OR (
           expected.parent_table IS NOT NULL
           AND position(expected.parent_table IN actual.qual) = 0
         )
       )
     )
     OR (
       expected.command = 'INSERT'
       AND (
         actual.qual IS NOT NULL
         OR actual.with_check IS NULL
         OR position('auth.uid()' IN actual.with_check) = 0
         OR (
           expected.parent_table IS NOT NULL
           AND position(expected.parent_table IN actual.with_check) = 0
         )
       )
     )
     OR (
       expected.command = 'UPDATE'
       AND (
         actual.qual IS NULL
         OR actual.with_check IS NULL
         OR position('auth.uid()' IN actual.qual) = 0
         OR position('auth.uid()' IN actual.with_check) = 0
         OR (
           expected.parent_table IS NOT NULL
           AND (
             position(expected.parent_table IN actual.qual) = 0
             OR position(expected.parent_table IN actual.with_check) = 0
           )
         )
       )
     );

  IF policy_mismatch_count <> 0 THEN
    RAISE EXCEPTION
      'Dedicated Recipe Books policy definitions are incompatible';
  END IF;
END
$migration_006_policies$;

REVOKE ALL PRIVILEGES
  ON TABLE
    public.recipe_books,
    public.recipes,
    public.recipe_ingredients,
    public.recipe_steps
  FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON TABLE
    public.recipe_books,
    public.recipes,
    public.recipe_ingredients,
    public.recipe_steps
  TO authenticated;


INSERT INTO public.recipe_books (
  id,
  user_id,
  name,
  description,
  cover_label,
  is_archived,
  created_at,
  updated_at
)
SELECT
  source_book.id,
  source_book.user_id,
  source_book.name,
  COALESCE(source_book.description, ''),
  NULL,
  false,
  COALESCE(source_book.created_at, now()),
  COALESCE(source_book.created_at, now())
FROM public.projects AS source_book
WHERE source_book.kind = 'recipes'
  AND NOT EXISTS (
    SELECT 1
    FROM public.recipe_books AS target_book
    WHERE target_book.id = source_book.id
  );

WITH source_recipes AS (
  SELECT
    source_recipe.*,
    CASE
      WHEN jsonb_typeof(source_recipe.metadata) = 'object'
        THEN source_recipe.metadata
      ELSE '{}'::jsonb
    END AS safe_metadata
  FROM public.tasks AS source_recipe
  JOIN public.projects AS source_book
    ON source_book.id = source_recipe.project_id
  WHERE source_book.kind = 'recipes'
)
INSERT INTO public.recipes (
  id,
  recipe_book_id,
  user_id,
  name,
  description,
  category,
  cuisine,
  servings,
  prep_minutes,
  cook_minutes,
  difficulty,
  notes,
  source,
  is_favorite,
  is_archived,
  created_at,
  updated_at
)
SELECT
  source_recipe.id,
  source_recipe.project_id,
  source_recipe.user_id,
  source_recipe.title,
  COALESCE(source_recipe.description, ''),
  '',
  '',
  CASE
    WHEN NOT source_recipe.safe_metadata ? 'servings'
      OR source_recipe.safe_metadata -> 'servings' = 'null'::jsonb
      THEN NULL
    ELSE (source_recipe.safe_metadata ->> 'servings')::NUMERIC(8, 2)
  END,
  CASE
    WHEN NOT source_recipe.safe_metadata ? 'prep_minutes'
      OR source_recipe.safe_metadata -> 'prep_minutes' = 'null'::jsonb
      THEN NULL
    ELSE (source_recipe.safe_metadata ->> 'prep_minutes')::NUMERIC::INTEGER
  END,
  CASE
    WHEN NOT source_recipe.safe_metadata ? 'cook_minutes'
      OR source_recipe.safe_metadata -> 'cook_minutes' = 'null'::jsonb
      THEN NULL
    ELSE (source_recipe.safe_metadata ->> 'cook_minutes')::NUMERIC::INTEGER
  END,
  NULL,
  '',
  NULL,
  COALESCE(source_recipe.is_pinned, false),
  COALESCE(source_recipe.is_archived, false),
  COALESCE(source_recipe.created_at, now()),
  COALESCE(
    source_recipe.updated_at,
    source_recipe.created_at,
    now()
  )
FROM source_recipes AS source_recipe
WHERE NOT EXISTS (
  SELECT 1
  FROM public.recipes AS target_recipe
  WHERE target_recipe.id = source_recipe.id
);

WITH generated_ingredients AS (
  SELECT
    (
      substr(hash_value, 1, 8) || '-' ||
      substr(hash_value, 9, 4) || '-5' ||
      substr(hash_value, 14, 3) || '-a' ||
      substr(hash_value, 18, 3) || '-' ||
      substr(hash_value, 21, 12)
    )::UUID AS id,
    source_recipe.id AS recipe_id,
    source_recipe.user_id,
    btrim(ingredient.value) AS name,
    ingredient.ordinality - 1 AS position,
    COALESCE(source_recipe.created_at, now()) AS created_at,
    COALESCE(
      source_recipe.updated_at,
      source_recipe.created_at,
      now()
    ) AS updated_at
  FROM public.tasks AS source_recipe
  JOIN public.projects AS source_book
    ON source_book.id = source_recipe.project_id
  CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE
      WHEN jsonb_typeof(source_recipe.metadata) = 'object'
       AND jsonb_typeof(source_recipe.metadata -> 'ingredients') = 'array'
        THEN source_recipe.metadata -> 'ingredients'
      ELSE '[]'::jsonb
    END
  ) WITH ORDINALITY AS ingredient(value, ordinality)
  CROSS JOIN LATERAL (
    SELECT md5(
      source_recipe.id::text || ':ingredient:' ||
      (ingredient.ordinality - 1)::text
    ) AS hash_value
  ) AS deterministic
  WHERE source_book.kind = 'recipes'
)
INSERT INTO public.recipe_ingredients (
  id,
  recipe_id,
  user_id,
  name,
  quantity_text,
  quantity_value,
  unit,
  preparation_note,
  position,
  created_at,
  updated_at
)
SELECT
  source_ingredient.id,
  source_ingredient.recipe_id,
  source_ingredient.user_id,
  source_ingredient.name,
  '',
  NULL,
  '',
  '',
  source_ingredient.position,
  source_ingredient.created_at,
  source_ingredient.updated_at
FROM generated_ingredients AS source_ingredient
WHERE NOT EXISTS (
  SELECT 1
  FROM public.recipe_ingredients AS target_ingredient
  WHERE target_ingredient.id = source_ingredient.id
);

WITH generated_steps AS (
  SELECT
    (
      substr(hash_value, 1, 8) || '-' ||
      substr(hash_value, 9, 4) || '-5' ||
      substr(hash_value, 14, 3) || '-a' ||
      substr(hash_value, 18, 3) || '-' ||
      substr(hash_value, 21, 12)
    )::UUID AS id,
    source_recipe.id AS recipe_id,
    source_recipe.user_id,
    btrim(step.value) AS instruction,
    step.ordinality - 1 AS position,
    COALESCE(source_recipe.created_at, now()) AS created_at,
    COALESCE(
      source_recipe.updated_at,
      source_recipe.created_at,
      now()
    ) AS updated_at
  FROM public.tasks AS source_recipe
  JOIN public.projects AS source_book
    ON source_book.id = source_recipe.project_id
  CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE
      WHEN jsonb_typeof(source_recipe.metadata) = 'object'
       AND jsonb_typeof(source_recipe.metadata -> 'steps') = 'array'
        THEN source_recipe.metadata -> 'steps'
      ELSE '[]'::jsonb
    END
  ) WITH ORDINALITY AS step(value, ordinality)
  CROSS JOIN LATERAL (
    SELECT md5(
      source_recipe.id::text || ':step:' ||
      (step.ordinality - 1)::text
    ) AS hash_value
  ) AS deterministic
  WHERE source_book.kind = 'recipes'
)
INSERT INTO public.recipe_steps (
  id,
  recipe_id,
  user_id,
  instruction,
  duration_minutes,
  temperature_value,
  temperature_unit,
  position,
  created_at,
  updated_at
)
SELECT
  source_step.id,
  source_step.recipe_id,
  source_step.user_id,
  source_step.instruction,
  NULL,
  NULL,
  NULL,
  source_step.position,
  source_step.created_at,
  source_step.updated_at
FROM generated_steps AS source_step
WHERE NOT EXISTS (
  SELECT 1
  FROM public.recipe_steps AS target_step
  WHERE target_step.id = source_step.id
);

DO $migration_006_postflight$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_book
    LEFT JOIN public.recipe_books AS target_book
      ON target_book.id = source_book.id
     AND target_book.user_id = source_book.user_id
    WHERE source_book.kind = 'recipes'
      AND target_book.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill postflight failed: missing or ownership-mismatched recipe book';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS source_recipe
    JOIN public.projects AS source_book
      ON source_book.id = source_recipe.project_id
    LEFT JOIN public.recipes AS target_recipe
      ON target_recipe.id = source_recipe.id
     AND target_recipe.recipe_book_id = source_recipe.project_id
     AND target_recipe.user_id = source_recipe.user_id
    WHERE source_book.kind = 'recipes'
      AND target_recipe.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill postflight failed: missing, parent-mismatched, or ownership-mismatched recipe';
  END IF;

  IF EXISTS (
    SELECT id
    FROM (
      SELECT recipe_ingredient.id
      FROM public.recipe_ingredients AS recipe_ingredient
      UNION ALL
      SELECT recipe_step.id
      FROM public.recipe_steps AS recipe_step
    ) AS child_ids
    GROUP BY id
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill postflight failed: duplicate child IDs exist across ingredient and step tables';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_project
    JOIN public.recipe_books AS target_book
      ON target_book.id = source_project.id
    WHERE source_project.kind IN ('board', 'shopping')
  ) OR EXISTS (
    SELECT 1
    FROM public.tasks AS source_task
    JOIN public.projects AS source_project
      ON source_project.id = source_task.project_id
    JOIN public.recipes AS target_recipe
      ON target_recipe.id = source_task.id
    WHERE source_project.kind IN ('board', 'shopping')
  ) THEN
    RAISE EXCEPTION
      'Recipe backfill postflight failed: Task Board or Shopping List IDs were copied';
  END IF;
END
$migration_006_postflight$;

COMMIT;

-- -------------------------------------------------------------------------
-- REVIEW-ONLY VERIFICATION QUERIES
-- Run separately after an explicitly approved application. Every statement
-- below is SELECT-only and avoids user-entered content and complete user IDs.
-- -------------------------------------------------------------------------
/*
-- Source and target aggregate counts.
SELECT
  (SELECT count(*) FROM public.projects WHERE kind = 'recipes')
    AS source_recipe_book_count,
  (
    SELECT count(*)
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
  ) AS source_recipe_count,
  (
    SELECT COALESCE(sum(jsonb_array_length(
      CASE
        WHEN jsonb_typeof(task_row.metadata) = 'object'
         AND jsonb_typeof(task_row.metadata -> 'ingredients') = 'array'
          THEN task_row.metadata -> 'ingredients'
        ELSE '[]'::jsonb
      END
    )), 0)
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
  ) AS source_ingredient_count,
  (
    SELECT COALESCE(sum(jsonb_array_length(
      CASE
        WHEN jsonb_typeof(task_row.metadata) = 'object'
         AND jsonb_typeof(task_row.metadata -> 'steps') = 'array'
          THEN task_row.metadata -> 'steps'
        ELSE '[]'::jsonb
      END
    )), 0)
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'recipes'
  ) AS source_step_count,
  (SELECT count(*) FROM public.recipe_books)
    AS target_recipe_book_count,
  (SELECT count(*) FROM public.recipes)
    AS target_recipe_count,
  (SELECT count(*) FROM public.recipe_ingredients)
    AS target_ingredient_count,
  (SELECT count(*) FROM public.recipe_steps)
    AS target_step_count;

-- Missing source IDs and parent/ownership mismatches.
SELECT
  count(*) FILTER (WHERE target_book.id IS NULL)
    AS missing_recipe_book_ids,
  count(*) FILTER (
    WHERE target_book.id IS NOT NULL
      AND target_book.user_id <> source_book.user_id
  ) AS recipe_book_ownership_mismatches
FROM public.projects AS source_book
LEFT JOIN public.recipe_books AS target_book
  ON target_book.id = source_book.id
WHERE source_book.kind = 'recipes';

SELECT
  count(*) FILTER (WHERE target_recipe.id IS NULL)
    AS missing_recipe_ids,
  count(*) FILTER (
    WHERE target_recipe.id IS NOT NULL
      AND target_recipe.user_id <> source_recipe.user_id
  ) AS recipe_ownership_mismatches,
  count(*) FILTER (
    WHERE target_recipe.id IS NOT NULL
      AND target_recipe.recipe_book_id <> source_recipe.project_id
  ) AS recipe_parent_mismatches
FROM public.tasks AS source_recipe
JOIN public.projects AS source_book
  ON source_book.id = source_recipe.project_id
LEFT JOIN public.recipes AS target_recipe
  ON target_recipe.id = source_recipe.id
WHERE source_book.kind = 'recipes';

-- Malformed arrays and invalid source positions.
SELECT
  count(*) FILTER (
    WHERE metadata ? 'ingredients'
      AND metadata -> 'ingredients' <> 'null'::jsonb
      AND jsonb_typeof(metadata -> 'ingredients') <> 'array'
  ) AS malformed_ingredient_arrays,
  count(*) FILTER (
    WHERE metadata ? 'steps'
      AND metadata -> 'steps' <> 'null'::jsonb
      AND jsonb_typeof(metadata -> 'steps') <> 'array'
  ) AS malformed_step_arrays
FROM public.tasks AS task_row
JOIN public.projects AS project_row
  ON project_row.id = task_row.project_id
WHERE project_row.kind = 'recipes';

SELECT
  (SELECT count(*) FROM public.recipe_ingredients WHERE position < 0)
    AS negative_ingredient_positions,
  (SELECT count(*) FROM public.recipe_steps WHERE position < 0)
    AS negative_step_positions,
  (
    SELECT count(*)
    FROM (
      SELECT id
      FROM (
        SELECT id FROM public.recipe_ingredients
        UNION ALL
        SELECT id FROM public.recipe_steps
      ) AS child_ids
      GROUP BY id
      HAVING count(*) > 1
    ) AS duplicates
  ) AS duplicate_child_ids;

-- Task Board and Shopping List IDs must not be copied.
SELECT
  (
    SELECT count(*)
    FROM public.projects AS source_project
    JOIN public.recipe_books AS target_book
      ON target_book.id = source_project.id
    WHERE source_project.kind = 'board'
  ) AS copied_task_board_ids,
  (
    SELECT count(*)
    FROM public.projects AS source_project
    JOIN public.recipe_books AS target_book
      ON target_book.id = source_project.id
    WHERE source_project.kind = 'shopping'
  ) AS copied_shopping_list_ids;

-- Columns, constraints, indexes, triggers, RLS, policies, and grants.
SELECT
  table_name,
  ordinal_position,
  column_name,
  udt_name,
  is_nullable,
  column_default,
  numeric_precision,
  numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'recipe_books',
    'recipes',
    'recipe_ingredients',
    'recipe_steps'
  )
ORDER BY table_name, ordinal_position;

SELECT
  conrelid::regclass::text AS table_name,
  conname AS constraint_name,
  pg_get_constraintdef(oid, true) AS definition
FROM pg_constraint
WHERE conrelid IN (
  'public.recipe_books'::regclass,
  'public.recipes'::regclass,
  'public.recipe_ingredients'::regclass,
  'public.recipe_steps'::regclass
)
ORDER BY table_name, constraint_name;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'recipe_books',
    'recipes',
    'recipe_ingredients',
    'recipe_steps'
  )
ORDER BY tablename, indexname;

SELECT
  relname AS table_name,
  relrowsecurity AS rls_enabled,
  relforcerowsecurity AS rls_forced
FROM pg_class
WHERE oid IN (
  'public.recipe_books'::regclass,
  'public.recipes'::regclass,
  'public.recipe_ingredients'::regclass,
  'public.recipe_steps'::regclass
)
ORDER BY relname;

SELECT
  tablename,
  policyname,
  roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN (
    'recipe_books',
    'recipes',
    'recipe_ingredients',
    'recipe_steps'
  )
ORDER BY tablename, policyname;

SELECT
  table_name,
  grantee,
  privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name IN (
    'recipe_books',
    'recipes',
    'recipe_ingredients',
    'recipe_steps'
  )
  AND grantee IN ('anon', 'authenticated')
ORDER BY table_name, grantee, privilege_type;

-- Retry verification: all missing/pending counts must remain zero after a
-- separately approved second application.
SELECT
  (
    SELECT count(*)
    FROM public.projects AS source_book
    LEFT JOIN public.recipe_books AS target_book
      ON target_book.id = source_book.id
    WHERE source_book.kind = 'recipes'
      AND target_book.id IS NULL
  ) AS recipe_books_still_pending,
  (
    SELECT count(*)
    FROM public.tasks AS source_recipe
    JOIN public.projects AS source_book
      ON source_book.id = source_recipe.project_id
    LEFT JOIN public.recipes AS target_recipe
      ON target_recipe.id = source_recipe.id
    WHERE source_book.kind = 'recipes'
      AND target_recipe.id IS NULL
  ) AS recipes_still_pending;
*/
