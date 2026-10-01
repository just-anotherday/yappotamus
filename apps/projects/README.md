# YapVibes Project Directory

A personal directory for several project formats:

- **Board** — the existing task workflow with status, priority, due dates, pinning, archiving, and manual ordering.
- **Shopping List** — categorized items with quantities, units, completion, editing, and checked-item cleanup.
- **Recipe Collection** — searchable recipes with timing, servings, ingredient checklists, and numbered instructions.

Projects and entries remain attached to the signed-in Supabase user. Existing projects default to the `board` type.

## Local development

```bash
npm install
npm run dev
```

The app reads `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from the appropriate Vite environment file.

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

## Validation

```bash
npm run lint
npm run build
```
