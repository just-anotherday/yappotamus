-- Migration 024: allow traditional Light and Dark appearance presets.
BEGIN;
ALTER TABLE public.user_settings DROP CONSTRAINT IF EXISTS user_settings_theme_check;
ALTER TABLE public.user_settings
  ADD CONSTRAINT user_settings_theme_check
  CHECK (theme IN ('light', 'dark', 'forest', 'midnight', 'sunset'));
COMMIT;
