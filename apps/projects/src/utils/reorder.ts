import type { Task } from '../lib/types/database.types'

/**
 * Reorders an array by moving an item from one index to another.
 * Returns a new array with the reordered items and updated order values.
 */
export function reorderTasks(list: Task[], startIndex: number, endIndex: number): Task[] {
  const result = [...list]
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)

  // Update order field to reflect new positions
  return result.map((task, index) => ({ ...task, order: index }))
}
