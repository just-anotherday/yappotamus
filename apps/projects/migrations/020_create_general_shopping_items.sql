-- Migration 020: add canonical user-owned General Grocery items.
-- General items intentionally belong to neither projects nor shopping stores.

BEGIN;

DO $migration_020_preflight$
BEGIN
  IF to_regclass('public.general_shopping_items') IS NOT NULL THEN
    RAISE EXCEPTION 'Migration 020 found an existing public.general_shopping_items table';
  ELSIF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
    RAISE EXCEPTION 'Migration 020 requires public.update_updated_at_column()';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'
  ) THEN
    RAISE EXCEPTION 'Migration 020 requires the existing supabase_realtime publication';
  END IF;
END
$migration_020_preflight$;

CREATE TABLE public.general_shopping_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  quantity TEXT NOT NULL DEFAULT '',
  unit TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'Other',
  completed BOOLEAN NOT NULL DEFAULT false,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT general_shopping_items_title_not_blank_check
    CHECK (btrim(title) <> ''),
  CONSTRAINT general_shopping_items_sort_order_check
    CHECK (sort_order >= 0)
);

CREATE INDEX idx_general_shopping_items_user_order
  ON public.general_shopping_items (user_id, sort_order, created_at, id);

CREATE TRIGGER update_general_shopping_items_updated_at
  BEFORE UPDATE ON public.general_shopping_items
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.general_shopping_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY general_shopping_items_select_own
  ON public.general_shopping_items FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY general_shopping_items_insert_own
  ON public.general_shopping_items FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY general_shopping_items_update_own
  ON public.general_shopping_items FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY general_shopping_items_delete_own
  ON public.general_shopping_items FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

REVOKE ALL PRIVILEGES ON TABLE public.general_shopping_items FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.general_shopping_items TO authenticated;

DO $migration_020_realtime$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication AS publication
    WHERE publication.pubname = 'supabase_realtime'
      AND (
        publication.puballtables
        OR EXISTS (
          SELECT 1 FROM pg_publication_rel AS publication_relation
          WHERE publication_relation.prpubid = publication.oid
            AND publication_relation.prrelid = 'public.general_shopping_items'::regclass
        )
      )
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.general_shopping_items;
  END IF;
END
$migration_020_realtime$;

DO $migration_020_postflight$
DECLARE
  title_constraint TEXT;
  sort_constraint TEXT;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.general_shopping_items'::regclass
      AND relkind = 'r' AND relrowsecurity
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General table or RLS is missing';
  ELSIF (
    SELECT count(*) FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
  ) <> 10 OR EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name IN ('project_id', 'shopping_store_id', 'task_id')
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General table column shape is incorrect';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name IN ('title', 'quantity', 'unit', 'category')
      AND udt_name = 'text' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'completed' AND udt_name = 'bool' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'sort_order' AND udt_name = 'int4' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name IN ('created_at', 'updated_at')
      AND udt_name = 'timestamptz' AND is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General column type or nullability mismatch';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'id' AND column_default LIKE '%gen_random_uuid()%'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'quantity' AND column_default = '''''::text'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'unit' AND column_default = '''''::text'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'category' AND column_default = '''Other''::text'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'completed' AND lower(column_default) IN ('false', 'false::boolean')
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name = 'sort_order' AND column_default = '0'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'general_shopping_items'
      AND column_name IN ('created_at', 'updated_at') AND column_default LIKE 'now()%'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General defaults are incorrect';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.general_shopping_items'::regclass
      AND conname = 'general_shopping_items_pkey' AND contype = 'p'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.general_shopping_items'::regclass
      AND conname = 'general_shopping_items_user_id_fkey' AND contype = 'f'
      AND confrelid = 'auth.users'::regclass AND confdeltype = 'c'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General primary key or owner cascade is missing';
  END IF;

  SELECT regexp_replace(lower(pg_get_constraintdef(oid, true)), '\s+', '', 'g')
    INTO title_constraint
  FROM pg_constraint
  WHERE conrelid = 'public.general_shopping_items'::regclass
    AND conname = 'general_shopping_items_title_not_blank_check';
  SELECT regexp_replace(lower(pg_get_constraintdef(oid, true)), '\s+', '', 'g')
    INTO sort_constraint
  FROM pg_constraint
  WHERE conrelid = 'public.general_shopping_items'::regclass
    AND conname = 'general_shopping_items_sort_order_check';
  IF title_constraint NOT LIKE '%btrim(title)<>''''%'
     OR sort_constraint NOT LIKE '%sort_order>=0%' THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General checks are incorrect';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_index AS index_row
    JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
    WHERE index_class.relnamespace = 'public'::regnamespace
      AND index_class.relname = 'idx_general_shopping_items_user_order'
      AND index_row.indnkeyatts = 4 AND index_row.indpred IS NULL
      AND pg_get_indexdef(index_row.indexrelid, 1, true) = 'user_id'
      AND pg_get_indexdef(index_row.indexrelid, 2, true) = 'sort_order'
      AND pg_get_indexdef(index_row.indexrelid, 3, true) = 'created_at'
      AND pg_get_indexdef(index_row.indexrelid, 4, true) = 'id'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General ordering index is missing';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.general_shopping_items'::regclass
      AND tgname = 'update_general_shopping_items_updated_at'
      AND NOT tgisinternal AND tgenabled = 'O'
      AND pg_get_triggerdef(oid, true) LIKE '%EXECUTE FUNCTION update_updated_at_column()%'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General updated_at trigger is missing';
  ELSIF (
    SELECT count(*) FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'general_shopping_items'
      AND policyname IN (
        'general_shopping_items_select_own', 'general_shopping_items_insert_own',
        'general_shopping_items_update_own', 'general_shopping_items_delete_own'
      )
      AND roles = ARRAY['authenticated']::name[]
  ) <> 4 THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General ownership policies are missing';
  ELSIF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'general_shopping_items'
      AND policyname = 'general_shopping_items_select_own'
      AND regexp_replace(lower(coalesce(qual, '')), '\s+', '', 'g') NOT LIKE '%auth.uid()=user_id%'
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'general_shopping_items'
      AND policyname = 'general_shopping_items_insert_own'
      AND regexp_replace(lower(coalesce(with_check, '')), '\s+', '', 'g') NOT LIKE '%auth.uid()=user_id%'
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'general_shopping_items'
      AND policyname = 'general_shopping_items_update_own'
      AND (
        regexp_replace(lower(coalesce(qual, '')), '\s+', '', 'g') NOT LIKE '%auth.uid()=user_id%'
        OR regexp_replace(lower(coalesce(with_check, '')), '\s+', '', 'g') NOT LIKE '%auth.uid()=user_id%'
      )
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'general_shopping_items'
      AND policyname = 'general_shopping_items_delete_own'
      AND regexp_replace(lower(coalesce(qual, '')), '\s+', '', 'g') NOT LIKE '%auth.uid()=user_id%'
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General policy ownership predicates are incorrect';
  ELSIF has_table_privilege('anon', 'public.general_shopping_items', 'SELECT')
     OR NOT has_table_privilege('authenticated', 'public.general_shopping_items', 'SELECT, INSERT, UPDATE, DELETE') THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General table grants are incorrect';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_publication AS publication
    WHERE publication.pubname = 'supabase_realtime'
      AND (
        publication.puballtables
        OR EXISTS (
          SELECT 1 FROM pg_publication_rel AS publication_relation
          WHERE publication_relation.prpubid = publication.oid
            AND publication_relation.prrelid = 'public.general_shopping_items'::regclass
        )
      )
  ) THEN
    RAISE EXCEPTION 'Migration 020 postflight failed: General table is not published to Realtime';
  END IF;
END
$migration_020_postflight$;

COMMIT;
