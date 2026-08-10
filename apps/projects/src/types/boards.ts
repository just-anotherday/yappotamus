import type { ProjectKind } from '../lib/types/database.types'

export type BoardType = 'projects' | 'shopping' | 'recipes'

export const boardTypeOptions: Array<{
  value: BoardType
  label: string
}> = [
  { value: 'projects', label: 'Task' },
  { value: 'shopping', label: 'Shopping' },
  { value: 'recipes', label: 'Recipe' },
]

export const boardTypeToProjectKind: Record<BoardType, ProjectKind> = {
  projects: 'board',
  shopping: 'shopping',
  recipes: 'recipes',
}

export function isBoardType(value: unknown): value is BoardType {
  return boardTypeOptions.some(option => option.value === value)
}
