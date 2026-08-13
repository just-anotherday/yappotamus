-- Migration 022: replace legacy light/dark/system preferences with named palettes.

BEGIN;

ALTER TABLE public.user_settings
  DROP CONSTRAINT IF EXISTS user_settings_theme_check;

UPDATE public.user_settings
SET theme = 'forest'
WHERE theme NOT IN ('forest', 'midnight', 'sunset');

ALTER TABLE public.user_settings
  ALTER COLUMN theme SET DEFAULT 'forest',
  ADD CONSTRAINT user_settings_theme_check
    CHECK (theme IN ('forest', 'midnight', 'sunset'));

COMMIT;
