-- Migration 009: Add archive lifecycle while preserving immutable notification content.
-- Active and archived feeds use separate partial indexes; unread counts exclude archived rows.

BEGIN;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_active_user_created_at
  ON public.notifications (user_id, created_at DESC, id DESC)
  WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_archived_user_created_at
  ON public.notifications (user_id, created_at DESC, id DESC)
  WHERE archived_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_active_unread
  ON public.notifications (user_id, created_at DESC, id DESC)
  WHERE is_read = false AND archived_at IS NULL;

REVOKE ALL PRIVILEGES (archived_at)
  ON TABLE public.notifications
  FROM PUBLIC, anon, authenticated;

GRANT UPDATE (archived_at)
  ON TABLE public.notifications
  TO authenticated;

REVOKE DELETE
  ON TABLE public.notifications
  FROM PUBLIC, anon;

GRANT DELETE
  ON TABLE public.notifications
  TO authenticated;

DROP POLICY IF EXISTS notifications_delete_archived_own
  ON public.notifications;

CREATE POLICY notifications_delete_archived_own
  ON public.notifications
  FOR DELETE
  TO authenticated
  USING (
    auth.uid() = user_id
    AND archived_at IS NOT NULL
  );

COMMIT;

-- Browser clients retain SELECT on their own rows, UPDATE only on is_read and
-- archived_at, and DELETE only on their own archived rows. read_at remains
-- trigger-owned because it is not granted to authenticated users.
