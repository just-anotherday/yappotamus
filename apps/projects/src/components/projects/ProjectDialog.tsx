import { useEffect, useState } from 'react'
import type { Project, ProjectKind } from '../../lib/types/database.types'

interface ProjectDialogProps {
  open: boolean
  mode: 'create' | 'edit'
  project?: Project
  kind: ProjectKind
  entityLabel: string
  childLabelPlural: string
  error?: string | null
  onClose: () => void
  onSave: (name: string, description: string, kind: ProjectKind) => Promise<boolean>
  onDelete?: () => Promise<boolean>
}

export function ProjectDialog({
  open,
  mode,
  project,
  kind,
  entityLabel,
  childLabelPlural,
  error,
  onClose,
  onSave,
  onDelete,
}: ProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    if (!open) return
    setName(project?.name ?? '')
    setDescription(project?.description ?? '')
    setConfirmDelete(false)
  }, [open, project])

  if (!open) return null

  const submit = async () => {
    if (!name.trim() || saving) return
    setSaving(true)
    try {
      const saved = await onSave(name.trim(), description.trim(), kind)
      if (saved) onClose()
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!onDelete || saving) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }

    setSaving(true)
    try {
      const deleted = await onDelete()
      if (deleted) onClose()
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
        if (!saving && event.target === event.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-xl rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-400">
              {mode === 'create' ? 'Add to directory' : 'Directory settings'}
            </p>
            <h2 id="project-dialog-title" className="mt-1 text-2xl font-semibold text-stone-950 dark:text-white">
              {mode === 'create' ? `Create ${entityLabel}` : `Edit ${entityLabel}`}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="text-sm text-stone-500 hover:text-stone-950 disabled:opacity-50 dark:hover:text-white"
          >
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
              disabled={saving}
              autoFocus
              placeholder={entityLabel === 'project' ? 'e.g. Website launch' : entityLabel === 'shopping list' ? 'e.g. Weekly groceries' : 'e.g. Favorite recipes'}
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 disabled:opacity-60 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-stone-700 dark:text-stone-200">Description</span>
            <textarea
              value={description}
              onChange={event => setDescription(event.target.value)}
              disabled={saving}
              rows={2}
              placeholder={`Optional context for this ${entityLabel}`}
              className="w-full resize-none rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 disabled:opacity-60 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
            />
          </label>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            {mode === 'edit' && onDelete && (
              <>
                {confirmDelete && (
                  <p className="mb-2 max-w-sm text-xs leading-5 text-red-700 dark:text-red-300">
                    This permanently deletes this {entityLabel} and all of its {childLabelPlural}. This cannot be undone.
                  </p>
                )}
                <button
                  type="button"
                  onClick={remove}
                  disabled={saving}
                  className="rounded-lg px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950/40"
                >
                  {confirmDelete ? `Confirm delete ${entityLabel}` : `Delete ${entityLabel}`}
                </button>
              </>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-100 disabled:opacity-50 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={saving || !name.trim()}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? 'Saving…' : mode === 'create' ? `Create ${entityLabel}` : 'Save changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
