import type { Task, TaskStatus, TaskPriority } from '../lib/types/database.types'
import { currentCalendarDate } from './calendarDate'

export interface TaskFilters {
  status: 'ALL' | TaskStatus
  priority: 'ALL' | TaskPriority
  dueDate: 'ALL' | 'DUE_TODAY' | 'OVERDUE' | 'NO_DUE_DATE'
  showArchived: boolean
}

export const defaultFilters: TaskFilters = {
  status: 'ALL',
  priority: 'ALL',
  dueDate: 'ALL',
  showArchived: false,
}

export function applyFilters(tasks: Task[], filters: TaskFilters): Task[] {
  const today = currentCalendarDate()
  return tasks.filter(task => {
    // Archive filter: when showArchived is false, hide archived tasks; when true, show only archived
    if (!filters.showArchived && task.is_archived) return false
    if (filters.showArchived && !task.is_archived) return false

    // Status filter
    if (filters.status !== 'ALL' && task.status !== filters.status) return false

    // Priority filter
    if (filters.priority !== 'ALL' && task.priority !== filters.priority) return false

    // Due date filter
    if (filters.dueDate !== 'ALL') {
      if (filters.dueDate === 'DUE_TODAY' && task.due_on !== today) return false
      if (filters.dueDate === 'OVERDUE' && (!task.due_on || task.due_on >= today)) return false
      if (filters.dueDate === 'NO_DUE_DATE' && task.due_on) return false
    }

    return true
  })
}
