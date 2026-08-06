-- Migration 008: Create immutable-content, user-owned notifications.
--
-- Prerequisite: migration 007 must already be applied.
-- Browser clients may select their own notifications and update only is_read.
-- Notification creation, deletion, content changes, reminder generators,
-- retention, email delivery, and browser push are deliberately out of scope.
-- Supabase Realtime publication setup is deferred to the frontend notification
-- phase so publication state can be reviewed explicitly before it is changed.

BEGIN;

DO $migration_008_preflight$
DECLARE
  mismatch_count INTEGER;
  normalized_function_body TEXT;
BEGIN
  IF to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'Migration 008 requires auth.users';
  END IF;

  IF to_regclass('public.user_settings') IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM pg_class
       WHERE oid = 'public.user_settings'::regclass
         AND relkind = 'r'
         AND relrowsecurity
     )
     OR (
       SELECT count(*)
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_settings'
     ) <> 12
     OR (
       SELECT count(*)
       FROM pg_policies
       WHERE schemaname = 'public'
         AND tablename = 'user_settings'
         AND roles::TEXT = '{authenticated}'
     ) <> 3 THEN
    RAISE EXCEPTION
      'Migration 008 requires a verified migration 007 user_settings table';
  END IF;

  IF to_regprocedure('public.sync_notification_read_at()') IS NOT NULL THEN
    SELECT regexp_replace(prosrc, '\s', '', 'g')
    INTO normalized_function_body
    FROM pg_proc
    WHERE oid = 'public.sync_notification_read_at()'::regprocedure
      AND prorettype = 'trigger'::regtype
      AND pronargs = 0
      AND NOT prosecdef
      AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[];

    IF normalized_function_body IS DISTINCT FROM
      'BEGINIFNEW.is_readTHENIFTG_OP=''INSERT''OROLD.is_readISDISTINCTFROMtrueTHENNEW.read_at:=clock_timestamp();ELSIFNEW.read_atISNULLTHENNEW.read_at:=OLD.read_at;ENDIF;ELSENEW.read_at:=NULL;ENDIF;RETURNNEW;END;'
    THEN
      RAISE EXCEPTION
        'Incompatible public.sync_notification_read_at()';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM information_schema.routine_privileges
      WHERE routine_schema = 'public'
        AND routine_name = 'sync_notification_read_at'
        AND grantee IN ('PUBLIC', 'anon', 'authenticated')
    ) THEN
      RAISE EXCEPTION
        'Incompatible sync_notification_read_at() execute grants';
    END IF;
  END IF;

  IF to_regclass('public.notifications') IS NULL
     AND (
       to_regclass('public.idx_notifications_user_created_at') IS NOT NULL
       OR to_regclass('public.idx_notifications_unread') IS NOT NULL
       OR to_regclass('public.idx_notifications_entity') IS NOT NULL
       OR to_regclass('public.idx_notifications_user_dedupe_key') IS NOT NULL
     ) THEN
    RAISE EXCEPTION
      'Migration 008 found a notification index name on an incompatible relation';
  END IF;

  IF to_regclass('public.notifications') IS NOT NULL THEN
    IF to_regprocedure('public.sync_notification_read_at()') IS NULL THEN
      RAISE EXCEPTION
        'Incompatible public.notifications: read-state function is missing';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_class
      WHERE oid = 'public.notifications'::regclass
        AND relkind = 'r'
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.notifications: expected an ordinary table';
    END IF;

    WITH expected(
      column_name,
      udt_name,
      is_nullable,
      normalized_default
    ) AS (
      VALUES
        ('id', 'uuid', 'NO', 'gen_random_uuid()'),
        ('user_id', 'uuid', 'NO', NULL::TEXT),
        ('type', 'text', 'NO', NULL::TEXT),
        ('title', 'text', 'NO', NULL::TEXT),
        ('message', 'text', 'NO', NULL::TEXT),
        ('workspace', 'text', 'YES', NULL::TEXT),
        ('entity_type', 'text', 'YES', NULL::TEXT),
        ('entity_id', 'uuid', 'YES', NULL::TEXT),
        ('metadata', 'jsonb', 'NO', '''{}''::jsonb'),
        ('dedupe_key', 'text', 'YES', NULL::TEXT),
        ('is_read', 'bool', 'NO', 'false'),
        ('read_at', 'timestamptz', 'YES', NULL::TEXT),
        ('expires_at', 'timestamptz', 'YES', NULL::TEXT),
        ('created_at', 'timestamptz', 'NO', 'now()')
    ),
    actual AS (
      SELECT
        column_name,
        udt_name,
        is_nullable,
        regexp_replace(lower(column_default), '\s', '', 'g')
          AS normalized_default
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (column_name)
    WHERE expected.column_name IS NULL
       OR actual.column_name IS NULL
       OR expected.udt_name IS DISTINCT FROM actual.udt_name
       OR expected.is_nullable IS DISTINCT FROM actual.is_nullable
       OR expected.normalized_default
            IS DISTINCT FROM actual.normalized_default;

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.notifications column definition(s): % mismatch(es)',
        mismatch_count;
    END IF;

    WITH expected(constraint_name, normalized_definition) AS (
      VALUES
        ('notifications_pkey', 'primarykey(id)'),
        (
          'notifications_user_id_fkey',
          'foreignkey(user_id)referencesauth.users(id)ondeletecascade'
        ),
        (
          'notifications_type_check',
          'check(type=any(array[''system_message''::text,''task_due_soon''::text,''task_overdue''::text,''shopping_date_upcoming''::text]))'
        ),
        (
          'notifications_workspace_check',
          'check(workspaceisnullorworkspace=any(array[''projects''::text,''shopping''::text,''recipes''::text]))'
        ),
        (
          'notifications_entity_type_check',
          'check(entity_typeisnullorentity_type=any(array[''task''::text,''shopping_list''::text,''recipe''::text]))'
        ),
        (
          'notifications_entity_pair_check',
          'check(entity_typeisnullandentity_idisnullorentity_typeisnotnullandentity_idisnotnull)'
        ),
        (
          'notifications_title_length_check',
          'check(char_length(btrim(title))>=1andchar_length(btrim(title))<=160)'
        ),
        (
          'notifications_message_length_check',
          'check(char_length(btrim(message))>=1andchar_length(btrim(message))<=2000)'
        ),
        (
          'notifications_dedupe_key_length_check',
          'check(dedupe_keyisnullorchar_length(btrim(dedupe_key))>=1andchar_length(btrim(dedupe_key))<=500)'
        ),
        (
          'notifications_metadata_object_check',
          'check(jsonb_typeof(metadata)=''object''::text)'
        ),
        (
          'notifications_read_state_check',
          'check(notis_readandread_atisnulloris_readandread_atisnotnull)'
        ),
        (
          'notifications_expiry_check',
          'check(expires_atisnullorexpires_at>created_at)'
        )
    ),
    actual AS (
      SELECT
        conname AS constraint_name,
        regexp_replace(
          lower(pg_get_constraintdef(oid, true)),
          '\s',
          '',
          'g'
        ) AS normalized_definition
      FROM pg_constraint
      WHERE conrelid = 'public.notifications'::regclass
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (constraint_name)
    WHERE expected.constraint_name IS NULL
       OR actual.constraint_name IS NULL
       OR expected.normalized_definition
            IS DISTINCT FROM actual.normalized_definition;

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.notifications constraint(s): % mismatch(es)',
        mismatch_count;
    END IF;

    WITH expected(index_name, normalized_definition) AS (
      VALUES
        (
          'idx_notifications_user_created_at',
          'createindexidx_notifications_user_created_atonpublic.notificationsusingbtree(user_id,created_atdesc,iddesc)'
        ),
        (
          'idx_notifications_unread',
          'createindexidx_notifications_unreadonpublic.notificationsusingbtree(user_id,created_atdesc,iddesc)where(is_read=false)'
        ),
        (
          'idx_notifications_entity',
          'createindexidx_notifications_entityonpublic.notificationsusingbtree(user_id,entity_type,entity_id)where((entity_typeisnotnull)and(entity_idisnotnull))'
        ),
        (
          'idx_notifications_user_dedupe_key',
          'createuniqueindexidx_notifications_user_dedupe_keyonpublic.notificationsusingbtree(user_id,dedupe_key)where(dedupe_keyisnotnull)'
        )
    ),
    actual AS (
      SELECT
        index_row.relname AS index_name,
        regexp_replace(
          lower(pg_get_indexdef(index_row.oid)),
          '\s',
          '',
          'g'
        ) AS normalized_definition
      FROM pg_class AS index_row
      JOIN pg_index AS index_metadata
        ON index_metadata.indexrelid = index_row.oid
      WHERE index_metadata.indrelid = 'public.notifications'::regclass
        AND index_row.relname IN (
          'idx_notifications_user_created_at',
          'idx_notifications_unread',
          'idx_notifications_entity',
          'idx_notifications_user_dedupe_key'
        )
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (index_name)
    WHERE expected.index_name IS NULL
       OR actual.index_name IS NULL
       OR expected.normalized_definition
            IS DISTINCT FROM actual.normalized_definition;

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.notifications index(es): % mismatch(es)',
        mismatch_count;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_trigger AS trigger_row
      JOIN pg_attribute AS read_column
        ON read_column.attrelid = trigger_row.tgrelid
       AND read_column.attname = 'is_read'
       AND NOT read_column.attisdropped
      WHERE trigger_row.tgrelid = 'public.notifications'::regclass
        AND trigger_row.tgname = 'sync_notifications_read_at'
        AND NOT trigger_row.tgisinternal
        AND trigger_row.tgenabled <> 'D'
        AND trigger_row.tgfoid =
              'public.sync_notification_read_at()'::regprocedure
        AND (trigger_row.tgtype & 1) = 1
        AND (trigger_row.tgtype & 2) = 2
        AND (trigger_row.tgtype & 4) = 4
        AND (trigger_row.tgtype & 16) = 16
        AND (trigger_row.tgtype & (8 | 32)) = 0
        AND trigger_row.tgattr::TEXT = read_column.attnum::TEXT
    ) THEN
      RAISE EXCEPTION
        'Incompatible sync_notifications_read_at trigger';
    END IF;
    IF (
      SELECT count(*)
      FROM pg_trigger
      WHERE tgrelid = 'public.notifications'::regclass
        AND NOT tgisinternal
    ) <> 1 OR (
      SELECT count(*)
      FROM pg_index
      WHERE indrelid = 'public.notifications'::regclass
        AND indisvalid
    ) <> 5 THEN
      RAISE EXCEPTION
        'Incompatible public.notifications trigger or index set';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_class
      WHERE oid = 'public.notifications'::regclass
        AND relrowsecurity
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.notifications: RLS is not enabled';
    END IF;

    WITH expected(
      policy_name,
      command,
      using_expression,
      with_check_expression
    ) AS (
      VALUES
        (
          'notifications_select_own',
          'SELECT',
          '(auth.uid()=user_id)',
          NULL::TEXT
        ),
        (
          'notifications_update_read_state_own',
          'UPDATE',
          '(auth.uid()=user_id)',
          '(auth.uid()=user_id)'
        )
    ),
    actual AS (
      SELECT
        policyname AS policy_name,
        cmd AS command,
        regexp_replace(qual, '\s', '', 'g') AS using_expression,
        regexp_replace(with_check, '\s', '', 'g')
          AS with_check_expression,
        permissive,
        roles::TEXT AS roles_text
      FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = 'notifications'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (policy_name)
    WHERE expected.policy_name IS NULL
       OR actual.policy_name IS NULL
       OR expected.command IS DISTINCT FROM actual.command
       OR expected.using_expression
            IS DISTINCT FROM actual.using_expression
       OR expected.with_check_expression
            IS DISTINCT FROM actual.with_check_expression
       OR actual.permissive IS DISTINCT FROM 'PERMISSIVE'
       OR actual.roles_text IS DISTINCT FROM '{authenticated}';

    IF mismatch_count <> 0 THEN
      RAISE EXCEPTION
        'Incompatible public.notifications RLS policy set: % mismatch(es)',
        mismatch_count;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
        AND grantee IN ('PUBLIC', 'anon')
    ) OR EXISTS (
      SELECT 1
      FROM information_schema.column_privileges
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
        AND grantee IN ('PUBLIC', 'anon')
    ) THEN
      RAISE EXCEPTION
        'Incompatible public.notifications grants: PUBLIC or anon has privileges';
    END IF;

    WITH expected(column_name, privilege_type) AS (
      SELECT column_name, 'SELECT'
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
      UNION ALL
      VALUES ('is_read', 'UPDATE')
    ),
    actual AS (
      SELECT DISTINCT column_name, privilege_type
      FROM information_schema.column_privileges
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
        AND grantee = 'authenticated'
    )
    SELECT count(*)
    INTO mismatch_count
    FROM expected
    FULL JOIN actual USING (column_name, privilege_type)
    WHERE expected.column_name IS NULL
       OR actual.column_name IS NULL;

    IF mismatch_count <> 0 OR (
      SELECT count(*)
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
        AND grantee = 'authenticated'
        AND privilege_type = 'SELECT'
    ) <> 1 OR EXISTS (
      SELECT 1
      FROM information_schema.table_privileges
      WHERE table_schema = 'public'
        AND table_name = 'notifications'
        AND grantee = 'authenticated'
        AND privilege_type <> 'SELECT'
    ) THEN
      RAISE EXCEPTION
        'Incompatible authenticated grants on public.notifications';
    END IF;
  END IF;
END
$migration_008_preflight$;

DO $migration_008_table$
BEGIN
  IF to_regclass('public.notifications') IS NULL THEN
    CREATE TABLE public.notifications (
      id UUID NOT NULL DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL,
      type TEXT NOT NULL,
      title TEXT NOT NULL,
      message TEXT NOT NULL,
      workspace TEXT,
      entity_type TEXT,
      entity_id UUID,
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      dedupe_key TEXT,
      is_read BOOLEAN NOT NULL DEFAULT false,
      read_at TIMESTAMPTZ,
      expires_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT notifications_pkey PRIMARY KEY (id),
      CONSTRAINT notifications_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES auth.users (id)
        ON DELETE CASCADE,
      CONSTRAINT notifications_type_check
        CHECK (
          type IN (
            'system_message',
            'task_due_soon',
            'task_overdue',
            'shopping_date_upcoming'
          )
        ),
      CONSTRAINT notifications_workspace_check
        CHECK (
          workspace IS NULL
          OR workspace IN ('projects', 'shopping', 'recipes')
        ),
      CONSTRAINT notifications_entity_type_check
        CHECK (
          entity_type IS NULL
          OR entity_type IN ('task', 'shopping_list', 'recipe')
        ),
      CONSTRAINT notifications_entity_pair_check
        CHECK (
          (
            entity_type IS NULL
            AND entity_id IS NULL
          )
          OR (
            entity_type IS NOT NULL
            AND entity_id IS NOT NULL
          )
        ),
      CONSTRAINT notifications_title_length_check
        CHECK (
          char_length(btrim(title)) BETWEEN 1 AND 160
        ),
      CONSTRAINT notifications_message_length_check
        CHECK (
          char_length(btrim(message)) BETWEEN 1 AND 2000
        ),
      CONSTRAINT notifications_dedupe_key_length_check
        CHECK (
          dedupe_key IS NULL
          OR char_length(btrim(dedupe_key)) BETWEEN 1 AND 500
        ),
      CONSTRAINT notifications_metadata_object_check
        CHECK (jsonb_typeof(metadata) = 'object'),
      CONSTRAINT notifications_read_state_check
        CHECK (
          (
            NOT is_read
            AND read_at IS NULL
          )
          OR (
            is_read
            AND read_at IS NOT NULL
          )
        ),
      CONSTRAINT notifications_expiry_check
        CHECK (
          expires_at IS NULL
          OR expires_at > created_at
        )
    );
  END IF;
END
$migration_008_table$;

DO $migration_008_function$
BEGIN
  IF to_regprocedure('public.sync_notification_read_at()') IS NULL THEN
    EXECUTE $create_function$
      CREATE FUNCTION public.sync_notification_read_at()
      RETURNS TRIGGER
      LANGUAGE plpgsql
      SECURITY INVOKER
      SET search_path = pg_catalog
      AS $function_body$
      BEGIN
        IF NEW.is_read THEN
          IF TG_OP = 'INSERT'
             OR OLD.is_read IS DISTINCT FROM true THEN
            NEW.read_at := clock_timestamp();
          ELSIF NEW.read_at IS NULL THEN
            NEW.read_at := OLD.read_at;
          END IF;
        ELSE
          NEW.read_at := NULL;
        END IF;

        RETURN NEW;
      END;
      $function_body$;
    $create_function$;
  END IF;
END
$migration_008_function$;

REVOKE ALL PRIVILEGES
  ON FUNCTION public.sync_notification_read_at()
  FROM PUBLIC, anon, authenticated;

DO $migration_008_trigger$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.notifications'::regclass
      AND tgname = 'sync_notifications_read_at'
      AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER sync_notifications_read_at
      BEFORE INSERT OR UPDATE OF is_read
      ON public.notifications
      FOR EACH ROW
      EXECUTE FUNCTION public.sync_notification_read_at();
  END IF;
END
$migration_008_trigger$;

DO $migration_008_indexes$
BEGIN
  IF to_regclass('public.idx_notifications_user_created_at') IS NULL THEN
    CREATE INDEX idx_notifications_user_created_at
      ON public.notifications (user_id, created_at DESC, id DESC);
  END IF;

  IF to_regclass('public.idx_notifications_unread') IS NULL THEN
    CREATE INDEX idx_notifications_unread
      ON public.notifications (user_id, created_at DESC, id DESC)
      WHERE is_read = false;
  END IF;

  IF to_regclass('public.idx_notifications_entity') IS NULL THEN
    CREATE INDEX idx_notifications_entity
      ON public.notifications (user_id, entity_type, entity_id)
      WHERE entity_type IS NOT NULL
        AND entity_id IS NOT NULL;
  END IF;

  IF to_regclass('public.idx_notifications_user_dedupe_key') IS NULL THEN
    CREATE UNIQUE INDEX idx_notifications_user_dedupe_key
      ON public.notifications (user_id, dedupe_key)
      WHERE dedupe_key IS NOT NULL;
  END IF;
END
$migration_008_indexes$;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

DO $migration_008_policies$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'notifications'
      AND policyname = 'notifications_select_own'
  ) THEN
    CREATE POLICY notifications_select_own
      ON public.notifications
      FOR SELECT
      TO authenticated
      USING (auth.uid() = user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'notifications'
      AND policyname = 'notifications_update_read_state_own'
  ) THEN
    CREATE POLICY notifications_update_read_state_own
      ON public.notifications
      FOR UPDATE
      TO authenticated
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END
$migration_008_policies$;

REVOKE ALL PRIVILEGES
  ON TABLE public.notifications
  FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES (
  id,
  user_id,
  type,
  title,
  message,
  workspace,
  entity_type,
  entity_id,
  metadata,
  dedupe_key,
  is_read,
  read_at,
  expires_at,
  created_at
)
  ON TABLE public.notifications
  FROM PUBLIC, anon, authenticated;

GRANT SELECT
  ON TABLE public.notifications
  TO authenticated;

GRANT UPDATE (is_read)
  ON TABLE public.notifications
  TO authenticated;

DO $migration_008_postflight$
DECLARE
  mismatch_count INTEGER;
BEGIN
  IF (
    SELECT count(*)
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
  ) <> 14 OR (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname IN (
        'notifications_pkey',
        'notifications_user_id_fkey',
        'notifications_type_check',
        'notifications_workspace_check',
        'notifications_entity_type_check',
        'notifications_entity_pair_check',
        'notifications_title_length_check',
        'notifications_message_length_check',
        'notifications_dedupe_key_length_check',
        'notifications_metadata_object_check',
        'notifications_read_state_check',
        'notifications_expiry_check'
      )
  ) <> 12 THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: columns or constraints missing';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_index AS index_metadata
    JOIN pg_class AS index_row
      ON index_row.oid = index_metadata.indexrelid
    WHERE index_metadata.indrelid = 'public.notifications'::regclass
      AND index_row.relname IN (
        'idx_notifications_user_created_at',
        'idx_notifications_unread',
        'idx_notifications_entity',
        'idx_notifications_user_dedupe_key'
      )
      AND index_metadata.indisvalid
  ) <> 4 THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: indexes missing or invalid';
  END IF;
  IF (
    SELECT count(*)
    FROM pg_index
    WHERE indrelid = 'public.notifications'::regclass
      AND indisvalid
  ) <> 5 OR (
    SELECT count(*)
    FROM pg_trigger
    WHERE tgrelid = 'public.notifications'::regclass
      AND NOT tgisinternal
  ) <> 1 THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: unexpected index or trigger';
  END IF;

  IF to_regprocedure('public.sync_notification_read_at()') IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM pg_trigger
       WHERE tgrelid = 'public.notifications'::regclass
         AND tgname = 'sync_notifications_read_at'
         AND NOT tgisinternal
         AND tgenabled <> 'D'
     ) THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: read-state function or trigger missing';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM information_schema.routine_privileges
    WHERE routine_schema = 'public'
      AND routine_name = 'sync_notification_read_at'
      AND grantee IN ('PUBLIC', 'anon', 'authenticated')
  ) THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: browser function execute grant detected';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_class
    WHERE oid = 'public.notifications'::regclass
      AND relrowsecurity
  ) OR (
    SELECT count(*)
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'notifications'
      AND roles::TEXT = '{authenticated}'
  ) <> 2 THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: incompatible RLS configuration';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
      AND grantee IN ('PUBLIC', 'anon')
  ) OR EXISTS (
    SELECT 1
    FROM information_schema.column_privileges
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
      AND grantee IN ('PUBLIC', 'anon')
  ) THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: PUBLIC or anon grant detected';
  END IF;

  WITH expected(column_name, privilege_type) AS (
    SELECT column_name, 'SELECT'
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
    UNION ALL
    VALUES ('is_read', 'UPDATE')
  ),
  actual AS (
    SELECT DISTINCT column_name, privilege_type
    FROM information_schema.column_privileges
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
      AND grantee = 'authenticated'
  )
  SELECT count(*)
  INTO mismatch_count
  FROM expected
  FULL JOIN actual USING (column_name, privilege_type)
  WHERE expected.column_name IS NULL
     OR actual.column_name IS NULL;

  IF mismatch_count <> 0 OR EXISTS (
    SELECT 1
    FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
      AND grantee = 'authenticated'
      AND privilege_type <> 'SELECT'
  ) THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: incompatible authenticated grants';
  END IF;
  IF (
    SELECT count(*)
    FROM information_schema.table_privileges
    WHERE table_schema = 'public'
      AND table_name = 'notifications'
      AND grantee = 'authenticated'
      AND privilege_type = 'SELECT'
  ) <> 1 THEN
    RAISE EXCEPTION
      'Migration 008 postflight failed: authenticated SELECT grant missing';
  END IF;
END
$migration_008_postflight$;

COMMIT;

-- SELECT-only review queries (run separately after an approved execution):
--
-- SELECT
--   column_name,
--   data_type,
--   udt_name,
--   is_nullable,
--   column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name = 'notifications'
-- ORDER BY ordinal_position;
--
-- SELECT
--   conname,
--   contype,
--   pg_get_constraintdef(oid, true) AS definition
-- FROM pg_constraint
-- WHERE conrelid = 'public.notifications'::regclass
-- ORDER BY conname;
--
-- SELECT
--   indexname,
--   indexdef
-- FROM pg_indexes
-- WHERE schemaname = 'public'
--   AND tablename = 'notifications'
-- ORDER BY indexname;
--
-- SELECT
--   policyname,
--   roles,
--   cmd,
--   qual,
--   with_check
-- FROM pg_policies
-- WHERE schemaname = 'public'
--   AND tablename = 'notifications'
-- ORDER BY policyname;
--
-- SELECT DISTINCT
--   grantee,
--   column_name,
--   privilege_type
-- FROM information_schema.column_privileges
-- WHERE table_schema = 'public'
--   AND table_name = 'notifications'
--   AND grantee IN ('PUBLIC', 'anon', 'authenticated')
-- ORDER BY grantee, privilege_type, column_name;
--
-- Realtime publication is intentionally unchanged by this migration.
-- Reminder generation, expiry cleanup, email, and browser push remain deferred.-- Task reminder generation is blocked until tasks.due_date TIMESTAMPTZ is
-- explicitly defined as an exact moment, a user-local calendar date, or a
-- timezone-normalized deadline.
