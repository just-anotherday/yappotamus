import type { Task } from '../lib/types/database.types'

export type SortField = 'manual' | 'dueDate' | 'priority' | 'createdAt' | 'updatedAt' | 'alphabetical'
export type SortDirection = 'asc' | 'desc'

export interface SortConfig {
  field: SortField
  direction: SortDirection
}

export const DEFAULT_SORT_CONFIG: SortConfig = {
  field: 'manual',
  direction: 'asc',
}

const PRIORITY_ORDER: Record<string, number> = {
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
}

function compare(a: Task, b: Task, config: SortConfig): number {
  const { field, direction } = config
  let result = 0

  switch (field) {
    case 'manual':
      result = a.order - b.order
      break

    case 'dueDate':
      // Null due dates always last
      if (!a.due_date && !b.due_date) result = 0
      else if (!a.due_date) result = 1
      else if (!b.due_date) result = -1
      else result = a.due_date.localeCompare(b.due_date)
      break

    case 'priority':
      result = (PRIORITY_ORDER[a.priority] ?? 0) - (PRIORITY_ORDER[b.priority] ?? 0)
      break

    case 'createdAt':
      result = a.created_at.localeCompare(b.created_at)
      break

    case 'updatedAt':
      result = (a.updated_at || '').localeCompare(b.updated_at || '')
      break

    case 'alphabetical':
      result = a.title.toLowerCase().localeCompare(b.title.toLowerCase())
      break
  }

  return direction === 'asc' ? result : -result
}

export function applySort(tasks: Task[], config: SortConfig): Task[] {
  return [...tasks].sort((a, b) => compare(a, b, config))
}
