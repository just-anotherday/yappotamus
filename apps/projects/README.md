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

## Database migration

Apply `migrations/004_add_project_kinds_and_task_metadata.sql` to the correctly identified Supabase project before using Shopping List or Recipe Collection projects. It adds:

- `projects.kind`, defaulting existing rows to `board`
- `tasks.metadata`, a JSON object used for shopping and recipe fields
- an index for a user's projects by kind

The migration does not replace or weaken existing row-level security policies. A rollback script is provided beside it.

## Validation

```bash
npm run lint
npm run build
```
