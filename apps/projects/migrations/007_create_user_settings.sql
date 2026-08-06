-- Migration 007: Create typed, user-owned organizer settings.
--
-- Prerequisites: migrations 004, 005, and 006 must already be applied.
-- Display names remain in Supabase Auth user_metadata; no profiles table is
-- introduced. Selection IDs intentionally have no foreign keys in this phase:
-- Task Boards still use public.projects, Shopping Lists are transitioning
-- storage, and Recipe Books use dedicated tables. The frontend must validate a
-- saved selection against rows visible to the authenticated user.--
--
-- Deferred frontend preference import:
--   theme
--     -> user_settings.theme
--   yapvibes:organizer:board:<userId>
--     -> user_settings.last_workspace
--   organizer:<userId>:recipe-book-selection
--     -> user_settings.selected_recipe_book_id
-- The bare theme key remains a pre-authentication, device-local bootstrap value
-- even after authenticated settings synchronization is implemented.

BEGIN;

DO $migration_007_preflight$
DECLARE
  mismatch_count INTEGER;
BEGIN
  IF to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'Migration 007 requires auth.users';
  END IF;

  IF to_regclass('public.projects') IS NULL
     OR to_regclass('public.tasks') IS NULL
     OR to_regclass('public.shopping_lists') IS NULL
     OR to_regclass('public.shopping_items') IS NULL
     OR to_regclass('public.recipe_books') IS NULL
     OR to_regclass('public.recipes') IS NULL
     OR to_regclass('public.recipe_ingredients') IS NULL
     OR to_regclass('public.recipe_steps') IS NULL THEN
    RAISE EXCEPTION
      'Migration 007 requires migrations 004, 005, and 006 in order';
  END IF;

  IF to_regprocedure('public.update_updated_at_column()') IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM pg_proc
       WHERE oid = 'public.update_updated_at_column()'::regprocedure
         AND prorettype = 'trigger'::regtype
         AND pronargs = 0
         AND NOT prosecdef
         AND regexp_replace(prosrc, '\s', '', 'g') =
               'BEGINNEW.updated_at=now();RETURNNEW;END;'
     ) THEN
    RAISE EXCEPTION
      'Migration 007 requires compatible public.update_updated_at_column()';
  END IF;

  IF to_regclass('public.user_settings') IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_class AS relation_row
      JOIN pg_namespace AS namespace_row
        ON namespace_row.oid = relation_row.relnamespace
      WHERE namespace_row.nspname = 'public'
        AND relation_row.relname = 'user_settings'
        AND relation_row.relkind = 'r'
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings: expected an ordinary table';
    END IF;

    WITH expected(
      column_name,
      udt_name,
      is_nullable,
      normalized_default
    ) AS (
      VALUES
        ('user_id', 'uuid', 'NO', NULL::TEXT),
        ('theme', 'text', 'NO', '''system''::text'),
        ('default_workspace', 'text', 'NO', '''last''::text'),
        ('last_workspace', 'text', 'NO', '''projects''::text'),
        ('selected_task_board_id', 'uuid', 'YES', NULL::TEXT),
        ('selected_shopping_list_id', 'uuid', 'YES', NULL::TEXT),
        ('selected_recipe_book_id', 'uuid', 'YES', NULL::TEXT),
        ('task_sort_field', 'text', 'NO', '''manual''::text'),
        ('task_sort_direction', 'text', 'NO', '''asc''::text'),
        ('hide_purchased_items', 'bool', 'NO', 'false'),
        ('created_at', 'timestamptz', 'NO', 'now()'),
        ('updated_at', 'timestamptz', 'NO', 'now()')
    ),
    actual AS (
      SELECT
        column_name,
        udt_name,
        is_nullable,
        regexp_replace(lower(column_default), '\s', '', 'g')
          AS normalized_default
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (column_name)
    WHERE expected.column_name IS NULL
       OR actual.column_name IS NULL
       OR expected.udt_name IS DISTINCT FROM actual.udt_name
       OR expected.is_nullable IS DISTINCT FROM actual.is_nullable
       OR expected.normalized_default
            IS DISTINCT FROM actual.normalized_default;

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings column definition(s): % mismatch(es)',
        mismatch_count;
    END IF;

    WITH expected(constraint_name, normalized_definition) AS (
      VALUES
        ('user_settings_pkey', 'primarykey(user_id)'),
        (
          'user_settings_user_id_fkey',
          'foreignkey(user_id)referencesauth.users(id)ondeletecascade'
        ),
        (
          'user_settings_theme_check',
          'check(theme=any(array[''system''::text,''light''::text,''dark''::text]))'
        ),
        (
          'user_settings_default_workspace_check',
          'check(default_workspace=any(array[''last''::text,''projects''::text,''shopping''::text,''recipes''::text]))'
        ),
        (
          'user_settings_last_workspace_check',
          'check(last_workspace=any(array[''projects''::text,''shopping''::text,''recipes''::text]))'
        ),
        (
          'user_settings_task_sort_field_check',
          'check(task_sort_field=any(array[''manual''::text,''duedate''::text,''priority''::text,''createdat''::text,''updatedat''::text,''alphabetical''::text]))'
        ),
        (
          'user_settings_task_sort_direction_check',
          'check(task_sort_direction=any(array[''asc''::text,''desc''::text]))'
        )
    ),
    actual AS (
      SELECT
        conname AS constraint_name,
        regexp_replace(
          lower(pg_get_constraintdef(oid, true)),
          '\s',
          '',
          'g'
        ) AS normalized_definition
      FROM pg_constraint
      WHERE conrelid = 'public.user_settings'::regclass
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (constraint_name)
    WHERE expected.constraint_name IS NULL
       OR actual.constraint_name IS NULL
       OR expected.normalized_definition
            IS DISTINCT FROM actual.normalized_definition;

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings constraint(s): % mismatch(es)',
        mismatch_count;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_trigger
      WHERE tgrelid = 'public.user_settings'::regclass
        AND tgname = 'update_user_settings_updated_at'
        AND NOT tgisinternal
        AND tgenabled <> 'D'
        AND tgfoid = 'public.update_updated_at_column()'::regprocedure
        AND (tgtype & 1) = 1
        AND (tgtype & 2) = 2
        AND (tgtype & 16) = 16
        AND (tgtype & (4 | 8 | 32)) = 0
    ) THEN
      RAISE EXCEPTION
        'Incompatible update_user_settings_updated_at trigger';
    END IF;
    IF (
      SELECT count(*)
      FROM pg_trigger
      WHERE tgrelid = 'public.user_settings'::regclass
        AND NOT tgisinternal
    ) <> 1 OR (
      SELECT count(*)
      FROM pg_index
      WHERE indrelid = 'public.user_settings'::regclass
        AND indisvalid
    ) <> 1 THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings trigger or index set';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_class
      WHERE oid = 'public.user_settings'::regclass
        AND relrowsecurity
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings: RLS is not enabled';
    END IF;

    WITH expected(
      policy_name,
      command,
      using_expression,
      with_check_expression
    ) AS (
      VALUES
        (
          'user_settings_select_own',
          'SELECT',
          '(auth.uid()=user_id)',
          NULL::TEXT
        ),
        (
          'user_settings_insert_own',
          'INSERT',
          NULL::TEXT,
          '(auth.uid()=user_id)'
        ),
        (
          'user_settings_update_own',
          'UPDATE',
          '(auth.uid()=user_id)',
          '(auth.uid()=user_id)'
        )
    ),
    actual AS (
      SELECT
        policyname AS policy_name,
        cmd AS command,
        regexp_replace(qual, '\s', '', 'g') AS using_expression,
        regexp_replace(with_check, '\s', '', 'g')
          AS with_check_expression,
        permissive,
        roles::TEXT AS roles_text
      FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = 'user_settings'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (policy_name)
    WHERE expected.policy_name IS NULL
       OR actual.policy_name IS NULL
       OR expected.command IS DISTINCT FROM actual.command
       OR expected.using_expression
            IS DISTINCT FROM actual.using_expression
       OR expected.with_check_expression
            IS DISTINCT FROM actual.with_check_expression
       OR actual.permissive IS DISTINCT FROM 'PERMISSIVE'
       OR actual.roles_text IS DISTINCT FROM '{authenticated}';

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings RLS policy set: % mismatch(es)',
        mismatch_count;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
        AND grantee IN ('PUBLIC', 'anon')
    ) OR EXISTS (
      SELECT 1
      FROM information_schema.column_privileges
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
        AND grantee IN ('PUBLIC', 'anon')
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.user_settings grants: PUBLIC or anon has privileges';
    END IF;

    WITH expected(column_name, privilege_type) AS (
      SELECT column_name, 'SELECT'
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
      UNION ALL
      SELECT column_name, 'INSERT'
      FROM unnest(ARRAY[
        'user_id',
        'theme',
        'default_workspace',
        'last_workspace',
        'selected_task_board_id',
        'selected_shopping_list_id',
        'selected_recipe_book_id',
        'task_sort_field',
        'task_sort_direction',
        'hide_purchased_items'
      ]) AS insert_column(column_name)
      UNION ALL
      SELECT column_name, 'UPDATE'
      FROM unnest(ARRAY[
        'theme',
        'default_workspace',
        'last_workspace',
        'selected_task_board_id',
        'selected_shopping_list_id',
        'selected_recipe_book_id',
        'task_sort_field',
        'task_sort_direction',
        'hide_purchased_items'
      ]) AS update_column(column_name)
    ),
    actual AS (
      SELECT DISTINCT column_name, privilege_type
      FROM information_schema.column_privileges
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
        AND grantee = 'authenticated'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (column_name, privilege_type)
    WHERE expected.column_name IS NULL
       OR actual.column_name IS NULL;

    IF mismatch_count <> 0 OR (
      SELECT count(*)
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
        AND grantee = 'authenticated'
        AND privilege_type = 'SELECT'
    ) <> 1 OR EXISTS (
      SELECT 1
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'user_settings'
        AND grantee = 'authenticated'
        AND privilege_type <> 'SELECT'
    ) THEN
      RAISE EXCEPTION
        'Incompatible authenticated grants on public.user_settings';
    END IF;
  END IF;
END
$migration_007_preflight$;

DO $migration_007_table$
BEGIN
  IF to_regclass('public.user_settings') IS NULL THEN
    CREATE TABLE public.user_settings (
      user_id UUID NOT NULL,
      theme TEXT NOT NULL DEFAULT 'system',
      default_workspace TEXT NOT NULL DEFAULT 'last',
      last_workspace TEXT NOT NULL DEFAULT 'projects',
      selected_task_board_id UUID,
      selected_shopping_list_id UUID,
      selected_recipe_book_id UUID,
      task_sort_field TEXT NOT NULL DEFAULT 'manual',
      task_sort_direction TEXT NOT NULL DEFAULT 'asc',
      hide_purchased_items BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT user_settings_pkey PRIMARY KEY (user_id),
      CONSTRAINT user_settings_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT user_settings_theme_check
        CHECK (theme IN ('system', 'light', 'dark')),
      CONSTRAINT user_settings_default_workspace_check
        CHECK (
          default_workspace IN ('last', 'projects', 'shopping', 'recipes')
        ),
      CONSTRAINT user_settings_last_workspace_check
        CHECK (last_workspace IN ('projects', 'shopping', 'recipes')),
      CONSTRAINT user_settings_task_sort_field_check
        CHECK (
          task_sort_field IN (
            'manual',
            'dueDate',
            'priority',
            'createdAt',
            'updatedAt',
            'alphabetical'
          )
        ),
      CONSTRAINT user_settings_task_sort_direction_check
        CHECK (task_sort_direction IN ('asc', 'desc'))
    );
  END IF;
END
$migration_007_table$;

DO $migration_007_trigger$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.user_settings'::regclass
      AND tgname = 'update_user_settings_updated_at'
      AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER update_user_settings_updated_at
      BEFORE UPDATE ON public.user_settings
      FOR EACH ROW
      EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END
$migration_007_trigger$;

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;

DO $migration_007_policies$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'user_settings'
      AND policyname = 'user_settings_select_own'
  ) THEN
    CREATE POLICY user_settings_select_own
      ON public.user_settings
      FOR SELECT
      TO authenticated
      USING (auth.uid() = user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'user_settings'
      AND policyname = 'user_settings_insert_own'
  ) THEN
    CREATE POLICY user_settings_insert_own
      ON public.user_settings
      FOR INSERT
      TO authenticated
      WITH CHECK (auth.uid() = user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'user_settings'
      AND policyname = 'user_settings_update_own'
  ) THEN
    CREATE POLICY user_settings_update_own
      ON public.user_settings
      FOR UPDATE
      TO authenticated
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END
$migration_007_policies$;

REVOKE ALL PRIVILEGES
  ON TABLE public.user_settings
  FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES (
  user_id,
  theme,
  default_workspace,
  last_workspace,
  selected_task_board_id,
  selected_shopping_list_id,
  selected_recipe_book_id,
  task_sort_field,
  task_sort_direction,
  hide_purchased_items,
  created_at,
  updated_at
)
  ON TABLE public.user_settings
  FROM PUBLIC, anon, authenticated;

GRANT SELECT
  ON TABLE public.user_settings
  TO authenticated;

GRANT INSERT (
  user_id,
  theme,
  default_workspace,
  last_workspace,
  selected_task_board_id,
  selected_shopping_list_id,
  selected_recipe_book_id,
  task_sort_field,
  task_sort_direction,
  hide_purchased_items
)
  ON TABLE public.user_settings
  TO authenticated;

GRANT UPDATE (
  theme,
  default_workspace,
  last_workspace,
  selected_task_board_id,
  selected_shopping_list_id,
  selected_recipe_book_id,
  task_sort_field,
  task_sort_direction,
  hide_purchased_items
)
  ON TABLE public.user_settings
  TO authenticated;

DO $migration_007_postflight$
DECLARE
  mismatch_count INTEGER;
BEGIN
  WITH expected(
    column_name,
    udt_name,
    is_nullable,
    normalized_default
  ) AS (
    VALUES
      ('user_id', 'uuid', 'NO', NULL::TEXT),
      ('theme', 'text', 'NO', '''system''::text'),
      ('default_workspace', 'text', 'NO', '''last''::text'),
      ('last_workspace', 'text', 'NO', '''projects''::text'),
      ('selected_task_board_id', 'uuid', 'YES', NULL::TEXT),
      ('selected_shopping_list_id', 'uuid', 'YES', NULL::TEXT),
      ('selected_recipe_book_id', 'uuid', 'YES', NULL::TEXT),
      ('task_sort_field', 'text', 'NO', '''manual''::text'),
      ('task_sort_direction', 'text', 'NO', '''asc''::text'),
      ('hide_purchased_items', 'bool', 'NO', 'false'),
      ('created_at', 'timestamptz', 'NO', 'now()'),
      ('updated_at', 'timestamptz', 'NO', 'now()')
  ),
  actual AS (
    SELECT
      column_name,
      udt_name,
      is_nullable,
      regexp_replace(lower(column_default), '\s', '', 'g')
        AS normalized_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
  )
  SELECT count(*)
  INTO mismatch_count
  FROM expected
  FULL JOIN actual USING (column_name)
  WHERE expected.column_name IS NULL
     OR actual.column_name IS NULL
     OR expected.udt_name IS DISTINCT FROM actual.udt_name
     OR expected.is_nullable IS DISTINCT FROM actual.is_nullable
     OR expected.normalized_default
          IS DISTINCT FROM actual.normalized_default;

  IF mismatch_count <> 0 THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: incompatible columns';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.user_settings'::regclass
      AND conname IN (
        'user_settings_pkey',
        'user_settings_user_id_fkey',
        'user_settings_theme_check',
        'user_settings_default_workspace_check',
        'user_settings_last_workspace_check',
        'user_settings_task_sort_field_check',
        'user_settings_task_sort_direction_check'
      )
  ) <> 7 THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: missing constraints';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.user_settings'::regclass
      AND tgname = 'update_user_settings_updated_at'
      AND NOT tgisinternal
      AND tgenabled <> 'D'
      AND tgfoid = 'public.update_updated_at_column()'::regprocedure
      AND (tgtype & 1) = 1
      AND (tgtype & 2) = 2
      AND (tgtype & 16) = 16
      AND (tgtype & (4 | 8 | 32)) = 0
  ) THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: incompatible updated_at trigger';
  END IF;
  IF (
    SELECT count(*)
    FROM pg_trigger
    WHERE tgrelid = 'public.user_settings'::regclass
      AND NOT tgisinternal
  ) <> 1 OR (
    SELECT count(*)
    FROM pg_index
    WHERE indrelid = 'public.user_settings'::regclass
      AND indisvalid
  ) <> 1 THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: unexpected trigger or index';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_class
    WHERE oid = 'public.user_settings'::regclass
      AND relrowsecurity
  ) OR (
    SELECT count(*)
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'user_settings'
      AND roles::TEXT = '{authenticated}'
  ) <> 3 THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: incompatible RLS configuration';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND grantee IN ('PUBLIC', 'anon')
  ) OR EXISTS (
    SELECT 1
    FROM information_schema.column_privileges
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND grantee IN ('PUBLIC', 'anon')
  ) THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: PUBLIC or anon grant detected';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.column_privileges
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND grantee = 'authenticated'
      AND (
        privilege_type IN ('DELETE', 'TRUNCATE', 'TRIGGER', 'REFERENCES')
        OR (
          privilege_type = 'INSERT'
          AND column_name IN ('created_at', 'updated_at')
        )
        OR (
          privilege_type = 'UPDATE'
          AND column_name IN ('user_id', 'created_at', 'updated_at')
        )
      )
  ) THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: prohibited authenticated grant';
  END IF;
  IF (
    SELECT count(*)
    FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'user_settings'
      AND grantee = 'authenticated'
      AND privilege_type = 'SELECT'
  ) <> 1 OR EXISTS (
    SELECT 1
    FROM unnest(ARRAY[
      'user_id',
      'theme',
      'default_workspace',
      'last_workspace',
      'selected_task_board_id',
      'selected_shopping_list_id',
      'selected_recipe_book_id',
      'task_sort_field',
      'task_sort_direction',
      'hide_purchased_items'
    ]) AS required_insert(column_name)
    WHERE NOT has_column_privilege(
      'authenticated',
      'public.user_settings',
      required_insert.column_name,
      'INSERT'
    )
  ) OR EXISTS (
    SELECT 1
    FROM unnest(ARRAY[
      'theme',
      'default_workspace',
      'last_workspace',
      'selected_task_board_id',
      'selected_shopping_list_id',
      'selected_recipe_book_id',
      'task_sort_field',
      'task_sort_direction',
      'hide_purchased_items'
    ]) AS required_update(column_name)
    WHERE NOT has_column_privilege(
      'authenticated',
      'public.user_settings',
      required_update.column_name,
      'UPDATE'
    )
  ) THEN
    RAISE EXCEPTION
      'Migration 007 postflight failed: required authenticated grant missing';
  END IF;
END
$migration_007_postflight$;

COMMIT;

-- SELECT-only review queries (run separately after an approved execution):
--
-- SELECT
--   column_name,
--   data_type,
--   udt_name,
--   is_nullable,
--   column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name = 'user_settings'
-- ORDER BY ordinal_position;
--
-- SELECT
--   conname,
--   contype,
--   pg_get_constraintdef(oid, true) AS definition
-- FROM pg_constraint
-- WHERE conrelid = 'public.user_settings'::regclass
-- ORDER BY conname;
--
-- SELECT
--   policyname,
--   roles,
--   cmd,
--   qual,
--   with_check
-- FROM pg_policies
-- WHERE schemaname = 'public'
--   AND tablename = 'user_settings'
-- ORDER BY policyname;
--
-- SELECT DISTINCT
--   grantee,
--   column_name,
--   privilege_type
-- FROM information_schema.column_privileges
-- WHERE table_schema = 'public'
--   AND table_name = 'user_settings'
--   AND grantee IN ('PUBLIC', 'anon', 'authenticated')
-- ORDER BY grantee, privilege_type, column_name;
