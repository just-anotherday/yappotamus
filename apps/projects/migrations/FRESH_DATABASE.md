# Fresh Projects database

Projects requires a Supabase database rather than an empty generic PostgreSQL
database. Supabase supplies `auth.users`, the `anon`, `authenticated`, and
`service_role` roles, Realtime, Storage, Vault, and the extension catalog used
by later migrations.

Create the Supabase project first and leave Auth enabled. The frontend uses
Supabase Auth directly, so configure the desired sign-in provider and redirect
URLs in the Supabase dashboard before testing account creation.

## Core schema

For a new Supabase project, run these files in the SQL editor as the database
owner, in this order:

1. `000_fresh_database_baseline.sql`
2. Forward migrations `001` through `016`
3. Forward migrations `018` through `025`

Do not run files whose names contain `rollback`, and do not run files under
`migrations/tests`. The baseline refuses to run if a legacy or current core
table exists. Existing installations start with their next unapplied migration
and must not run the baseline.

This core path creates the tables, indexes, triggers, RPC functions, RLS
policies, browser grants, Realtime registrations, and the public
`recipe-images` Storage bucket. Supabase Storage must be enabled for migration
025. No enum types are required; the schema uses checked text columns.

## Optional scheduled reminders and email

Migrations 011 and 012 create reminder generators but intentionally do not
schedule them. Migration 017 is an operational add-on. Apply it only after all
of these manual prerequisites are complete:

1. Enable `pg_cron`, `pg_net`, and Supabase Vault in the Supabase dashboard.
2. Register the generator jobs as the database owner:

   ```sql
   SELECT cron.schedule(
     'projects-generate-task-due-notifications',
     '17 * * * *',
     $$SELECT * FROM public.generate_task_due_notifications();$$
   );

   SELECT cron.schedule(
     'projects-generate-custom-reminders',
     '* * * * *',
     $$SELECT * FROM public.generate_custom_reminders();$$
   );
   ```

3. Deploy `supabase/functions/reminder-email-worker` and configure its
   `reminder_worker`, `RESEND_API_KEY`, and `REMINDER_EMAIL_FROM` secrets.
4. Add the endpoint URL and the same worker API secret to Vault. Replace these
   placeholders locally; never commit the real values:

   ```sql
   SELECT vault.create_secret(
     'https://YOUR_PROJECT.supabase.co',
     'projects_supabase_url'
   );
   SELECT vault.create_secret(
     'YOUR_REMINDER_WORKER_SECRET',
     'projects_reminder_worker_api_key'
   );
   ```

5. Apply `017_schedule_reminder_email_worker.sql`.

The application runs without migration 017. Scheduled generation and reminder
email delivery remain unavailable until the optional setup is complete.
