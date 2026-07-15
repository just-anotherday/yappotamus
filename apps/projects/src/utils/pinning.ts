import type { Task } from '../lib/types/database.types'

/**
 * Groups tasks into pinned first, then normal tasks.
 * Only applies when sort mode is "manual" (default).
 * 
 * This approach keeps pinning as a separate concern from sorting:
 * - Sorting determines the order within each group.
 * - Pinning groups tasks before rendering.
 */
export function groupByPinned(tasks: Task[]): Task[] {
  const pinned = tasks.filter(t => t.is_pinned)
  const normal = tasks.filter(t => !t.is_pinned)
  return [...pinned, ...normal]
}
