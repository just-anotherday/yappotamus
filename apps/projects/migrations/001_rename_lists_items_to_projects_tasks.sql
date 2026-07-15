-- ============================================================
-- Migration: Rename lists → projects, items → tasks
-- Date: 2026-07-14
-- Purpose: Structural rename only. No feature changes.
-- ============================================================

BEGIN;

-- -----------------------------------------------------------
-- Step 1: Drop existing foreign key constraint
-- PostgreSQL requires dropping FKs before renaming referenced tables
-- -----------------------------------------------------------
ALTER TABLE items DROP CONSTRAINT items_list_id_fkey;

-- -----------------------------------------------------------
-- Step 2: Rename tables
-- -----------------------------------------------------------
ALTER TABLE lists RENAME TO projects;
ALTER TABLE items RENAME TO tasks;

-- -----------------------------------------------------------
-- Step 3: Rename column list_id → project_id in tasks table
-- -----------------------------------------------------------
ALTER TABLE tasks RENAME COLUMN list_id TO project_id;

-- -----------------------------------------------------------
-- Step 4: Recreate foreign key constraint with updated names
-- -----------------------------------------------------------
ALTER TABLE tasks
  ADD CONSTRAINT tasks_project_id_fkey
  FOREIGN KEY (project_id) REFERENCES projects (id)
  ON DELETE CASCADE;

-- -----------------------------------------------------------
-- Step 5: Rename indexes to reflect new table names
-- -----------------------------------------------------------
ALTER INDEX lists_pkey RENAME TO projects_pkey;
ALTER INDEX lists_user_id_idx RENAME TO projects_user_id_idx;
ALTER INDEX items_pkey RENAME TO tasks_pkey;
ALTER INDEX items_user_id_idx RENAME TO tasks_user_id_idx;

COMMIT;
