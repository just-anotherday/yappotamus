import { createContext, useContext } from 'react'

export interface TaskNavigationTarget {
  projectId: string
  taskId: string
}

export interface TaskNavigationContextValue {
  navigateToTask: (target: TaskNavigationTarget) => void
}

export const TaskNavigationContext = createContext<TaskNavigationContextValue | null>(null)

export function useTaskNavigation(): TaskNavigationContextValue {
  const context = useContext(TaskNavigationContext)
  if (!context) {
    throw new Error('useTaskNavigation must be used within a TaskNavigationContext')
  }
  return context
}
