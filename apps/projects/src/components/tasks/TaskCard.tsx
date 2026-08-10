import { useEffect, useRef, useState } from 'react'
import type { Task, TaskStatus, TaskPriority } from '../../lib/types/database.types'
import TaskStatusBadge from './TaskStatusBadge'
import TaskPriorityBadge from './TaskPriorityBadge'
import { formatCalendarDate } from '../../utils/calendarDate'
import { ReminderControl } from '../reminders/ReminderControl'
import { IconButton } from '../shared/IconButton'

interface TaskCardProps {
  task: Task
  isFocused?: boolean
  isEditing: boolean
  editTitle: string
  editDescription: string
  onToggleComplete: () => void
  onStartEdit: () => void
  onSaveEdit: () => void
  onCancelEdit: () => void
  onUpdateStatus: (status: TaskStatus) => void
  onUpdatePriority: (priority: TaskPriority) => void
  onUpdateDueDate: (dueDate: string | null) => void
  onTogglePin: () => void
  onToggleArchive: () => void
  onDelete: () => void
  onChangeEditTitle: (title: string) => void
  onChangeEditDescription: (desc: string) => void
}

export default function TaskCard({
  task,
  isFocused = false,
  isEditing,
  editTitle,
  editDescription,
  onToggleComplete,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onUpdateStatus,
  onUpdatePriority,
  onUpdateDueDate,
  onTogglePin,
  onToggleArchive,
  onDelete,
  onChangeEditTitle,
  onChangeEditDescription,
}: TaskCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [focusActive, setFocusActive] = useState(false)

  useEffect(() => {
    if (!isFocused) {
      setFocusActive(false)
      return
    }
    setFocusActive(true)
    cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    cardRef.current?.focus({ preventScroll: true })
    const timeout = window.setTimeout(() => setFocusActive(false), 3000)
    return () => window.clearTimeout(timeout)
  }, [isFocused])

  return (
    <div
      ref={cardRef}
      tabIndex={focusActive ? -1 : undefined}
      className={`flex items-start gap-3 p-3 rounded-md border dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition ${task.completed ? 'opacity-60' : ''} ${task.is_pinned ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-300 dark:border-yellow-700' : ''} ${focusActive ? 'ring-2 ring-emerald-500 ring-offset-2 dark:ring-offset-gray-900' : ''}`}
    >
      <input
        type="checkbox"
        checked={task.completed}
        onChange={onToggleComplete}
        className="w-4 h-4 mt-1 cursor-pointer"
      />

      <div className="flex-1 min-w-0">
        {isEditing ? (
          <div className="flex flex-col gap-1">
            <input
              type="text"
              value={editTitle}
              onChange={e => onChangeEditTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && onSaveEdit()}
              className="w-full px-2 py-1 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
              autoFocus
            />
            <input
              type="text"
              value={editDescription}
              onChange={e => onChangeEditDescription(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && onSaveEdit()}
              className="w-full px-2 py-1 border rounded text-xs focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
              placeholder="Description..."
            />
            <div className="flex gap-1">
              <IconButton ariaLabel={`Save changes to ${task.title}`} onClick={onSaveEdit} tone="emerald" className="size-9 min-h-9 text-base">✓</IconButton>
              <IconButton ariaLabel={`Cancel editing ${task.title}`} onClick={onCancelEdit} className="size-9 min-h-9 text-base">✕</IconButton>
            </div>
          </div>
        ) : (
          <div
            className="cursor-pointer group"
            onDoubleClick={onStartEdit}
          >
            {/* Task title + badges row */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-sm ${task.completed ? 'line-through text-gray-400 dark:text-gray-500' : 'text-gray-700 dark:text-gray-200'}`}>
                {task.title}
              </span>

              <TaskStatusBadge status={task.status} />
              <TaskPriorityBadge priority={task.priority} />
            </div>

            {/* Description on hover */}
            {task.description && (
              <span className="invisible group-hover:visible block text-xs text-gray-400 dark:text-gray-500 mt-0.5 transition-opacity">{task.description}</span>
            )}

            {/* Due date row */}
            {task.due_on && (
              <div className="mt-1 flex items-center gap-1">
                <span className="text-xs text-gray-400 dark:text-gray-500">📅 {formatCalendarDate(task.due_on)}</span>
              </div>
            )}
          </div>
        )}

        {/* Action row: status select, priority select, due date, edit, delete */}
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <ReminderControl target={{ kind: 'task', id: task.id, label: task.title }} />
          {/* Status selector */}
          {isEditing !== true && (
            <select
              value={task.status}
              onChange={e => onUpdateStatus(e.target.value as TaskStatus)}
              className={`text-xs px-2 py-1 border rounded cursor-pointer focus:outline-none ${
                task.status === 'TODO' ? 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-200' :
                task.status === 'IN_PROGRESS' ? 'bg-yellow-200 text-yellow-800 dark:bg-yellow-700 dark:text-yellow-100' :
                'bg-green-200 text-green-800 dark:bg-green-700 dark:text-green-100'
              }`}
            >
              <option value="TODO">To Do</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="COMPLETED">Done</option>
            </select>
          )}

          {/* Priority selector */}
          {isEditing !== true && (
            <select
              value={task.priority}
              onChange={e => onUpdatePriority(e.target.value as TaskPriority)}
              className={`text-xs px-2 py-1 border rounded cursor-pointer focus:outline-none dark:bg-gray-700 dark:text-gray-200 ${
                task.priority === 'LOW' ? 'text-blue-500' :
                task.priority === 'MEDIUM' ? 'text-yellow-600' :
                'text-red-500'
              }`}
            >
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
            </select>
          )}

          {/* Due date input */}
          {isEditing !== true && (
            <input
              type="date"
              value={task.due_on ?? ''}
              onChange={e => onUpdateDueDate(e.target.value || null)}
              className="text-xs px-2 py-1 border rounded focus:outline-none dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
            />
          )}

          {/* Pin button */}
          {isEditing !== true && (
            <IconButton
              onClick={onTogglePin}
              ariaLabel={task.is_pinned ? `Unpin ${task.title}` : `Pin ${task.title}`}
              className={`size-9 min-h-9 text-base ${task.is_pinned ? 'text-yellow-600 hover:text-yellow-800 dark:text-yellow-400' : 'text-stone-500 hover:text-yellow-700 dark:text-stone-300'}`}
            >
              {task.is_pinned ? '📌' : '📍'}
            </IconButton>
          )}

          {/* Edit button */}
          {isEditing !== true && (
            <IconButton
              onClick={onStartEdit}
              ariaLabel={`Edit ${task.title}`}
              className="size-9 min-h-9 text-base text-stone-500 hover:text-blue-700 dark:text-stone-300"
            >✏️</IconButton>
          )}

          {/* Archive/Restore button */}
          {isEditing !== true && (
            <IconButton
              onClick={onToggleArchive}
              ariaLabel={task.is_archived ? `Restore ${task.title} from archive` : `Archive ${task.title}`}
              className={`size-9 min-h-9 text-base ${
                task.is_archived
                  ? 'text-purple-600 hover:text-purple-800 dark:text-purple-400'
                  : 'text-stone-500 hover:text-purple-700 dark:text-stone-300'
              }`}
            >
              {task.is_archived ? '📤' : '📥'}
            </IconButton>
          )}

          {/* Delete button */}
          <IconButton
            onClick={onDelete}
            ariaLabel={`Delete ${task.title}`}
            variant="destructive"
            className="size-9 min-h-9 text-base"
          >🗑️</IconButton>
        </div>
      </div>
    </div>
  )
}
