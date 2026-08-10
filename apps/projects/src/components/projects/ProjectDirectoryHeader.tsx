import type { Project } from '../../lib/types/database.types'
import type { BoardType } from '../../types/boards'

const directoryCopy: Record<BoardType, {
  eyebrow: string
  title: string
  selectorLabel: string
  emptyOption: string
  createLabel: string
}> = {
  projects: {
    eyebrow: 'Workflow',
    title: 'Task Boards',
    selectorLabel: 'Current Task Board',
    emptyOption: 'Select a Task Board…',
    createLabel: 'New Task Board',
  },
  shopping: {
    eyebrow: 'Category checklist',
    title: 'Shopping Lists',
    selectorLabel: 'Current Shopping List',
    emptyOption: 'Select a Shopping List…',
    createLabel: 'New Shopping List',
  },
  recipes: {
    eyebrow: 'Cooking collections',
    title: 'Recipe Collections',
    selectorLabel: 'Current Recipe Collection',
    emptyOption: 'Select a Recipe Collection…',
    createLabel: 'New Recipe Collection',
  },
}

interface ProjectDirectoryHeaderProps {
  boardType: BoardType
  projects: Project[]
  selectedProjectId: string | null
  onSelect: (projectId: string) => void
  onCreate: () => void
  onEdit: () => void
}

export function ProjectDirectoryHeader({
  boardType,
  projects,
  selectedProjectId,
  onSelect,
  onCreate,
  onEdit,
}: ProjectDirectoryHeaderProps) {
  const copy = directoryCopy[boardType]

  return (
    <section className="mb-5 rounded-2xl border border-stone-200 bg-white p-4 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-400">{copy.eyebrow}</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-stone-950 dark:text-white">{copy.title}</h2>
        </div>
        <div className="flex flex-1 flex-wrap items-center gap-2 lg:max-w-2xl lg:justify-end">
          <label className="min-w-52 flex-1 lg:max-w-sm">
            <span className="sr-only">{copy.selectorLabel}</span>
            <select
              value={selectedProjectId ?? ''}
              onChange={event => onSelect(event.target.value)}
              aria-label={copy.selectorLabel}
              className="h-10 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm font-medium text-stone-800 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
            >
              <option value="" disabled>{copy.emptyOption}</option>
              {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <button type="button" onClick={onCreate} className="h-10 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white transition hover:bg-emerald-800">{copy.createLabel}</button>
          <button type="button" onClick={onEdit} disabled={!selectedProjectId} className="h-10 rounded-lg border border-stone-300 px-3 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800">Edit</button>
        </div>
      </div>
    </section>
  )
}
