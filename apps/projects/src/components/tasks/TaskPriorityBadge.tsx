import type { TaskPriority } from '../../lib/types/database.types'

const PRIORITY_ICONS: Record<TaskPriority, string> = {
  LOW: '↓',
  MEDIUM: '→',
  HIGH: '↑',
}

const PRIORITY_COLORS: Record<TaskPriority, string> = {
  LOW: 'text-blue-500',
  MEDIUM: 'text-yellow-600',
  HIGH: 'text-red-500',
}

export default function TaskPriorityBadge({ priority }: { priority: TaskPriority }) {
  return (
    <span className={`text-xs flex items-center gap-0.5 ${PRIORITY_COLORS[priority]}`}>
      <span>{PRIORITY_ICONS[priority]}</span>
      <span>{priority}</span>
    </span>
  )
}

export function getPriorityColor(priority: TaskPriority) {
  return PRIORITY_COLORS[priority]
}

export function getPriorityIcon(priority: TaskPriority) {
  return PRIORITY_ICONS[priority]
}
