import type { Task } from '../lib/types/database.types'

export function filterTasksBySearch(tasks: Task[], query: string): Task[] {
  const trimmed = query.trim()

  if (!trimmed) return tasks

  const lowerQuery = trimmed.toLowerCase()

  return tasks.filter(task => {
    const titleMatch = task.title.toLowerCase().includes(lowerQuery)
    const descMatch = task.description ? task.description.toLowerCase().includes(lowerQuery) : false
    return titleMatch || descMatch
  })
}
