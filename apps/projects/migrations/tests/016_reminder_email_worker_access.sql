-- Controlled validation for migration 016. This test makes no fixture data and
-- can be run as one rollback-only transaction after migration 016.

BEGIN;

DO $test$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'Migration 016 requires PostgreSQL role service_role';
  ELSIF NOT has_function_privilege('service_role', 'public.claim_reminder_email_deliveries(integer,timestamptz)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'public.complete_reminder_email_delivery(uuid,uuid,text)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'public.record_reminder_email_delivery_failure(uuid,uuid,boolean,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'service_role cannot execute all reminder email worker RPCs';
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
    RAISE EXCEPTION 'PUBLIC, anon, or authenticated can execute a reminder email worker RPC';
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
    RAISE EXCEPTION 'Reminder email worker RPC security settings changed';
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
    RAISE EXCEPTION 'Browser reminder_deliveries access or policy is present';
  END IF;
END
$test$;

ROLLBACK;
