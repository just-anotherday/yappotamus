import { useCallback, useMemo, useState } from 'react'
import type { Task } from '../lib/types/database.types'
import { applySort, DEFAULT_SORT_CONFIG } from '../utils/sorting'

export function useTaskSort(tasks: Task[]) {
  const [sortConfig, setSortConfig] = useState(DEFAULT_SORT_CONFIG)
  
  // Memoize sorted tasks to avoid recalculating on every render
  const sortedTasks = useMemo(
    () => applySort(tasks, sortConfig),
    [tasks, sortConfig]
  )

  const clearSort = useCallback(() => {
    setSortConfig(DEFAULT_SORT_CONFIG)
  }, [])

  return {
    sortedTasks,
    sortConfig,
    setSortConfig,
    clearSort,
  }
}
