# YapVibes Projects / Planner

A personal organizer with a full Todo/task manager plus two other project formats:

- **Board (Todo/task manager)** — tasks with status, priority, due dates, reminders, pinning, archiving, searching, filtering, sorting, and drag-and-drop ordering.
- **Shopping List** — categorized items with quantities, units, completion, editing, and checked-item cleanup.
- **Recipe Collection** — searchable recipes with timing, servings, ingredient checklists, and numbered instructions.

Projects and entries remain attached to the signed-in Supabase user. Existing projects default to the `board` type.

## Prerequisites

- Node.js and npm.
- A Supabase project with Auth enabled.
- The project's public URL and anon/publishable key. Never use a service-role key in the browser.

## Local development

From the repository root:

```powershell
npm install
Copy-Item apps/projects/.env.example apps/projects/.env.local
```

Fill in `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `.env.local`. Find both values in **Supabase Dashboard → Project Settings → API**.

## Database setup

Projects needs a Supabase project; a plain empty PostgreSQL database does not
provide the required Auth, Storage, Realtime, and database roles.

For a new Supabase project, follow
[`migrations/FRESH_DATABASE.md`](migrations/FRESH_DATABASE.md). Start with the
fresh-only `000` baseline, then apply the documented forward migrations in
order. The optional reminder-email scheduler has separate extension, Vault,
function, and provider-secret prerequisites.

For an existing installation, never apply the fresh baseline. Continue from
the next unapplied forward migration using that installation's migration
record. Files containing `rollback` and files under `migrations/tests` are not
part of the forward install sequence.

After the database is ready, start the app from the repository root:

```powershell
npm run dev:projects
```

Open the URL printed by Vite. Choose **Sign Up**, create an email/password account, and follow the confirmation email if your Supabase Auth settings require it. After signing in, create a **Board** project to use the Todo/task manager. Shopping List and Recipe Collection are optional additional project types.

## Validation

```bash
npm run lint
npm run build
```
