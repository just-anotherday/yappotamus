import { createContext, useContext } from 'react'

export interface TaskNavigationTarget {
  taskId: string
  projectId?: string
}

export interface TaskNavigationContextValue {
  navigateToTask: (target: TaskNavigationTarget) => Promise<void>
}

export const TaskNavigationContext = createContext<TaskNavigationContextValue | null>(null)

export function useTaskNavigation(): TaskNavigationContextValue {
  const context = useContext(TaskNavigationContext)
  if (!context) {
    throw new Error('useTaskNavigation must be used within a TaskNavigationContext')
  }
  return context
}
