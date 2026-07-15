import { useCallback } from 'react'
import type { UniqueIdentifier } from '@dnd-kit/core'
import type { Task } from '../lib/types/database.types'
import { reorderTasks } from '../utils/reorder'

interface UseTaskReorderOptions {
  tasks: Task[]
  onReorder: (tasks: Task[]) => void
  isManualSort: boolean
}

interface DragEvent {
  active: { id: UniqueIdentifier }
  over: { id: UniqueIdentifier } | null
}

export function useTaskReorder({ tasks, onReorder, isManualSort }: UseTaskReorderOptions) {
  const handleDragEnd = useCallback(
    (dragResult: DragEvent) => {
      if (!isManualSort || !dragResult.over) return

      const { active, over } = dragResult
      if (active.id === over.id) return

      const oldIndex = tasks.findIndex(t => t.id === active.id)
      const newIndex = tasks.findIndex(t => t.id === over.id)

      if (oldIndex === -1 || newIndex === -1) return

      const reordered = reorderTasks(tasks, oldIndex, newIndex)
      onReorder(reordered)
    },
    [tasks, isManualSort, onReorder]
  )

  return { handleDragEnd, dragEnabled: isManualSort }
}
