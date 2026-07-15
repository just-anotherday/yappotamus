import { useState, useCallback, useMemo } from 'react'
import type { Task } from '../lib/types/database.types'
import { filterTasksBySearch } from '../utils/search'

export function useTaskSearch(tasks: Task[]) {
  const [query, setQuery] = useState('')

  const filteredTasks = useMemo(() => filterTasksBySearch(tasks, query), [tasks, query])

  const setSearchQuery = useCallback((q: string) => {
    setQuery(q)
  }, [])

  const clearSearch = useCallback(() => {
    setQuery('')
  }, [])

  return {
    filteredTasks,
    query,
    setSearchQuery,
    clearSearch,
    isSearching: query.trim().length > 0,
  }
}
