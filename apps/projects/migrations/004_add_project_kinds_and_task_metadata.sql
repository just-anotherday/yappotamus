-- Migration 004: Add project workspace types and structured task metadata.
--
-- Existing projects become Task Boards. This migration is deliberately
-- retry-safe, but it refuses to accept incompatible pre-existing objects.

BEGIN;

DO $migration_004$
DECLARE
  constraint_definition TEXT;
  normalized_definition TEXT;
  user_kind_index_oid OID;
BEGIN
  IF to_regclass('public.projects') IS NULL THEN
    RAISE EXCEPTION 'Migration 004 requires public.projects';
  END IF;

  IF to_regclass('public.tasks') IS NULL THEN
    RAISE EXCEPTION 'Migration 004 requires public.tasks';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'projects'
      AND column_name = 'kind'
  ) AND NOT EXISTS (
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
      'Incompatible public.projects.kind: expected TEXT NOT NULL DEFAULT ''board''';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'metadata'
  ) AND NOT EXISTS (
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
      'Incompatible public.tasks.metadata: expected JSONB NOT NULL DEFAULT empty object';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'projects_kind_check'
      AND conrelid <> 'public.projects'::regclass
  ) THEN
    RAISE EXCEPTION
      'Constraint projects_kind_check already exists on a different table';
  END IF;

  SELECT pg_get_constraintdef(oid, true)
  INTO constraint_definition
  FROM pg_constraint
  WHERE conname = 'projects_kind_check'
    AND conrelid = 'public.projects'::regclass;

  IF constraint_definition IS NOT NULL THEN
    normalized_definition :=
      regexp_replace(lower(constraint_definition), '\s', '', 'g');

    IF normalized_definition NOT IN (
      'check(kind=any(array[''board''::text,''shopping''::text,''recipes''::text]))',
      'check((kind=any(array[''board''::text,''shopping''::text,''recipes''::text])))',
      'check(kindin(''board''::text,''shopping''::text,''recipes''::text))',
      'check((kindin(''board''::text,''shopping''::text,''recipes''::text)))'
    ) THEN
      RAISE EXCEPTION
        'Incompatible projects_kind_check definition: %',
        constraint_definition;
    END IF;
  ELSIF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.projects'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid, true) ~* '\mkind\M'
  ) THEN
    RAISE EXCEPTION
      'A differently named kind check already exists on public.projects; review it before migration 004';
  END IF;

  user_kind_index_oid :=
    to_regclass('public.idx_projects_user_kind');

  IF user_kind_index_oid IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
       FROM pg_index AS index_row
       WHERE index_row.indexrelid = user_kind_index_oid
         AND index_row.indrelid = 'public.projects'::regclass
         AND index_row.indisvalid
         AND NOT index_row.indisunique
         AND index_row.indpred IS NULL
         AND index_row.indexprs IS NULL
         AND regexp_replace(
               lower(pg_get_indexdef(index_row.indexrelid)),
               '\s',
               '',
               'g'
             ) LIKE '%onpublic.projectsusingbtree(user_id,kind)'
     ) THEN
    RAISE EXCEPTION
      'Incompatible public.idx_projects_user_kind index already exists';
  END IF;
END
$migration_004$;

ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'board';

DO $migration_004$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'projects_kind_check'
      AND conrelid = 'public.projects'::regclass
  ) THEN
    ALTER TABLE public.projects
      ADD CONSTRAINT projects_kind_check
      CHECK (kind IN ('board', 'shopping', 'recipes'));
  END IF;
END
$migration_004$;

ALTER TABLE public.tasks
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_projects_user_kind
  ON public.projects (user_id, kind);

DO $migration_004$
DECLARE
  constraint_definition TEXT;
  normalized_definition TEXT;
BEGIN
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
    RAISE EXCEPTION 'Migration 004 postflight failed for public.projects.kind';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.projects
    WHERE kind IS NULL
       OR kind NOT IN ('board', 'shopping', 'recipes')
  ) THEN
    RAISE EXCEPTION 'Migration 004 found an invalid public.projects.kind value';
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
    RAISE EXCEPTION 'Migration 004 postflight failed for public.tasks.metadata';
  END IF;

  SELECT pg_get_constraintdef(oid, true)
  INTO constraint_definition
  FROM pg_constraint
  WHERE conname = 'projects_kind_check'
    AND conrelid = 'public.projects'::regclass
    AND contype = 'c';

  normalized_definition :=
    regexp_replace(lower(constraint_definition), '\s', '', 'g');

  IF normalized_definition NOT IN (
    'check(kind=any(array[''board''::text,''shopping''::text,''recipes''::text]))',
    'check((kind=any(array[''board''::text,''shopping''::text,''recipes''::text])))',
    'check(kindin(''board''::text,''shopping''::text,''recipes''::text))',
    'check((kindin(''board''::text,''shopping''::text,''recipes''::text)))'
  ) THEN
    RAISE EXCEPTION
      'Migration 004 postflight failed for projects_kind_check: %',
      constraint_definition;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_index AS index_row
    WHERE index_row.indexrelid = 'public.idx_projects_user_kind'::regclass
      AND index_row.indrelid = 'public.projects'::regclass
      AND index_row.indisvalid
      AND NOT index_row.indisunique
      AND index_row.indpred IS NULL
      AND index_row.indexprs IS NULL
      AND regexp_replace(
            lower(pg_get_indexdef(index_row.indexrelid)),
            '\s',
            '',
            'g'
          ) LIKE '%onpublic.projectsusingbtree(user_id,kind)'
  ) THEN
    RAISE EXCEPTION
      'Migration 004 postflight failed for public.idx_projects_user_kind';
  END IF;
END
$migration_004$;

COMMIT;
