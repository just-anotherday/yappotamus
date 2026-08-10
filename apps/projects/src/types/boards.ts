import type { ProjectKind } from '../lib/types/database.types'

export type BoardType = 'projects' | 'shopping' | 'recipes'

export const boardTypeOptions: Array<{
  value: BoardType
  label: string
}> = [
  { value: 'projects', label: 'Task Boards' },
  { value: 'shopping', label: 'Shopping Lists' },
  { value: 'recipes', label: 'Recipe Collections' },
]

export const boardTypeToProjectKind: Record<BoardType, ProjectKind> = {
  projects: 'board',
  shopping: 'shopping',
  recipes: 'recipes',
}

export function isBoardType(value: unknown): value is BoardType {
  return boardTypeOptions.some(option => option.value === value)
}
