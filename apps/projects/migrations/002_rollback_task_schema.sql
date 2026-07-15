-- ============================================================
-- Rollback: Remove extended task schema fields
-- Date: 2026-07-14
-- Purpose: Revert tasks table to original schema
-- ============================================================

BEGIN;

-- Remove the updated_at trigger
DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Drop CHECK constraints
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_priority_check;

-- Drop the added columns
ALTER TABLE tasks DROP COLUMN IF EXISTS status;
ALTER TABLE tasks DROP COLUMN IF EXISTS priority;
ALTER TABLE tasks DROP COLUMN IF EXISTS due_date;
ALTER TABLE tasks DROP COLUMN IF EXISTS is_pinned;
ALTER TABLE tasks DROP COLUMN IF EXISTS is_archived;
ALTER TABLE tasks DROP COLUMN IF EXISTS updated_at;

COMMIT;
