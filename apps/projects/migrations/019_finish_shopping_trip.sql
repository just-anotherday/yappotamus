-- Migration 019: atomically finish one store-scoped shopping trip.
--
-- A trip is UI state only. This migration intentionally adds no tables,
-- columns, history, schedules, or reminder behavior.

BEGIN;

DO $migration_019_preflight$
DECLARE
  v_existing_function_oid OID := to_regprocedure('public.finish_shopping_trip(uuid,uuid)');
  v_named_function_count INTEGER;
BEGIN
  IF to_regclass('public.projects') IS NULL
     OR to_regclass('public.tasks') IS NULL
     OR to_regclass('public.shopping_stores') IS NULL THEN
    RAISE EXCEPTION 'Migration 019 requires projects, tasks, and shopping_stores';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'projects'
      AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'projects'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'projects'
      AND column_name = 'kind' AND udt_name = 'text' AND is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'Migration 019 requires projects id/user_id UUID NOT NULL and kind TEXT NOT NULL';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'project_id' AND udt_name = 'uuid'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'shopping_store_id' AND udt_name = 'uuid' AND is_nullable = 'YES'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tasks'
      AND column_name = 'completed' AND udt_name = 'bool'
  ) THEN
    -- Legacy task rows may allow a NULL completion value. The final predicate
    -- uses `completed IS TRUE`, so NULL rows are safely retained.
    RAISE EXCEPTION 'Migration 019 requires task ownership, project, nullable store, and boolean completion columns';
  ELSIF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'shopping_stores'
      AND column_name = 'id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'shopping_stores'
      AND column_name = 'user_id' AND udt_name = 'uuid' AND is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'Migration 019 requires shopping_stores id and user_id UUID NOT NULL';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.tasks'::regclass
      AND conname = 'tasks_shopping_store_owner_fkey'
      AND contype = 'f'
      AND confrelid = 'public.shopping_stores'::regclass
  ) THEN
    RAISE EXCEPTION 'Migration 019 requires the G1 owner-safe task store foreign key';
  END IF;

  SELECT count(*) INTO v_named_function_count
  FROM pg_proc
  WHERE pronamespace = 'public'::regnamespace
    AND proname = 'finish_shopping_trip';

  IF v_named_function_count > 0 AND v_existing_function_oid IS NULL THEN
    RAISE EXCEPTION 'Migration 019 found an incompatible public.finish_shopping_trip overload';
  ELSIF v_existing_function_oid IS NOT NULL AND (
    v_named_function_count <> 1
    OR NOT EXISTS (
      SELECT 1
      FROM pg_proc AS procedure_row
      JOIN pg_language AS language_row ON language_row.oid = procedure_row.prolang
      WHERE procedure_row.oid = v_existing_function_oid
        AND procedure_row.prorettype = 'integer'::regtype
        AND procedure_row.pronargs = 2
        AND procedure_row.proargtypes = ARRAY['uuid'::regtype::oid, 'uuid'::regtype::oid]::OIDVECTOR
        AND language_row.lanname = 'plpgsql'
        AND procedure_row.prosecdef
        AND procedure_row.proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
        AND pg_get_userbyid(procedure_row.proowner) = current_user
        -- This token check is deliberately whitespace-insensitive. It accepts
        -- the verified earlier `= true` body and the canonical `IS TRUE` body,
        -- while rejecting a same-signature function without the G2 boundary.
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%auth.uid()%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%frompublic.projectsasproject_row%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%project_row.user_id=v_user_id%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%project_row.kind=''shopping''%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%frompublic.shopping_storesasstore_row%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%store_row.user_id=v_user_id%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%deletefrompublic.tasksastask_row%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%task_row.user_id=v_user_id%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%task_row.project_id=p_project_id%'
        AND regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%task_row.shopping_store_id=p_store_id%'
        AND (
          regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%task_row.completed=true%'
          OR regexp_replace(lower(procedure_row.prosrc), '\s+', '', 'g') LIKE '%task_row.completedistrue%'
        )
    )
  ) THEN
    RAISE EXCEPTION 'Migration 019 found an existing public.finish_shopping_trip function with an incompatible contract';
  END IF;
END
$migration_019_preflight$;

CREATE OR REPLACE FUNCTION public.finish_shopping_trip(
  p_project_id UUID,
  p_store_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_user_id UUID := auth.uid();
  v_deleted_count INTEGER;
BEGIN
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'Authentication is required' USING ERRCODE = '42501';
  END IF;

  IF p_project_id IS NULL OR p_store_id IS NULL THEN
    RAISE EXCEPTION 'A shopping project and store are required' USING ERRCODE = '22023';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.projects AS project_row
    WHERE project_row.id = p_project_id
      AND project_row.user_id = v_user_id
      AND project_row.kind = 'shopping'
  ) THEN
    RAISE EXCEPTION 'Shopping trip project must be an owned shopping project'
      USING ERRCODE = '42501';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.shopping_stores AS store_row
    WHERE store_row.id = p_store_id
      AND store_row.user_id = v_user_id
  ) THEN
    RAISE EXCEPTION 'Shopping trip store must be an owned store'
      USING ERRCODE = '42501';
  END IF;

  DELETE FROM public.tasks AS task_row
  WHERE task_row.user_id = v_user_id
    AND task_row.project_id = p_project_id
    AND task_row.shopping_store_id = p_store_id
    AND task_row.completed IS TRUE;

  GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
  RETURN v_deleted_count;
END;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public.finish_shopping_trip(UUID, UUID)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_shopping_trip(UUID, UUID)
  TO authenticated;

DO $migration_019_postflight$
DECLARE
  function_oid OID := 'public.finish_shopping_trip(uuid,uuid)'::regprocedure;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc
    WHERE oid = function_oid
      AND prorettype = 'integer'::regtype
      AND prosecdef
      AND proconfig @> ARRAY['search_path=pg_catalog']::TEXT[]
  ) THEN
    RAISE EXCEPTION 'Migration 019 postflight failed: finish_shopping_trip signature or security configuration mismatch';
  ELSIF EXISTS (
       SELECT 1
       FROM pg_proc AS procedure_row
       CROSS JOIN LATERAL aclexplode(
         COALESCE(procedure_row.proacl, acldefault('f', procedure_row.proowner))
       ) AS privilege_row
       WHERE procedure_row.oid = function_oid
         AND privilege_row.grantee = 0
         AND privilege_row.privilege_type = 'EXECUTE'
     )
     OR has_function_privilege('anon', function_oid, 'EXECUTE')
     OR NOT has_function_privilege('authenticated', function_oid, 'EXECUTE') THEN
    RAISE EXCEPTION 'Migration 019 postflight failed: finish_shopping_trip execute grants mismatch';
  END IF;
END
$migration_019_postflight$;

COMMIT;
