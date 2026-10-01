-- Fresh Supabase database baseline for the historical Projects migrations.
-- Run ONLY when lists, items, projects, and tasks are all absent. This creates
-- the legacy schema expected by migration 001; migrations 001-025 remain
-- unchanged for databases where they have already been applied.

BEGIN;

DO $fresh_baseline_preflight$
BEGIN
  IF to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'Fresh baseline requires a Supabase database with auth.users';
  END IF;
  IF to_regclass('public.lists') IS NOT NULL
     OR to_regclass('public.items') IS NOT NULL
     OR to_regclass('public.projects') IS NOT NULL
     OR to_regclass('public.tasks') IS NOT NULL THEN
    RAISE EXCEPTION 'Fresh baseline is only for an empty Projects schema';
  END IF;
END
$fresh_baseline_preflight$;

CREATE TABLE public.lists (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  list_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  completed BOOLEAN NOT NULL DEFAULT false,
  "order" INTEGER NOT NULL DEFAULT 0,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT items_list_id_fkey
    FOREIGN KEY (list_id) REFERENCES public.lists(id) ON DELETE CASCADE
);

CREATE INDEX lists_user_id_idx ON public.lists(user_id);
CREATE INDEX items_user_id_idx ON public.items(user_id);

ALTER TABLE public.lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;

CREATE POLICY lists_select_own ON public.lists FOR SELECT TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY lists_insert_own ON public.lists FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY lists_update_own ON public.lists FOR UPDATE TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY lists_delete_own ON public.lists FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY items_select_own ON public.items FOR SELECT TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY items_insert_own ON public.items FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY items_update_own ON public.items FOR UPDATE TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY items_delete_own ON public.items FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

REVOKE ALL PRIVILEGES ON public.lists, public.items FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.lists, public.items TO authenticated;

DO $fresh_baseline_realtime$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.lists, public.items;
  END IF;
END
$fresh_baseline_realtime$;

COMMIT;
