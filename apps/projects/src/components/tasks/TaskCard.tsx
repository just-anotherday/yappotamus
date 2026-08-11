import { useEffect, useRef, useState } from 'react'
import type { Task, TaskPriority, TaskStatus } from '../../lib/types/database.types'
import { formatCalendarDate } from '../../utils/calendarDate'
import { ReminderControl } from '../reminders/ReminderControl'
import { IconButton } from '../shared/IconButton'
import TaskPriorityBadge from './TaskPriorityBadge'
import TaskStatusBadge from './TaskStatusBadge'

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

const fieldClass = 'min-h-10 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100'

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
      className={`flex items-start gap-3 rounded-xl border border-stone-200 bg-white p-4 transition-colors hover:border-emerald-200 hover:bg-emerald-50/30 dark:border-stone-800 dark:bg-stone-900/70 dark:hover:border-emerald-900 dark:hover:bg-emerald-950/20 ${task.completed ? 'opacity-60' : ''} ${task.is_pinned ? 'border-amber-300 bg-amber-50/60 dark:border-amber-900/70 dark:bg-amber-950/20' : ''} ${focusActive ? 'ring-2 ring-emerald-500 ring-offset-2 dark:ring-offset-stone-950' : ''}`}
    >
      <input type="checkbox" checked={task.completed} onChange={onToggleComplete} className="mt-1 size-5 shrink-0 accent-emerald-700" aria-label={`Mark ${task.title} ${task.completed ? 'incomplete' : 'complete'}`} />

      <div className="min-w-0 flex-1">
        {isEditing ? (
          <div className="grid gap-2">
            <input type="text" value={editTitle} onChange={e => onChangeEditTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && onSaveEdit()} className={fieldClass} autoFocus />
            <input type="text" value={editDescription} onChange={e => onChangeEditDescription(e.target.value)} onKeyDown={e => e.key === 'Enter' && onSaveEdit()} className={fieldClass} placeholder="Description..." />
            <div className="flex flex-wrap gap-2">
              <IconButton ariaLabel={`Save changes to ${task.title}`} onClick={onSaveEdit} tone="emerald">✓</IconButton>
              <IconButton ariaLabel={`Cancel editing ${task.title}`} onClick={onCancelEdit}>×</IconButton>
            </div>
          </div>
        ) : (
          <div className="group cursor-pointer" onDoubleClick={onStartEdit}>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-sm font-medium ${task.completed ? 'text-stone-400 line-through dark:text-stone-500' : 'text-stone-800 dark:text-stone-100'}`}>{task.title}</span>
              <TaskStatusBadge status={task.status} />
              <TaskPriorityBadge priority={task.priority} />
            </div>
            {task.description && <span className="mt-1 block text-xs text-stone-500 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 dark:text-stone-400">{task.description}</span>}
            {task.due_on && <div className="mt-1 text-xs text-stone-500 dark:text-stone-400">Due {formatCalendarDate(task.due_on)}</div>}
          </div>
        )}

        {!isEditing && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <ReminderControl target={{ kind: 'task', id: task.id, label: task.title }} />
            <select value={task.status} onChange={e => onUpdateStatus(e.target.value as TaskStatus)} className={`${fieldClass} min-h-9 px-2 py-1 text-xs ${task.status === 'TODO' ? 'bg-stone-100 dark:bg-stone-800' : task.status === 'IN_PROGRESS' ? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100' : 'border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100'}`}>
              <option value="TODO">To Do</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="COMPLETED">Done</option>
            </select>
            <select value={task.priority} onChange={e => onUpdatePriority(e.target.value as TaskPriority)} className={`${fieldClass} min-h-9 px-2 py-1 text-xs ${task.priority === 'LOW' ? 'text-blue-700 dark:text-blue-300' : task.priority === 'MEDIUM' ? 'text-amber-800 dark:text-amber-300' : 'text-red-700 dark:text-red-300'}`}>
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
            </select>
            <input type="date" value={task.due_on ?? ''} onChange={e => onUpdateDueDate(e.target.value || null)} className={`${fieldClass} min-h-9 px-2 py-1 text-xs`} />
            <div className="flex flex-wrap gap-1">
              <IconButton onClick={onTogglePin} ariaLabel={task.is_pinned ? `Unpin ${task.title}` : `Pin ${task.title}`} tone="emerald" className={task.is_pinned ? 'text-amber-700 dark:text-amber-300' : ''}>{task.is_pinned ? '📌' : '📍'}</IconButton>
              <IconButton onClick={onStartEdit} ariaLabel={`Edit ${task.title}`} tone="emerald">✏️</IconButton>
              <IconButton onClick={onToggleArchive} ariaLabel={task.is_archived ? `Restore ${task.title} from archive` : `Archive ${task.title}`} tone="emerald">{task.is_archived ? '📤' : '📥'}</IconButton>
              <IconButton onClick={onDelete} ariaLabel={`Delete ${task.title}`} variant="destructive">🗑️</IconButton>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
