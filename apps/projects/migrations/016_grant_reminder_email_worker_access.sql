-- Migration 016: authorize only the private reminder-email worker RPCs for a
-- future trusted service_role worker. This migration grants no table access.

BEGIN;

DO $migration_016_preflight$
BEGIN
  IF to_regprocedure('public.claim_reminder_email_deliveries(integer,timestamp with time zone)') IS NULL
     OR to_regprocedure('public.complete_reminder_email_delivery(uuid,uuid,text)') IS NULL
     OR to_regprocedure('public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 016 requires the three Migration 013 reminder email worker RPCs';
  ELSIF to_regclass('public.reminder_deliveries') IS NULL THEN
    RAISE EXCEPTION 'Migration 016 requires public.reminder_deliveries';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.reminder_deliveries'::regclass AND relrowsecurity
  ) THEN
    RAISE EXCEPTION 'Migration 016 requires RLS enabled on public.reminder_deliveries';
  ELSIF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'Migration 016 requires PostgreSQL role service_role';
  ELSIF (
    SELECT count(*)
    FROM pg_proc
    WHERE oid IN (
      'public.claim_reminder_email_deliveries(integer,timestamptz)'::regprocedure,
      'public.complete_reminder_email_delivery(uuid,uuid,text)'::regprocedure,
      'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)'::regprocedure
    )
      AND prosecdef
      AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) <> 3 THEN
    RAISE EXCEPTION 'Migration 016 requires SECURITY DEFINER worker RPCs with search_path=pg_catalog';
  END IF;
END
$migration_016_preflight$;

REVOKE EXECUTE ON FUNCTION public.claim_reminder_email_deliveries(INTEGER, TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.complete_reminder_email_delivery(UUID, UUID, TEXT)
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.record_reminder_email_delivery_failure(UUID, UUID, BOOLEAN, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.claim_reminder_email_deliveries(INTEGER, TIMESTAMPTZ)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_reminder_email_delivery(UUID, UUID, TEXT)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.record_reminder_email_delivery_failure(UUID, UUID, BOOLEAN, TEXT)
  TO service_role;

DO $migration_016_postflight$
BEGIN
  IF NOT has_function_privilege('service_role', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 016 postflight failed: service_role worker RPC grants missing';
  ELSIF EXISTS (
    SELECT 1
    FROM pg_proc AS procedure_row
    CROSS JOIN LATERAL aclexplode(coalesce(procedure_row.proacl, acldefault('f', procedure_row.proowner))) AS privilege_row
    WHERE procedure_row.oid IN (
      'public.claim_reminder_email_deliveries(integer,timestamptz)'::regprocedure,
      'public.complete_reminder_email_delivery(uuid,uuid,text)'::regprocedure,
      'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)'::regprocedure
    )
      AND privilege_row.grantee = 0
      AND privilege_row.privilege_type = 'EXECUTE'
  ) OR has_function_privilege('anon', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('anon', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 016 postflight failed: browser or PUBLIC worker RPC execute access present';
  ELSIF (
    SELECT count(*)
    FROM pg_proc
    WHERE oid IN (
      'public.claim_reminder_email_deliveries(integer,timestamptz)'::regprocedure,
      'public.complete_reminder_email_delivery(uuid,uuid,text)'::regprocedure,
      'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)'::regprocedure
    )
      AND prosecdef
      AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) <> 3 THEN
    RAISE EXCEPTION 'Migration 016 postflight failed: worker RPC security settings changed';
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = 'public.reminder_deliveries'::regclass AND relrowsecurity
  ) OR EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reminder_deliveries'
  ) OR has_table_privilege('anon', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('anon', 'public.reminder_deliveries', 'DELETE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'SELECT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'INSERT')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.reminder_deliveries', 'DELETE') THEN
    RAISE EXCEPTION 'Migration 016 postflight failed: reminder delivery browser table boundary changed';
  END IF;
END
$migration_016_postflight$;

COMMIT;
