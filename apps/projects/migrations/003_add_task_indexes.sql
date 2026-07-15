-- Migration 003: Add indexes for task queries
-- Created: 2026-07-14
-- Purpose: Improve query performance for upcoming search/filter/sort features

-- Due date index (required for Phase 2 Search due date filtering)
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);

-- Rollback SQL:
-- DROP INDEX IF EXISTS idx_tasks_due_date;
