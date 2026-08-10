-- Migration 018: add user-owned stores to the active projects/tasks Shopping model.
-- The legacy shopping_lists/shopping_items tables remain intentionally unused.

BEGIN;

DO $migration_018_preflight$
BEGIN
  IF to_regclass('public.shopping_stores') IS NOT NULL THEN
    RAISE EXCEPTION 'Migration 018 found an existing public.shopping_stores table';
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'shopping_store_id'
  ) THEN
    RAISE EXCEPTION 'Migration 018 found an existing public.tasks.shopping_store_id column';
  ELSIF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
    RAISE EXCEPTION 'Migration 018 requires public.update_updated_at_column()';
  ELSIF to_regclass('public.projects') IS NULL OR to_regclass('public.tasks') IS NULL THEN
    RAISE EXCEPTION 'Migration 018 requires public.projects and public.tasks';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.projects'::regclass
      AND contype = 'u'
      AND pg_get_constraintdef(oid, true) = 'UNIQUE (id, user_id)'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.tasks'::regclass
      AND contype = 'u'
      AND pg_get_constraintdef(oid, true) = 'UNIQUE (id, user_id)'
  ) THEN
    RAISE EXCEPTION 'Migration 018 requires UNIQUE (id, user_id) on public.projects and public.tasks';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'Migration 018 requires public.tasks.user_id UUID NOT NULL';
  END IF;
END
$migration_018_preflight$;

CREATE TABLE public.shopping_stores (
  id UUID DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT shopping_stores_pkey
    PRIMARY KEY (id),
  CONSTRAINT shopping_stores_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT shopping_stores_name_length_check
    CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
  CONSTRAINT shopping_stores_sort_order_check
    CHECK (sort_order >= 0),
  CONSTRAINT shopping_stores_id_user_id_key
    UNIQUE (id, user_id)
);

CREATE UNIQUE INDEX shopping_stores_user_normalized_name_key
  ON public.shopping_stores (user_id, lower(btrim(name)));

CREATE INDEX idx_shopping_stores_user_order
  ON public.shopping_stores (user_id, sort_order, name, id);

CREATE TRIGGER update_shopping_stores_updated_at
  BEFORE UPDATE ON public.shopping_stores
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.shopping_stores ENABLE ROW LEVEL SECURITY;

CREATE POLICY shopping_stores_select_own
  ON public.shopping_stores FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY shopping_stores_insert_own
  ON public.shopping_stores FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY shopping_stores_update_own
  ON public.shopping_stores FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY shopping_stores_delete_own
  ON public.shopping_stores FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

REVOKE ALL PRIVILEGES ON TABLE public.shopping_stores FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shopping_stores TO authenticated;

ALTER TABLE public.tasks
  ADD COLUMN shopping_store_id UUID NULL;

ALTER TABLE public.tasks
  ADD CONSTRAINT tasks_shopping_store_owner_fkey
  FOREIGN KEY (shopping_store_id, user_id)
  REFERENCES public.shopping_stores (id, user_id)
  ON DELETE SET NULL (shopping_store_id);

CREATE INDEX idx_tasks_shopping_store_grouping
  ON public.tasks (project_id, shopping_store_id, "order", created_at, id);

DO $migration_018_postflight$
DECLARE
  store_id_attnum SMALLINT;
  store_user_id_attnum SMALLINT;
  task_store_id_attnum SMALLINT;
  task_user_id_attnum SMALLINT;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.shopping_stores'::regclass
      AND relkind = 'r' AND relrowsecurity
  ) THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: shopping_stores RLS is not enabled';
  ELSIF (
    SELECT count(*) FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'shopping_stores'
  ) <> 6 THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: shopping_stores column count mismatch';
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
  ) <> 5 OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.shopping_stores'::regclass
      AND conname = 'shopping_stores_user_id_fkey'
      AND confrelid = 'auth.users'::regclass AND confdeltype = 'c'
  ) THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: shopping_stores constraints mismatch';
  ELSIF (
    SELECT count(*) FROM pg_class
    WHERE relkind = 'i'
      AND relnamespace = 'public'::regnamespace
      AND relname IN (
        'shopping_stores_pkey',
        'shopping_stores_id_user_id_key',
        'shopping_stores_user_normalized_name_key',
        'idx_shopping_stores_user_order'
      )
  ) <> 4 OR (
    SELECT count(*) FROM pg_index AS index_row
    JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
    WHERE index_class.relname = 'shopping_stores_user_normalized_name_key'
      AND index_class.relnamespace = 'public'::regnamespace
      AND index_row.indisunique AND index_row.indnkeyatts = 2
      AND index_row.indpred IS NULL
      AND pg_get_indexdef(index_row.indexrelid, 1, true) = 'user_id'
      AND pg_get_indexdef(index_row.indexrelid, 2, true) = 'lower(btrim(name))'
  ) <> 1 OR (
    SELECT count(*) FROM pg_index AS index_row
    JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
    WHERE index_class.relname = 'idx_shopping_stores_user_order'
      AND index_class.relnamespace = 'public'::regnamespace
      AND index_row.indnkeyatts = 4 AND index_row.indpred IS NULL
      AND pg_get_indexdef(index_row.indexrelid, 1, true) = 'user_id'
      AND pg_get_indexdef(index_row.indexrelid, 2, true) = 'sort_order'
      AND pg_get_indexdef(index_row.indexrelid, 3, true) = 'name'
      AND pg_get_indexdef(index_row.indexrelid, 4, true) = 'id'
  ) <> 1 THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: shopping_stores constraints or indexes mismatch';
  ELSIF (
    SELECT count(*) FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'shopping_stores'
      AND policyname IN (
        'shopping_stores_select_own', 'shopping_stores_insert_own',
        'shopping_stores_update_own', 'shopping_stores_delete_own'
      )
      AND roles = ARRAY['authenticated']::name[]
  ) <> 4 THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: shopping_stores policies mismatch';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.shopping_stores'::regclass
      AND tgname = 'update_shopping_stores_updated_at'
      AND NOT tgisinternal
      AND pg_get_triggerdef(oid, true) LIKE '%EXECUTE FUNCTION update_updated_at_column()%'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'shopping_store_id' AND udt_name = 'uuid' AND is_nullable = 'YES'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_index AS index_row
    JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
    WHERE index_class.relname = 'idx_tasks_shopping_store_grouping'
      AND index_class.relnamespace = 'public'::regnamespace
      AND index_row.indnkeyatts = 5 AND index_row.indpred IS NULL
      AND pg_get_indexdef(index_row.indexrelid, 1, true) = 'project_id'
      AND pg_get_indexdef(index_row.indexrelid, 2, true) = 'shopping_store_id'
      AND pg_get_indexdef(index_row.indexrelid, 3, true) = '"order"'
      AND pg_get_indexdef(index_row.indexrelid, 4, true) = 'created_at'
      AND pg_get_indexdef(index_row.indexrelid, 5, true) = 'id'
  ) THEN
    RAISE EXCEPTION 'Migration 018 postflight failed: task assignment column, trigger, or index mismatch';
  END IF;

  SELECT attnum INTO store_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.shopping_stores'::regclass AND attname = 'id' AND NOT attisdropped;
  SELECT attnum INTO store_user_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.shopping_stores'::regclass AND attname = 'user_id' AND NOT attisdropped;
  SELECT attnum INTO task_store_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.tasks'::regclass AND attname = 'shopping_store_id' AND NOT attisdropped;
  SELECT attnum INTO task_user_id_attnum FROM pg_attribute
  WHERE attrelid = 'public.tasks'::regclass AND attname = 'user_id' AND NOT attisdropped;

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
    RAISE EXCEPTION 'Migration 018 postflight failed: owner-safe targeted task store FK mismatch';
  END IF;
END
$migration_018_postflight$;

COMMIT;
