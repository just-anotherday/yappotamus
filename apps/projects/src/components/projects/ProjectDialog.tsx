import { useEffect, useState } from 'react'
import type { Project, ProjectKind } from '../../lib/types/database.types'

const projectKinds: Array<{
  kind: ProjectKind
  label: string
  description: string
}> = [
  { kind: 'board', label: 'Board', description: 'Tasks, priorities, due dates, and workflow.' },
  { kind: 'shopping', label: 'Shopping List', description: 'Items grouped by aisle or category.' },
  { kind: 'recipes', label: 'Recipe Book', description: 'Ingredients and step-by-step instructions.' },
]

interface ProjectDialogProps {
  open: boolean
  mode: 'create' | 'edit'
  project?: Project
  initialKind?: ProjectKind
  error?: string | null
  onClose: () => void
  onSave: (name: string, description: string, kind: ProjectKind) => Promise<void>
  onDelete?: () => Promise<void>
}

export function ProjectDialog({
  open,
  mode,
  project,
  initialKind = 'board',
  error,
  onClose,
  onSave,
  onDelete,
}: ProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [kind, setKind] = useState<ProjectKind>('board')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    if (!open) return
    setName(project?.name ?? '')
    setDescription(project?.description ?? '')
    setKind(project?.kind ?? initialKind)
    setConfirmDelete(false)
  }, [initialKind, open, project])

  if (!open) return null

  const submit = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      await onSave(name.trim(), description.trim(), kind)
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!onDelete) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setSaving(true)
    try {
      await onDelete()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-stone-950/45 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="project-dialog-title"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-xl rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-400">
              {mode === 'create' ? 'Add to directory' : 'Project settings'}
            </p>
            <h2 id="project-dialog-title" className="mt-1 text-2xl font-semibold text-stone-950 dark:text-white">
              {mode === 'create' ? 'Create a project' : 'Edit project'}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-stone-500 hover:text-stone-950 dark:hover:text-white">
            Close
          </button>
        </div>

        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-stone-700 dark:text-stone-200">Name</span>
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              onKeyDown={event => event.key === 'Enter' && submit()}
              autoFocus
              placeholder="e.g. Weekly groceries"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-stone-700 dark:text-stone-200">Description</span>
            <textarea
              value={description}
              onChange={event => setDescription(event.target.value)}
              rows={2}
              placeholder="Optional context for this project"
              className="w-full resize-none rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
            />
          </label>

          <fieldset>
            <legend className="mb-2 text-sm font-semibold text-stone-700 dark:text-stone-200">Project type</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {projectKinds.map(option => (
                <label
                  key={option.kind}
                  className={`rounded-xl border p-3 transition ${
                    kind === option.kind
                      ? 'border-emerald-600 bg-emerald-50 ring-2 ring-emerald-600/10 dark:bg-emerald-950/30'
                      : 'border-stone-200 hover:border-stone-400 dark:border-stone-700'
                  } ${mode === 'edit' ? 'cursor-not-allowed opacity-75' : 'cursor-pointer'}`}
                >
                  <input
                    type="radio"
                    name="project-kind"
                    value={option.kind}
                    checked={kind === option.kind}
                    disabled={mode === 'edit'}
                    onChange={() => setKind(option.kind)}
                    className="sr-only"
                  />
                  <span className="block text-sm font-semibold text-stone-900 dark:text-white">{option.label}</span>
                  <span className="mt-1 block text-xs leading-4 text-stone-500 dark:text-stone-400">{option.description}</span>
                </label>
              ))}
            </div>
            {mode === 'edit' && (
              <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
                Project type stays fixed so existing entries keep their format.
              </p>
            )}
          </fieldset>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            {mode === 'edit' && onDelete && (
              <button
                type="button"
                onClick={remove}
                disabled={saving}
                className="rounded-lg px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950/40"
              >
                {confirmDelete ? 'Click again to delete' : 'Delete project'}
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-100 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={saving || !name.trim()}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? 'Saving…' : mode === 'create' ? 'Create project' : 'Save changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
