-- Migration 021: persist user-wide Shopping category exclusions.

BEGIN;

DO $migration_021_preflight$
DECLARE
  column_type TEXT;
  column_nullable TEXT;
  column_default TEXT;
BEGIN
  IF to_regclass('public.user_settings') IS NULL THEN
    RAISE EXCEPTION 'Migration 021 requires public.user_settings';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_class WHERE oid = 'public.user_settings'::regclass AND relkind = 'r'
  ) OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.user_settings'::regclass) THEN
    RAISE EXCEPTION 'Migration 021 requires an RLS-enabled public.user_settings table';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'selected_shopping_list_id' AND udt_name = 'uuid'
  ) THEN
    RAISE EXCEPTION 'Migration 021 requires the existing Shopping-list settings column';
  END IF;

  SELECT column_row.udt_name, column_row.is_nullable, column_row.column_default
    INTO column_type, column_nullable, column_default
  FROM information_schema.columns AS column_row
  WHERE column_row.table_schema = 'public' AND column_row.table_name = 'user_settings'
    AND column_row.column_name = 'hidden_shopping_categories';

  IF column_type IS NOT NULL AND (
    column_type <> '_text' OR column_nullable <> 'YES' OR column_default IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Migration 021 found incompatible hidden_shopping_categories column';
  END IF;
END
$migration_021_preflight$;

ALTER TABLE public.user_settings
  ADD COLUMN IF NOT EXISTS hidden_shopping_categories TEXT[] NULL;

REVOKE ALL PRIVILEGES (hidden_shopping_categories)
  ON TABLE public.user_settings
  FROM PUBLIC, anon, authenticated;

GRANT INSERT (hidden_shopping_categories)
  ON TABLE public.user_settings
  TO authenticated;

GRANT UPDATE (hidden_shopping_categories)
  ON TABLE public.user_settings
  TO authenticated;

DO $migration_021_postflight$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'hidden_shopping_categories'
      AND udt_name = '_text' AND is_nullable = 'YES' AND column_default IS NULL
  ) THEN
    RAISE EXCEPTION 'Migration 021 postflight failed: hidden category preference column is incorrect';
  ELSIF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.user_settings'::regclass) THEN
    RAISE EXCEPTION 'Migration 021 postflight failed: user settings RLS is disabled';
  ELSIF NOT has_column_privilege('authenticated', 'public.user_settings', 'hidden_shopping_categories', 'INSERT')
     OR NOT has_column_privilege('authenticated', 'public.user_settings', 'hidden_shopping_categories', 'UPDATE') THEN
    RAISE EXCEPTION 'Migration 021 postflight failed: hidden category preference grants are missing';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'user_settings'
      AND column_name = 'selected_shopping_list_id' AND udt_name = 'uuid'
  ) THEN
    RAISE EXCEPTION 'Migration 021 postflight failed: existing settings schema changed';
  END IF;
END
$migration_021_postflight$;

COMMIT;
