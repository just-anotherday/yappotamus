-- Migration 004: Add project workspace types and structured task metadata
-- Existing projects remain task boards. Shopping items and recipes continue
-- to inherit the existing projects/tasks ownership and RLS policies.

BEGIN;

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'board';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'projects_kind_check'
      AND conrelid = 'projects'::regclass
  ) THEN
    ALTER TABLE projects
      ADD CONSTRAINT projects_kind_check
      CHECK (kind IN ('board', 'shopping', 'recipes'));
  END IF;
END
$$;

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_projects_user_kind
  ON projects(user_id, kind);

COMMIT;
