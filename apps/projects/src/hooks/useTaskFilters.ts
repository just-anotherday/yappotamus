import { useState, useCallback, useMemo } from 'react'
import type { Task } from '../lib/types/database.types'
import { applyFilters, defaultFilters, type TaskFilters } from '../utils/filters'

export function useTaskFilters(tasks: Task[]) {
  const [filters, setFilters] = useState<TaskFilters>(defaultFilters)

  const filteredTasks = useMemo(() => applyFilters(tasks, filters), [tasks, filters])

  const setFilter = useCallback(<K extends keyof TaskFilters>(key: K, value: TaskFilters[K]) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }, [])

  const clearFilters = useCallback(() => {
    setFilters(defaultFilters)
  }, [])

  const hasActiveFilters = useMemo(
    () => filters.status !== 'ALL' || filters.priority !== 'ALL' || filters.dueDate !== 'ALL',
    [filters]
  )

  return {
    filteredTasks,
    filters,
    setFilter,
    clearFilters,
    hasActiveFilters,
  }
}
