-- Rollback 004: Remove project workspace types and structured task metadata

BEGIN;

DROP INDEX IF EXISTS idx_projects_user_kind;

ALTER TABLE tasks
  DROP COLUMN IF EXISTS metadata;

ALTER TABLE projects
  DROP CONSTRAINT IF EXISTS projects_kind_check;

ALTER TABLE projects
  DROP COLUMN IF EXISTS kind;

COMMIT;
