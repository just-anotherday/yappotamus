import type { TaskStatus } from '../../lib/types/database.types'

const STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: 'To Do',
  IN_PROGRESS: 'In Progress',
  COMPLETED: 'Done',
}

const STATUS_COLORS: Record<TaskStatus, string> = {
  TODO: 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-200',
  IN_PROGRESS: 'bg-yellow-200 text-yellow-800 dark:bg-yellow-700 dark:text-yellow-100',
  COMPLETED: 'bg-green-200 text-green-800 dark:bg-green-700 dark:text-green-100',
}

export default function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}

export function getStatusColor(status: TaskStatus) {
  return STATUS_COLORS[status]
}
