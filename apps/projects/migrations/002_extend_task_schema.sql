-- ============================================================
-- Migration: Extend tasks table with new fields
-- Date: 2026-07-14
-- Purpose: Add status, priority, due_date, is_pinned, is_archived, updated_at
-- ============================================================

BEGIN;

-- -----------------------------------------------------------
-- Status field (TEXT + CHECK constraint instead of ENUM)
-- Default: 'TODO' for all existing rows
-- Rationale: TEXT allows easier future schema evolution
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN status TEXT NOT NULL DEFAULT 'TODO';

ALTER TABLE tasks 
  ADD CONSTRAINT tasks_status_check 
  CHECK (status IN ('TODO', 'IN_PROGRESS', 'COMPLETED'));

-- -----------------------------------------------------------
-- Priority field (TEXT + CHECK constraint)
-- Default: 'MEDIUM' for all existing rows
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN priority TEXT NOT NULL DEFAULT 'MEDIUM';

ALTER TABLE tasks 
  ADD CONSTRAINT tasks_priority_check 
  CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH'));

-- -----------------------------------------------------------
-- Due date field (timestamp with timezone)
-- Nullable, default NULL (existing tasks have no due date)
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN due_date TIMESTAMPTZ;

-- -----------------------------------------------------------
-- Pin flag
-- Default: false for all existing rows
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT FALSE;

-- -----------------------------------------------------------
-- Archive flag
-- Default: false for all existing rows
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE;

-- -----------------------------------------------------------
-- Updated timestamp with auto-update trigger
-- Defaults to created_at for existing rows initially
-- -----------------------------------------------------------
ALTER TABLE tasks 
  ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Set existing rows' updated_at to their created_at
UPDATE tasks SET updated_at = created_at WHERE updated_at IS NULL;

-- Create trigger function to auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Attach trigger to tasks table
DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;
CREATE TRIGGER update_tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

COMMIT;
