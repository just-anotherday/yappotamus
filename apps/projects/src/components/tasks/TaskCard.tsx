import type { Task, TaskStatus, TaskPriority } from '../../lib/types/database.types'
import TaskStatusBadge from './TaskStatusBadge'
import TaskPriorityBadge from './TaskPriorityBadge'

interface TaskCardProps {
  task: Task
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

const formatDate = (dateStr: string | null | undefined) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return ''
  }
}

export default function TaskCard({
  task,
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
  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-md border dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition ${task.completed ? 'opacity-60' : ''} ${task.is_pinned ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-300 dark:border-yellow-700' : ''}`}
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
              <button onClick={onSaveEdit} className="text-green-500 hover:text-green-700 text-sm px-1 cursor-pointer">✓</button>
              <button onClick={onCancelEdit} className="text-gray-400 hover:text-gray-600 text-sm px-1 cursor-pointer">✕</button>
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
            {task.due_date && (
              <div className="mt-1 flex items-center gap-1">
                <span className="text-xs text-gray-400 dark:text-gray-500">📅 {formatDate(task.due_date)}</span>
              </div>
            )}
          </div>
        )}

        {/* Action row: status select, priority select, due date, edit, delete */}
        <div className="flex flex-wrap items-center gap-2 mt-2">
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
              value={task.due_date ? task.due_date.split('T')[0] : ''}
              onChange={e => onUpdateDueDate(e.target.value || null)}
              className="text-xs px-2 py-1 border rounded focus:outline-none dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
            />
          )}

          {/* Pin button */}
          {isEditing !== true && (
            <button
              onClick={onTogglePin}
              className={`text-xs px-1 cursor-pointer transition ${task.is_pinned ? 'text-yellow-500 hover:text-yellow-700' : 'text-gray-400 hover:text-yellow-500'}`}
              title={task.is_pinned ? 'Unpin task' : 'Pin task'}
            >
              {task.is_pinned ? '📌' : '📍'}
            </button>
          )}

          {/* Edit button */}
          {isEditing !== true && (
            <button
              onClick={onStartEdit}
              className="text-gray-400 hover:text-blue-500 text-xs px-1 cursor-pointer"
            >✏️</button>
          )}

          {/* Archive/Restore button */}
          {isEditing !== true && (
            <button
              onClick={onToggleArchive}
              className={`text-xs px-1 cursor-pointer transition ${
                task.is_archived
                  ? 'text-purple-500 hover:text-purple-700'
                  : 'text-gray-400 hover:text-purple-500'
              }`}
              title={task.is_archived ? 'Restore from archive' : 'Archive task'}
            >
              {task.is_archived ? '📤' : '📥'}
            </button>
          )}

          {/* Delete button */}
          <button
            onClick={onDelete}
            className="text-gray-400 hover:text-red-500 text-xs px-1 cursor-pointer"
          >🗑️</button>
        </div>
      </div>
    </div>
  )
}
