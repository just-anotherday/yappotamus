-- ============================================================
-- Rollback: Rename projects → lists, tasks → items
-- Date: 2026-07-14
-- Purpose: Restore original table/column names if migration fails
-- ============================================================

BEGIN;

-- -----------------------------------------------------------
-- Step 1: Drop existing foreign key constraint
-- -----------------------------------------------------------
ALTER TABLE tasks DROP CONSTRAINT tasks_project_id_fkey;

-- -----------------------------------------------------------
-- Step 2: Rename column project_id → list_id in tasks table
-- -----------------------------------------------------------
ALTER TABLE tasks RENAME COLUMN project_id TO list_id;

-- -----------------------------------------------------------
-- Step 3: Rename tables back to original names
-- -----------------------------------------------------------
ALTER TABLE projects RENAME TO lists;
ALTER TABLE tasks RENAME TO items;

-- -----------------------------------------------------------
-- Step 4: Recreate foreign key constraint with original names
-- -----------------------------------------------------------
ALTER TABLE items
  ADD CONSTRAINT items_list_id_fkey
  FOREIGN KEY (list_id) REFERENCES lists (id)
  ON DELETE CASCADE;

-- -----------------------------------------------------------
-- Step 5: Rename indexes back to original names
-- -----------------------------------------------------------
ALTER INDEX projects_pkey RENAME TO lists_pkey;
ALTER INDEX projects_user_id_idx RENAME TO lists_user_id_idx;
ALTER INDEX tasks_pkey RENAME TO items_pkey;
ALTER INDEX tasks_user_id_idx RENAME TO items_user_id_idx;

COMMIT;
