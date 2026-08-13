-- Migration 023: persist structured per-user appearance preferences.
BEGIN;
ALTER TABLE public.user_settings
  ADD COLUMN IF NOT EXISTS appearance JSONB NULL;

ALTER TABLE public.user_settings
  ADD CONSTRAINT user_settings_appearance_object_check
  CHECK (appearance IS NULL OR jsonb_typeof(appearance) = 'object');

REVOKE ALL PRIVILEGES (appearance) ON TABLE public.user_settings FROM PUBLIC, anon, authenticated;
GRANT INSERT (appearance) ON TABLE public.user_settings TO authenticated;
GRANT UPDATE (appearance) ON TABLE public.user_settings TO authenticated;
COMMIT;
