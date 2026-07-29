import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useProjects } from '../../hooks/useProjects'
import {
  useTasks,
  type AddTaskOptions,
  type UpdateTaskOptions,
} from '../../hooks/useTasks'
import type { Project, Task, ProjectKind } from '../../lib/types/database.types'
import { boardTypeToProjectKind, type BoardType } from '../../types/boards'
import { ProjectDialog } from '../projects/ProjectDialog'
import { ProjectDirectoryHeader } from '../projects/ProjectDirectoryHeader'
import { LoadingState, RecoverableError } from '../shared/AsyncState'

export interface DirectoryContentProps {
  tasks: Task[]
  onAddTask: (options: AddTaskOptions | string, description?: string) => Promise<void>
  onToggleTask: (id: string, completed: boolean) => Promise<void>
  onUpdateTask: (id: string, options: UpdateTaskOptions | string, description?: string) => Promise<void>
  onDeleteTask: (id: string) => Promise<void>
  onDeleteTasks: (ids: string[]) => Promise<void>
}

interface DirectoryWorkspaceProps {
  boardType: BoardType
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
  renderContent: (props: DirectoryContentProps) => ReactNode
}

const boardCopy: Record<BoardType, {
  singular: string
  plural: string
  childPlural: string
  emptyTitle: string
  emptyDescription: string
  loadingLabel: string
  accent: string
  badge: string
}> = {
  projects: {
    singular: 'Task Board',
    plural: 'Task Boards',
    childPlural: 'tasks',
    emptyTitle: 'No Task Boards yet.',
    emptyDescription: 'Create your first Task Board to organize tasks.',
    loadingLabel: 'Loading Task Boards…',
    accent: 'Task Board',
    badge: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
  },
  shopping: {
    singular: 'Shopping List',
    plural: 'Shopping Lists',
    childPlural: 'shopping items',
    emptyTitle: 'No Shopping Lists yet.',
    emptyDescription: 'Create a list for groceries, supplies, or an upcoming event.',
    loadingLabel: 'Loading Shopping Lists…',
    accent: 'Shopping List',
    badge: 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300',
  },
  recipes: {
    singular: 'Recipe Book',
    plural: 'Recipe Books',
    childPlural: 'recipes',
    emptyTitle: 'No Recipe Books yet.',
    emptyDescription: 'Create a collection for your favorite recipes.',
    loadingLabel: 'Loading Recipe Books…',
    accent: 'Recipe Book',
    badge: 'bg-orange-100 text-orange-800 dark:bg-orange-950/50 dark:text-orange-300',
  },
}

export function DirectoryWorkspace({
  boardType,
  selectedRecordId,
  onSelectedRecordChange,
  renderContent,
}: DirectoryWorkspaceProps) {
  const {
    projects,
    loading: projectsLoading,
    error: projectsError,
    addProject,
    updateProject,
    deleteProject,
  } = useProjects()
  const [dialogMode, setDialogMode] = useState<'create' | 'edit' | null>(null)
  const projectKind = boardTypeToProjectKind[boardType]
  const copy = boardCopy[boardType]
  const directoryRecords = useMemo(
    () => projects.filter(project => project.kind === projectKind),
    [projectKind, projects],
  )

  useEffect(() => {
    if (!directoryRecords.length) {
      if (selectedRecordId !== null) onSelectedRecordChange(null)
      return
    }
    if (!selectedRecordId || !directoryRecords.some(project => project.id === selectedRecordId)) {
      onSelectedRecordChange(directoryRecords[0].id)
    }
  }, [directoryRecords, onSelectedRecordChange, selectedRecordId])

  const selectedRecord = directoryRecords.find(project => project.id === selectedRecordId)
  const {
    tasks,
    loading: tasksLoading,
    error: tasksError,
    addTask,
    toggleTask,
    updateTask,
    deleteTask,
    deleteTasks,
  } = useTasks(selectedRecordId)

  const saveRecord = async (name: string, description: string, kind: ProjectKind) => {
    if (dialogMode === 'create') {
      const created = await addProject(name, description, kind)
      if (!created) return false
      onSelectedRecordChange(created.id)
      return true
    }
    if (!selectedRecord) return false
    return updateProject(selectedRecord.id, name, description)
  }

  const removeRecord = async () => {
    if (!selectedRecord) return false
    const targetId = selectedRecord.id
    const deleted = await deleteProject(targetId)
    if (deleted && selectedRecordId === targetId) onSelectedRecordChange(null)
    return deleted
  }

  if (projectsLoading) return <LoadingState label={copy.loadingLabel} />

  return (
    <>
      <ProjectDirectoryHeader
        boardType={boardType}
        projects={directoryRecords}
        selectedProjectId={selectedRecordId}
        onSelect={onSelectedRecordChange}
        onCreate={() => setDialogMode('create')}
        onEdit={() => selectedRecord && setDialogMode('edit')}
      />
      {(projectsError || tasksError) && <RecoverableError message={projectsError || tasksError || 'Unknown error'} />}
      {selectedRecord ? (
        <section className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 sm:p-7">
          <DirectoryRecordHeading project={selectedRecord} count={tasks.length} badge={copy.badge} accent={copy.accent} />
          {tasksLoading ? <LoadingState label={`Loading ${copy.childPlural}…`} /> : renderContent({
            tasks,
            onAddTask: addTask,
            onToggleTask: toggleTask,
            onUpdateTask: updateTask,
            onDeleteTask: deleteTask,
            onDeleteTasks: deleteTasks,
          })}
        </section>
      ) : (
        <EmptyDirectory
          title={copy.emptyTitle}
          description={copy.emptyDescription}
          createLabel={`Create ${copy.singular}`}
          onCreate={() => setDialogMode('create')}
        />
      )}
      <ProjectDialog
        open={dialogMode !== null}
        mode={dialogMode ?? 'create'}
        project={dialogMode === 'edit' ? selectedRecord : undefined}
        kind={projectKind}
        entityLabel={copy.singular}
        childLabelPlural={copy.childPlural}
        error={projectsError}
        onClose={() => setDialogMode(null)}
        onSave={saveRecord}
        onDelete={dialogMode === 'edit' ? removeRecord : undefined}
      />
    </>
  )
}

function DirectoryRecordHeading({
  project,
  count,
  badge,
  accent,
}: {
  project: Project
  count: number
  badge: string
  accent: string
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 border-b border-stone-200 pb-5 dark:border-stone-800 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-[0.12em] ${badge}`}>{accent}</span>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-stone-950 dark:text-white">{project.name}</h2>
        {project.description && <p className="mt-1 max-w-3xl text-stone-500 dark:text-stone-400">{project.description}</p>}
      </div>
      <p className="text-xs text-stone-400">{count} {count === 1 ? 'entry' : 'entries'} · synced</p>
    </div>
  )
}

function EmptyDirectory({
  title,
  description,
  createLabel,
  onCreate,
}: {
  title: string
  description: string
  createLabel: string
  onCreate: () => void
}) {
  return (
    <section className="rounded-3xl border border-stone-200 bg-white p-7 text-center shadow-sm dark:border-stone-800 dark:bg-stone-900 sm:p-10">
      <h2 className="text-3xl font-semibold tracking-tight text-stone-950 dark:text-white">{title}</h2>
      <p className="mx-auto mt-3 max-w-xl text-stone-600 dark:text-stone-300">{description}</p>
      <button type="button" onClick={onCreate} className="mt-6 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-800">{createLabel}</button>
    </section>
  )
}
