-- Migration 005: Create dedicated Shopping List tables and retain a guarded
-- compatibility backfill from projects/tasks.
--
-- Prerequisite: migration 004 must have completed successfully.
-- Preservation: generalized projects/tasks rows are retained unchanged.
-- Scope: projects.kind = 'shopping' only; board and recipes rows are excluded.
--
-- Deliberate ownership behavior:
--   * deleting an auth.users row cascades to that user's lists and items;
--   * deleting a shopping list cascades to its items;
--   * the composite item/list foreign key rejects cross-user relationships.

BEGIN;

DO $migration_005_preflight$
DECLARE
  kind_constraint TEXT;
BEGIN
  IF to_regclass('public.projects') IS NULL
     OR to_regclass('public.tasks') IS NULL THEN
    RAISE EXCEPTION
      'Migration 005 requires public.projects and public.tasks';
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
  ) THEN
    RAISE EXCEPTION
      'Migration 005 requires migration 004 public.projects.kind';
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
      'Migration 005 requires migration 004 public.tasks.metadata';
  END IF;

  SELECT lower(pg_get_constraintdef(oid, true))
  INTO kind_constraint
  FROM pg_constraint
  WHERE conname = 'projects_kind_check'
    AND conrelid = 'public.projects'::regclass
    AND contype = 'c';

  IF kind_constraint IS NULL
     OR kind_constraint NOT LIKE '%board%'
     OR kind_constraint NOT LIKE '%shopping%'
     OR kind_constraint NOT LIKE '%recipes%' THEN
    RAISE EXCEPTION
      'Migration 005 requires the migration 004 projects_kind_check';
  END IF;

  IF to_regclass('public.idx_projects_user_kind') IS NULL THEN
    RAISE EXCEPTION
      'Migration 005 requires migration 004 index idx_projects_user_kind';
  END IF;

  IF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
    RAISE EXCEPTION
      'Migration 005 requires public.update_updated_at_column()';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    LEFT JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: orphaned public.tasks rows must be resolved first';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'shopping'
      AND task_row.user_id <> project_row.user_id
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: shopping task/project ownership mismatch';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects
    WHERE kind = 'shopping'
      AND char_length(btrim(name)) NOT BETWEEN 1 AND 200
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: shopping project name violates the proposed list-name length constraint';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    CROSS JOIN LATERAL (
      SELECT CASE
        WHEN jsonb_typeof(task_row.metadata) = 'object'
          THEN task_row.metadata
        ELSE '{}'::jsonb
      END AS value
    ) AS safe_metadata
    WHERE project_row.kind = 'shopping'
      AND (
        char_length(btrim(task_row.title)) NOT BETWEEN 1 AND 300
        OR char_length(COALESCE(task_row.description, '')) > 10000
        OR char_length(
             CASE
               WHEN jsonb_typeof(safe_metadata.value -> 'quantity_text') IN ('string', 'number')
                 THEN safe_metadata.value ->> 'quantity_text'
               WHEN jsonb_typeof(safe_metadata.value -> 'quantity') IN ('string', 'number')
                 THEN safe_metadata.value ->> 'quantity'
               ELSE ''
             END
           ) > 100
        OR char_length(
             CASE
               WHEN jsonb_typeof(safe_metadata.value -> 'unit') = 'string'
                 THEN safe_metadata.value ->> 'unit'
               ELSE ''
             END
           ) > 50
        OR char_length(
             CASE
               WHEN jsonb_typeof(safe_metadata.value -> 'category') = 'string'
                 AND btrim(safe_metadata.value ->> 'category') <> ''
                 THEN safe_metadata.value ->> 'category'
               ELSE 'Other'
             END
           ) > 100
      )
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: shopping task text exceeds a target length constraint';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'shopping'
      AND COALESCE(task_row."order", 0) < 0
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: shopping task position is negative';
  END IF;
END
$migration_005_preflight$;

DO $migration_005_tables$
BEGIN
  IF to_regclass('public.shopping_lists') IS NULL THEN
    CREATE TABLE public.shopping_lists (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      shopping_date DATE,
      store_name TEXT,
      is_archived BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT shopping_lists_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT shopping_lists_id_user_id_key
        UNIQUE (id, user_id),
      CONSTRAINT shopping_lists_name_length_check
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
      CONSTRAINT shopping_lists_store_name_length_check
        CHECK (store_name IS NULL OR char_length(store_name) <= 200)
    );
  END IF;

  IF to_regclass('public.shopping_items') IS NULL THEN
    CREATE TABLE public.shopping_items (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      shopping_list_id UUID NOT NULL,
      user_id UUID NOT NULL,
      name TEXT NOT NULL,
      quantity_text TEXT NOT NULL DEFAULT '',
      unit TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL DEFAULT 'Other',
      notes TEXT NOT NULL DEFAULT '',
      estimated_price NUMERIC(12, 2),
      actual_price NUMERIC(12, 2),
      is_purchased BOOLEAN NOT NULL DEFAULT false,
      priority TEXT NOT NULL DEFAULT 'MEDIUM',
      position INTEGER NOT NULL DEFAULT 0,
      is_archived BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT shopping_items_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT shopping_items_list_owner_fkey
        FOREIGN KEY (shopping_list_id, user_id)
        REFERENCES public.shopping_lists (id, user_id)
        ON DELETE CASCADE,
      CONSTRAINT shopping_items_name_length_check
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 300),
      CONSTRAINT shopping_items_quantity_length_check
        CHECK (char_length(quantity_text) <= 100),
      CONSTRAINT shopping_items_unit_length_check
        CHECK (char_length(unit) <= 50),
      CONSTRAINT shopping_items_category_length_check
        CHECK (
          char_length(btrim(category)) BETWEEN 1 AND 100
        ),
      CONSTRAINT shopping_items_notes_length_check
        CHECK (char_length(notes) <= 10000),
      CONSTRAINT shopping_items_estimated_price_check
        CHECK (estimated_price IS NULL OR estimated_price >= 0),
      CONSTRAINT shopping_items_actual_price_check
        CHECK (actual_price IS NULL OR actual_price >= 0),
      CONSTRAINT shopping_items_priority_check
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')),
      CONSTRAINT shopping_items_position_check
        CHECK (position >= 0)
    );
  END IF;
END
$migration_005_tables$;

DO $migration_005_schema_validation$
DECLARE
  mismatch_count INTEGER;
BEGIN
  WITH expected (
    column_name,
    udt_name,
    is_nullable,
    normalized_default,
    numeric_precision,
    numeric_scale
  ) AS (
    VALUES
      ('id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('description', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('shopping_date', 'date', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('store_name', 'text', 'YES', '', NULL::INTEGER, NULL::INTEGER),
      ('is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER)
  )
  SELECT count(*)
  INTO mismatch_count
  FROM expected
  LEFT JOIN information_schema.columns AS actual
    ON actual.table_schema = 'public'
   AND actual.table_name = 'shopping_lists'
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

  IF mismatch_count <> 0
     OR (
       SELECT count(*)
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'shopping_lists'
     ) <> 9 THEN
    RAISE EXCEPTION
      'Incompatible existing public.shopping_lists definition';
  END IF;

  WITH expected (
    column_name,
    udt_name,
    is_nullable,
    normalized_default,
    numeric_precision,
    numeric_scale
  ) AS (
    VALUES
      ('id', 'uuid', 'NO', 'gen_random_uuid()', NULL::INTEGER, NULL::INTEGER),
      ('shopping_list_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('user_id', 'uuid', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('name', 'text', 'NO', '', NULL::INTEGER, NULL::INTEGER),
      ('quantity_text', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('unit', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('category', 'text', 'NO', '''Other''::text', NULL::INTEGER, NULL::INTEGER),
      ('notes', 'text', 'NO', '''''::text', NULL::INTEGER, NULL::INTEGER),
      ('estimated_price', 'numeric', 'YES', '', 12, 2),
      ('actual_price', 'numeric', 'YES', '', 12, 2),
      ('is_purchased', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('priority', 'text', 'NO', '''MEDIUM''::text', NULL::INTEGER, NULL::INTEGER),
      ('position', 'int4', 'NO', '0', NULL::INTEGER, NULL::INTEGER),
      ('is_archived', 'bool', 'NO', 'false', NULL::INTEGER, NULL::INTEGER),
      ('created_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER),
      ('updated_at', 'timestamptz', 'NO', 'now()', NULL::INTEGER, NULL::INTEGER)
  )
  SELECT count(*)
  INTO mismatch_count
  FROM expected
  LEFT JOIN information_schema.columns AS actual
    ON actual.table_schema = 'public'
   AND actual.table_name = 'shopping_items'
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

  IF mismatch_count <> 0
     OR (
       SELECT count(*)
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'shopping_items'
     ) <> 16 THEN
    RAISE EXCEPTION
      'Incompatible existing public.shopping_items definition';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_lists'::regclass
      AND conname IN (
        'shopping_lists_pkey',
        'shopping_lists_user_id_fkey',
        'shopping_lists_id_user_id_key',
        'shopping_lists_name_length_check',
        'shopping_lists_store_name_length_check'
      )
  ) <> 5 THEN
    RAISE EXCEPTION
      'Missing or incompatible required shopping_lists constraints';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.shopping_items'::regclass
      AND conname IN (
        'shopping_items_pkey',
        'shopping_items_user_id_fkey',
        'shopping_items_list_owner_fkey',
        'shopping_items_name_length_check',
        'shopping_items_quantity_length_check',
        'shopping_items_unit_length_check',
        'shopping_items_category_length_check',
        'shopping_items_notes_length_check',
        'shopping_items_estimated_price_check',
        'shopping_items_actual_price_check',
        'shopping_items_priority_check',
        'shopping_items_position_check'
      )
  ) <> 12 THEN
    RAISE EXCEPTION
      'Missing or incompatible required shopping_items constraints';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'shopping_lists_user_id_fkey'
      AND conrelid = 'public.shopping_lists'::regclass
      AND confrelid = 'auth.users'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
  ) THEN
    RAISE EXCEPTION
      'shopping_lists.user_id must cascade from auth.users';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'shopping_items_user_id_fkey'
      AND conrelid = 'public.shopping_items'::regclass
      AND confrelid = 'auth.users'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
  ) THEN
    RAISE EXCEPTION
      'shopping_items.user_id must cascade from auth.users';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'shopping_items_list_owner_fkey'
      AND conrelid = 'public.shopping_items'::regclass
      AND confrelid = 'public.shopping_lists'::regclass
      AND contype = 'f'
      AND confdeltype = 'c'
      AND pg_get_constraintdef(oid, true)
        LIKE 'FOREIGN KEY (shopping_list_id, user_id) REFERENCES shopping_lists(id, user_id) ON DELETE CASCADE'
  ) THEN
    RAISE EXCEPTION
      'shopping_items must use the composite owner/list cascading foreign key';
  END IF;
END
$migration_005_schema_validation$;

CREATE INDEX IF NOT EXISTS idx_shopping_lists_active
  ON public.shopping_lists (user_id, created_at DESC)
  WHERE is_archived = false;

CREATE INDEX IF NOT EXISTS idx_shopping_lists_date
  ON public.shopping_lists (user_id, shopping_date)
  WHERE shopping_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shopping_items_ordering
  ON public.shopping_items (
    shopping_list_id,
    is_archived,
    is_purchased,
    position,
    created_at
  );

CREATE INDEX IF NOT EXISTS idx_shopping_items_ownership
  ON public.shopping_items (user_id, shopping_list_id);

CREATE INDEX IF NOT EXISTS idx_shopping_items_category
  ON public.shopping_items (shopping_list_id, category);

CREATE INDEX IF NOT EXISTS idx_shopping_items_purchase_state
  ON public.shopping_items (user_id, is_purchased)
  WHERE is_archived = false;

CREATE INDEX IF NOT EXISTS idx_shopping_items_archive_state
  ON public.shopping_items (user_id, is_archived);

DO $migration_005_triggers$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_lists'::regclass
      AND tgname = 'update_shopping_lists_updated_at'
      AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER update_shopping_lists_updated_at
      BEFORE UPDATE ON public.shopping_lists
      FOR EACH ROW
      EXECUTE FUNCTION public.update_updated_at_column();
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_items'::regclass
      AND tgname = 'update_shopping_items_updated_at'
      AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER update_shopping_items_updated_at
      BEFORE UPDATE ON public.shopping_items
      FOR EACH ROW
      EXECUTE FUNCTION public.update_updated_at_column();
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_lists'::regclass
      AND tgname = 'update_shopping_lists_updated_at'
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true)
        LIKE '%EXECUTE FUNCTION update_updated_at_column()'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.shopping_items'::regclass
      AND tgname = 'update_shopping_items_updated_at'
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true)
        LIKE '%EXECUTE FUNCTION update_updated_at_column()'
  ) THEN
    RAISE EXCEPTION
      'Incompatible Shopping List updated_at trigger';
  END IF;
END
$migration_005_triggers$;

ALTER TABLE public.shopping_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shopping_items ENABLE ROW LEVEL SECURITY;

DO $migration_005_policies$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_lists'
      AND policyname = 'shopping_lists_select_own'
  ) THEN
    CREATE POLICY shopping_lists_select_own
      ON public.shopping_lists
      FOR SELECT
      TO authenticated
      USING (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_lists'
      AND policyname = 'shopping_lists_insert_own'
  ) THEN
    CREATE POLICY shopping_lists_insert_own
      ON public.shopping_lists
      FOR INSERT
      TO authenticated
      WITH CHECK (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_lists'
      AND policyname = 'shopping_lists_update_own'
  ) THEN
    CREATE POLICY shopping_lists_update_own
      ON public.shopping_lists
      FOR UPDATE
      TO authenticated
      USING (user_id = auth.uid())
      WITH CHECK (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_lists'
      AND policyname = 'shopping_lists_delete_own'
  ) THEN
    CREATE POLICY shopping_lists_delete_own
      ON public.shopping_lists
      FOR DELETE
      TO authenticated
      USING (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_items'
      AND policyname = 'shopping_items_select_own'
  ) THEN
    CREATE POLICY shopping_items_select_own
      ON public.shopping_items
      FOR SELECT
      TO authenticated
      USING (
        user_id = auth.uid()
        AND EXISTS (
          SELECT 1
          FROM public.shopping_lists AS parent_list
          WHERE parent_list.id = shopping_items.shopping_list_id
            AND parent_list.user_id = auth.uid()
            AND parent_list.user_id = shopping_items.user_id
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_items'
      AND policyname = 'shopping_items_insert_own'
  ) THEN
    CREATE POLICY shopping_items_insert_own
      ON public.shopping_items
      FOR INSERT
      TO authenticated
      WITH CHECK (
        user_id = auth.uid()
        AND EXISTS (
          SELECT 1
          FROM public.shopping_lists AS parent_list
          WHERE parent_list.id = shopping_items.shopping_list_id
            AND parent_list.user_id = auth.uid()
            AND parent_list.user_id = shopping_items.user_id
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_items'
      AND policyname = 'shopping_items_update_own'
  ) THEN
    CREATE POLICY shopping_items_update_own
      ON public.shopping_items
      FOR UPDATE
      TO authenticated
      USING (
        user_id = auth.uid()
        AND EXISTS (
          SELECT 1
          FROM public.shopping_lists AS parent_list
          WHERE parent_list.id = shopping_items.shopping_list_id
            AND parent_list.user_id = auth.uid()
            AND parent_list.user_id = shopping_items.user_id
        )
      )
      WITH CHECK (
        user_id = auth.uid()
        AND EXISTS (
          SELECT 1
          FROM public.shopping_lists AS parent_list
          WHERE parent_list.id = shopping_items.shopping_list_id
            AND parent_list.user_id = auth.uid()
            AND parent_list.user_id = shopping_items.user_id
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'shopping_items'
      AND policyname = 'shopping_items_delete_own'
  ) THEN
    CREATE POLICY shopping_items_delete_own
      ON public.shopping_items
      FOR DELETE
      TO authenticated
      USING (
        user_id = auth.uid()
        AND EXISTS (
          SELECT 1
          FROM public.shopping_lists AS parent_list
          WHERE parent_list.id = shopping_items.shopping_list_id
            AND parent_list.user_id = auth.uid()
            AND parent_list.user_id = shopping_items.user_id
        )
      );
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('shopping_lists', 'shopping_items')
      AND (
        policyname NOT IN (
          'shopping_lists_select_own',
          'shopping_lists_insert_own',
          'shopping_lists_update_own',
          'shopping_lists_delete_own',
          'shopping_items_select_own',
          'shopping_items_insert_own',
          'shopping_items_update_own',
          'shopping_items_delete_own'
        )
        OR roles <> ARRAY['authenticated']::name[]
      )
  ) THEN
    RAISE EXCEPTION
      'Unexpected or non-authenticated policy exists on Shopping List tables';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('shopping_lists', 'shopping_items')
  ) <> 8 THEN
    RAISE EXCEPTION
      'Expected exactly eight Shopping List RLS policies';
  END IF;
END
$migration_005_policies$;

REVOKE ALL PRIVILEGES
  ON TABLE public.shopping_lists, public.shopping_items
  FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON TABLE public.shopping_lists, public.shopping_items
  TO authenticated;

DO $migration_005_conflicts$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_list
    JOIN public.shopping_lists AS target_list
      ON target_list.id = source_list.id
    WHERE source_list.kind = 'shopping'
      AND target_list.user_id <> source_list.user_id
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: an existing shopping_lists ID has a conflicting owner';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS source_item
    JOIN public.projects AS source_list
      ON source_list.id = source_item.project_id
    JOIN public.shopping_items AS target_item
      ON target_item.id = source_item.id
    WHERE source_list.kind = 'shopping'
      AND (
        target_item.user_id <> source_item.user_id
        OR target_item.shopping_list_id <> source_item.project_id
      )
  ) THEN
    RAISE EXCEPTION
      'Backfill aborted: an existing shopping_items ID has a conflicting owner or parent';
  END IF;
END
$migration_005_conflicts$;

INSERT INTO public.shopping_lists (
  id,
  user_id,
  name,
  description,
  shopping_date,
  store_name,
  is_archived,
  created_at,
  updated_at
)
SELECT
  source_list.id,
  source_list.user_id,
  source_list.name,
  COALESCE(source_list.description, ''),
  NULL,
  NULL,
  false,
  COALESCE(source_list.created_at, now()),
  COALESCE(source_list.created_at, now())
FROM public.projects AS source_list
WHERE source_list.kind = 'shopping'
  AND NOT EXISTS (
    SELECT 1
    FROM public.shopping_lists AS target_list
    WHERE target_list.id = source_list.id
  );

WITH source_items AS (
  SELECT
    source_item.*,
    CASE
      WHEN jsonb_typeof(source_item.metadata) = 'object'
        THEN source_item.metadata
      ELSE '{}'::jsonb
    END AS safe_metadata
  FROM public.tasks AS source_item
  JOIN public.projects AS source_list
    ON source_list.id = source_item.project_id
  WHERE source_list.kind = 'shopping'
)
INSERT INTO public.shopping_items (
  id,
  shopping_list_id,
  user_id,
  name,
  quantity_text,
  unit,
  category,
  notes,
  estimated_price,
  actual_price,
  is_purchased,
  priority,
  position,
  is_archived,
  created_at,
  updated_at
)
SELECT
  source_item.id,
  source_item.project_id,
  source_item.user_id,
  source_item.title,
  CASE
    WHEN jsonb_typeof(source_item.safe_metadata -> 'quantity_text')
           IN ('string', 'number')
      THEN source_item.safe_metadata ->> 'quantity_text'
    WHEN jsonb_typeof(source_item.safe_metadata -> 'quantity')
           IN ('string', 'number')
      THEN source_item.safe_metadata ->> 'quantity'
    ELSE ''
  END,
  CASE
    WHEN jsonb_typeof(source_item.safe_metadata -> 'unit') = 'string'
      THEN source_item.safe_metadata ->> 'unit'
    ELSE ''
  END,
  CASE
    WHEN jsonb_typeof(source_item.safe_metadata -> 'category') = 'string'
      AND btrim(source_item.safe_metadata ->> 'category') <> ''
      THEN source_item.safe_metadata ->> 'category'
    ELSE 'Other'
  END,
  COALESCE(source_item.description, ''),
  CASE
    WHEN jsonb_typeof(source_item.safe_metadata -> 'estimated_price')
           IN ('number', 'string')
      AND source_item.safe_metadata ->> 'estimated_price'
            ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
      THEN (source_item.safe_metadata ->> 'estimated_price')::NUMERIC(12, 2)
    ELSE NULL
  END,
  CASE
    WHEN jsonb_typeof(source_item.safe_metadata -> 'actual_price')
           IN ('number', 'string')
      AND source_item.safe_metadata ->> 'actual_price'
            ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
      THEN (source_item.safe_metadata ->> 'actual_price')::NUMERIC(12, 2)
    ELSE NULL
  END,
  COALESCE(
    source_item.completed,
    CASE
      WHEN jsonb_typeof(source_item.safe_metadata -> 'is_purchased') = 'boolean'
        THEN (source_item.safe_metadata ->> 'is_purchased')::BOOLEAN
      WHEN jsonb_typeof(source_item.safe_metadata -> 'purchased') = 'boolean'
        THEN (source_item.safe_metadata ->> 'purchased')::BOOLEAN
      ELSE NULL
    END,
    false
  ),
  CASE
    WHEN source_item.priority IN ('LOW', 'MEDIUM', 'HIGH')
      THEN source_item.priority
    ELSE 'MEDIUM'
  END,
  COALESCE(source_item."order", 0),
  COALESCE(source_item.is_archived, false),
  COALESCE(source_item.created_at, now()),
  COALESCE(
    source_item.updated_at,
    source_item.created_at,
    now()
  )
FROM source_items AS source_item
WHERE NOT EXISTS (
  SELECT 1
  FROM public.shopping_items AS target_item
  WHERE target_item.id = source_item.id
);

DO $migration_005_postflight$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.projects AS source_list
    LEFT JOIN public.shopping_lists AS target_list
      ON target_list.id = source_list.id
     AND target_list.user_id = source_list.user_id
    WHERE source_list.kind = 'shopping'
      AND target_list.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Backfill postflight failed: missing or ownership-mismatched shopping list';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.tasks AS source_item
    JOIN public.projects AS source_list
      ON source_list.id = source_item.project_id
    LEFT JOIN public.shopping_items AS target_item
      ON target_item.id = source_item.id
     AND target_item.shopping_list_id = source_item.project_id
     AND target_item.user_id = source_item.user_id
    WHERE source_list.kind = 'shopping'
      AND target_item.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'Backfill postflight failed: missing, parent-mismatched, or ownership-mismatched shopping item';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects AS recipe_book
    JOIN public.shopping_lists AS target_list
      ON target_list.id = recipe_book.id
    WHERE recipe_book.kind = 'recipes'
  ) OR EXISTS (
    SELECT 1
    FROM public.tasks AS recipe
    JOIN public.projects AS recipe_book
      ON recipe_book.id = recipe.project_id
    JOIN public.shopping_items AS target_item
      ON target_item.id = recipe.id
    WHERE recipe_book.kind = 'recipes'
  ) THEN
    RAISE EXCEPTION
      'Backfill postflight failed: Recipe Book IDs were copied';
  END IF;
END
$migration_005_postflight$;

COMMIT;

-- -------------------------------------------------------------------------
-- REVIEW-ONLY VERIFICATION QUERIES
-- Run separately after an explicitly approved application. Every statement
-- below is SELECT-only and reports identifiers only as aggregate counts.
-- -------------------------------------------------------------------------
/*
-- Source and target counts.
SELECT
  (SELECT count(*) FROM public.projects WHERE kind = 'shopping')
    AS source_list_count,
  (SELECT count(*) FROM public.shopping_lists)
    AS target_list_count,
  (
    SELECT count(*)
    FROM public.tasks AS task_row
    JOIN public.projects AS project_row
      ON project_row.id = task_row.project_id
    WHERE project_row.kind = 'shopping'
  ) AS source_item_count,
  (SELECT count(*) FROM public.shopping_items)
    AS target_item_count;

-- Missing copied IDs, ownership mismatches, and parent mismatches.
SELECT
  count(*) FILTER (WHERE target_list.id IS NULL) AS missing_list_ids,
  count(*) FILTER (
    WHERE target_list.id IS NOT NULL
      AND target_list.user_id <> source_list.user_id
  ) AS list_ownership_mismatches
FROM public.projects AS source_list
LEFT JOIN public.shopping_lists AS target_list
  ON target_list.id = source_list.id
WHERE source_list.kind = 'shopping';

SELECT
  count(*) FILTER (WHERE target_item.id IS NULL) AS missing_item_ids,
  count(*) FILTER (
    WHERE target_item.id IS NOT NULL
      AND target_item.user_id <> source_item.user_id
  ) AS item_ownership_mismatches,
  count(*) FILTER (
    WHERE target_item.id IS NOT NULL
      AND target_item.shopping_list_id <> source_item.project_id
  ) AS item_parent_mismatches
FROM public.tasks AS source_item
JOIN public.projects AS source_list
  ON source_list.id = source_item.project_id
LEFT JOIN public.shopping_items AS target_item
  ON target_item.id = source_item.id
WHERE source_list.kind = 'shopping';

-- Recipe Books must never be copied.
SELECT
  (
    SELECT count(*)
    FROM public.projects AS recipe_book
    JOIN public.shopping_lists AS target_list
      ON target_list.id = recipe_book.id
    WHERE recipe_book.kind = 'recipes'
  ) AS copied_recipe_book_ids,
  (
    SELECT count(*)
    FROM public.tasks AS recipe
    JOIN public.projects AS recipe_book
      ON recipe_book.id = recipe.project_id
    JOIN public.shopping_items AS target_item
      ON target_item.id = recipe.id
    WHERE recipe_book.kind = 'recipes'
  ) AS copied_recipe_ids;

-- Composite ownership FK and cascade definitions. A cross-user item write
-- must be tested only later in an approved rollback-only transaction.
SELECT
  constraint_name,
  pg_get_constraintdef(pg_constraint.oid, true) AS definition
FROM information_schema.table_constraints
JOIN pg_constraint
  ON pg_constraint.conname =
       information_schema.table_constraints.constraint_name
 AND pg_constraint.conrelid =
       (information_schema.table_schema || '.' ||
        information_schema.table_name)::regclass
WHERE information_schema.table_schema = 'public'
  AND information_schema.table_name IN ('shopping_lists', 'shopping_items')
ORDER BY information_schema.table_name, constraint_name;

-- RLS status and exact policy coverage.
SELECT
  relname AS table_name,
  relrowsecurity AS rls_enabled,
  relforcerowsecurity AS rls_forced
FROM pg_class
WHERE oid IN (
  'public.shopping_lists'::regclass,
  'public.shopping_items'::regclass
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
  AND tablename IN ('shopping_lists', 'shopping_items')
ORDER BY tablename, policyname;

-- Grants must be CRUD-only for authenticated and absent for anon.
SELECT
  table_name,
  grantee,
  privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name IN ('shopping_lists', 'shopping_items')
  AND grantee IN ('anon', 'authenticated')
ORDER BY table_name, grantee, privilege_type;

-- Required indexes and triggers.
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('shopping_lists', 'shopping_items')
ORDER BY tablename, indexname;

SELECT
  event_object_table AS table_name,
  trigger_name,
  action_timing,
  event_manipulation
FROM information_schema.triggers
WHERE event_object_schema = 'public'
  AND event_object_table IN ('shopping_lists', 'shopping_items')
ORDER BY event_object_table, trigger_name;

-- Retry verification: these counts must remain zero after a second approved
-- application of migrations 004 and 005.
SELECT
  (
    SELECT count(*)
    FROM public.projects AS source_list
    LEFT JOIN public.shopping_lists AS target_list
      ON target_list.id = source_list.id
    WHERE source_list.kind = 'shopping'
      AND target_list.id IS NULL
  ) AS lists_still_pending,
  (
    SELECT count(*)
    FROM public.tasks AS source_item
    JOIN public.projects AS source_list
      ON source_list.id = source_item.project_id
    LEFT JOIN public.shopping_items AS target_item
      ON target_item.id = source_item.id
    WHERE source_list.kind = 'shopping'
      AND target_item.id IS NULL
  ) AS items_still_pending;
*/

-- Deferred, separate remediation (not changed by this migration):
--   1. Existing projects/tasks grants include excessive privileges.
--   2. Existing task RLS does not validate parent-project ownership.
--   3. Migration 003's due-date index appears absent in production.
--   4. Existing nullable columns differ from frontend assumptions.
--   5. Legacy constraint and index names are cosmetic technical debt.
