import type { Project } from '../../lib/types/database.types'

const kindLabel = {
  board: 'Board',
  shopping: 'Shopping',
  recipes: 'Recipes',
} as const

interface ProjectDirectoryHeaderProps {
  projects: Project[]
  selectedProjectId: string | null
  userEmail?: string
  theme: 'light' | 'dark'
  onSelect: (projectId: string) => void
  onCreate: () => void
  onEdit: () => void
  onToggleTheme: () => void
  onSignOut: () => void
}

export function ProjectDirectoryHeader({
  projects,
  selectedProjectId,
  userEmail,
  theme,
  onSelect,
  onCreate,
  onEdit,
  onToggleTheme,
  onSignOut,
}: ProjectDirectoryHeaderProps) {
  return (
    <header className="border-b border-stone-200/80 bg-white/90 backdrop-blur dark:border-stone-800 dark:bg-stone-950/90">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl bg-emerald-700 text-sm font-black tracking-tight text-white shadow-sm">
            YV
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-400">
              yapvibes
            </p>
            <h1 className="text-xl font-semibold text-stone-950 dark:text-stone-50">Project Directory</h1>
          </div>
        </div>

        <div className="flex flex-1 flex-wrap items-center gap-2 lg:max-w-2xl lg:justify-end">
          <label className="min-w-52 flex-1 lg:max-w-sm">
            <span className="sr-only">Current project</span>
            <select
              value={selectedProjectId ?? ''}
              onChange={event => onSelect(event.target.value)}
              className="h-10 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm font-medium text-stone-800 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
            >
              <option value="" disabled>Select a project…</option>
              {projects.map(project => (
                <option key={project.id} value={project.id}>
                  {kindLabel[project.kind]} — {project.name}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={onCreate}
            className="h-10 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white transition hover:bg-emerald-800"
          >
            New project
          </button>
          <button
            type="button"
            onClick={onEdit}
            disabled={!selectedProjectId}
            className="h-10 rounded-lg border border-stone-300 px-3 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onToggleTheme}
            className="h-10 rounded-lg border border-stone-300 px-3 text-sm text-stone-700 transition hover:bg-stone-100 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
            aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
          >
            {theme === 'light' ? 'Dark' : 'Light'}
          </button>
          <div className="hidden text-right xl:block">
            <p className="max-w-44 truncate text-xs text-stone-500 dark:text-stone-400">{userEmail}</p>
            <button
              type="button"
              onClick={onSignOut}
              className="text-xs font-semibold text-stone-700 hover:text-emerald-700 dark:text-stone-300 dark:hover:text-emerald-400"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
