import { useEffect, useMemo, useRef, useState } from 'react'
import type { AddTaskOptions, UpdateTaskOptions } from '../../hooks/useTasks'
import { useTaskFilters } from '../../hooks/useTaskFilters'
import { useTaskReorder } from '../../hooks/useTaskReorder'
import { useTaskSearch } from '../../hooks/useTaskSearch'
import { useTaskSort } from '../../hooks/useTaskSort'
import type { Task, TaskPriority, TaskStatus } from '../../lib/types/database.types'
import { groupByPinned } from '../../utils/pinning'
import { DraggableTaskList } from '../tasks/DraggableTaskList'
import TaskCard from '../tasks/TaskCard'
import { TaskFilterBar } from '../tasks/TaskFilterBar'
import TaskForm from '../tasks/TaskForm'
import { TaskSearchBar } from '../tasks/TaskSearchBar'
import { TaskSortBar } from '../tasks/TaskSortBar'

interface BoardProjectProps {
  tasks: Task[]
  onAddTask: (options: AddTaskOptions | string, description?: string) => Promise<void>
  onToggleTask: (id: string, completed: boolean) => Promise<void>
  onUpdateTask: (id: string, options: UpdateTaskOptions | string, description?: string) => Promise<void>
  onDeleteTask: (id: string) => Promise<void>
  focusedTaskId: string | null
  onFocusedTaskHandled: () => void
}

export function BoardProject({
  tasks,
  onAddTask,
  onToggleTask,
  onUpdateTask,
  onDeleteTask,
  focusedTaskId,
  onFocusedTaskHandled,
}: BoardProjectProps) {
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editTaskTitle, setEditTaskTitle] = useState('')
  const [editTaskDescription, setEditTaskDescription] = useState('')
  const [activeFocusedTaskId, setActiveFocusedTaskId] = useState<string | null>(null)
  const focusTimeoutRef = useRef<number | null>(null)

  const { filteredTasks: searchedTasks, query, setSearchQuery, clearSearch, isSearching } = useTaskSearch(tasks)
  const { filteredTasks, filters, setFilter, clearFilters, hasActiveFilters } = useTaskFilters(searchedTasks)
  const { sortedTasks, sortConfig, setSortConfig, clearSort } = useTaskSort(filteredTasks)
  const renderedTasks = useMemo(() => groupByPinned(sortedTasks), [sortedTasks])
  const requestedFocusedTask = useMemo(
    () => focusedTaskId ? tasks.find(task => task.id === focusedTaskId) ?? null : null,
    [focusedTaskId, tasks],
  )
  const activeFocusedTask = useMemo(
    () => activeFocusedTaskId ? tasks.find(task => task.id === activeFocusedTaskId) ?? null : null,
    [activeFocusedTaskId, tasks],
  )
  const visibleTasks = useMemo(() => {
    if (!activeFocusedTask || renderedTasks.some(task => task.id === activeFocusedTask.id)) return renderedTasks
    return [activeFocusedTask, ...renderedTasks]
  }, [activeFocusedTask, renderedTasks])

  useEffect(() => {
    if (!requestedFocusedTask) return
    setActiveFocusedTaskId(requestedFocusedTask.id)
    if (focusTimeoutRef.current !== null) window.clearTimeout(focusTimeoutRef.current)
    focusTimeoutRef.current = window.setTimeout(() => {
      setActiveFocusedTaskId(null)
      focusTimeoutRef.current = null
    }, 3000)
    onFocusedTaskHandled()
  }, [onFocusedTaskHandled, requestedFocusedTask])

  useEffect(() => () => {
    if (focusTimeoutRef.current !== null) window.clearTimeout(focusTimeoutRef.current)
  }, [])

  const saveTaskEdit = async (id: string) => {
    if (!editTaskTitle.trim()) return
    await onUpdateTask(id, {
      title: editTaskTitle.trim(),
      description: editTaskDescription.trim(),
    })
    setEditingTaskId(null)
    setEditTaskTitle('')
    setEditTaskDescription('')
  }

  const updateStatus = async (id: string, status: TaskStatus) => {
    await onUpdateTask(id, { status, completed: status === 'COMPLETED' })
  }

  const reorderTasks = async (reorderedTasks: Task[]) => {
    await Promise.all(reorderedTasks.map(task => onUpdateTask(task.id, { order: task.order })))
  }

  const { handleDragEnd, dragEnabled } = useTaskReorder({
    tasks: renderedTasks,
    onReorder: reorderTasks,
    isManualSort: sortConfig.field === 'manual',
  })

  return (
    <div className="grid gap-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <aside className="rounded-2xl border border-stone-200 bg-stone-50 p-4 dark:border-stone-800 dark:bg-stone-900/70">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Add a task</p>
        <TaskForm
          onSubmit={(title, description, priority, dueDate) => {
            if (!title.trim()) return
            return onAddTask({
              title: title.trim(),
              description: description.trim() || undefined,
              priority,
              due_on: dueDate,
            })
          }}
        />
        <div className="mt-5 border-t border-stone-200 pt-4 text-sm text-stone-600 dark:border-stone-700 dark:text-stone-300">
          <div className="flex justify-between">
            <span>Completed</span>
            <strong>{tasks.filter(task => task.completed).length}</strong>
          </div>
          <div className="mt-2 flex justify-between">
            <span>Total tasks</span>
            <strong>{tasks.length}</strong>
          </div>
        </div>
      </aside>

      <section className="min-w-0">
        <div className="mb-4 grid gap-3">
          <TaskSearchBar value={query} onChange={setSearchQuery} onClear={clearSearch} />
          <TaskFilterBar
            filters={filters}
            onSetFilter={setFilter}
            onClear={clearFilters}
            hasActiveFilters={hasActiveFilters}
          />
          <TaskSortBar sortConfig={sortConfig} onSetSortConfig={setSortConfig} onReset={clearSort} />
        </div>

        <DraggableTaskList tasks={visibleTasks} onDragEnd={handleDragEnd} dragEnabled={dragEnabled}>
          {task => (
            <TaskCard
              key={task.id}
              task={task}
              isFocused={task.id === activeFocusedTaskId}
              isEditing={editingTaskId === task.id}
              editTitle={editTaskTitle}
              editDescription={editTaskDescription}
              onToggleComplete={() => onToggleTask(task.id, !task.completed)}
              onStartEdit={() => {
                setEditingTaskId(task.id)
                setEditTaskTitle(task.title)
                setEditTaskDescription(task.description || '')
              }}
              onSaveEdit={() => saveTaskEdit(task.id)}
              onCancelEdit={() => {
                setEditingTaskId(null)
                setEditTaskTitle('')
                setEditTaskDescription('')
              }}
              onUpdateStatus={(status: TaskStatus) => updateStatus(task.id, status)}
              onUpdatePriority={(priority: TaskPriority) => onUpdateTask(task.id, { priority })}
              onUpdateDueDate={dueDate => onUpdateTask(task.id, { due_on: dueDate })}
              onTogglePin={() => onUpdateTask(task.id, { is_pinned: !task.is_pinned })}
              onToggleArchive={() => onUpdateTask(task.id, { is_archived: !task.is_archived })}
              onDelete={() => onDeleteTask(task.id)}
              onChangeEditTitle={setEditTaskTitle}
              onChangeEditDescription={setEditTaskDescription}
            />
          )}
        </DraggableTaskList>

        {renderedTasks.length === 0 && (
          <div className="rounded-2xl border border-dashed border-stone-300 px-6 py-14 text-center dark:border-stone-700">
            <p className="font-medium text-stone-700 dark:text-stone-200">
              {isSearching || hasActiveFilters ? 'No tasks match these filters.' : 'This board is ready for its first task.'}
            </p>
            <p className="mt-1 text-sm text-stone-500">Use the form to add something you want to move forward.</p>
          </div>
        )}
      </section>
    </div>
  )
}
