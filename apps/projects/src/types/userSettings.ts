import { DEFAULT_THEME, isTheme, normalizeAppearance, type AppearancePreference, type Theme } from '../lib/themes'

export type ThemePreference = Theme
export type DefaultWorkspace = 'last' | Workspace
export type Workspace = 'projects' | 'shopping' | 'recipes'
export type TaskSortField =
  | 'manual'
  | 'dueDate'
  | 'priority'
  | 'createdAt'
  | 'updatedAt'
  | 'alphabetical'
export type TaskSortDirection = 'asc' | 'desc'

export interface UserSettingsRow {
  user_id: string
  theme: ThemePreference
  appearance: AppearancePreference | null
  default_workspace: DefaultWorkspace
  last_workspace: Workspace
  selected_task_board_id: string | null
  selected_shopping_list_id: string | null
  selected_recipe_book_id: string | null
  hidden_shopping_categories: string[] | null
  task_sort_field: TaskSortField
  task_sort_direction: TaskSortDirection
  hide_purchased_items: boolean
  timezone: string | null
  created_at: string
  updated_at: string
}

export type UserSettingsWritableFields = Pick<
  UserSettingsRow,
  | 'theme'
  | 'appearance'
  | 'default_workspace'
  | 'last_workspace'
  | 'selected_task_board_id'
  | 'selected_shopping_list_id'
  | 'selected_recipe_book_id'
  | 'hidden_shopping_categories'
  | 'task_sort_field'
  | 'task_sort_direction'
  | 'hide_purchased_items'
  | 'timezone'
>

export type UserSettingsInsert = UserSettingsWritableFields & {
  user_id: string
}

export type UserSettingsUpdate = Partial<UserSettingsWritableFields>

export const DEFAULT_USER_SETTINGS: Readonly<UserSettingsWritableFields> = {
  theme: DEFAULT_THEME,
  appearance: null,
  default_workspace: 'last',
  last_workspace: 'projects',
  selected_task_board_id: null,
  selected_shopping_list_id: null,
  selected_recipe_book_id: null,
  hidden_shopping_categories: null,
  task_sort_field: 'manual',
  task_sort_direction: 'asc',
  hide_purchased_items: false,
  timezone: null,
}

const workspaces: readonly Workspace[] = ['projects', 'shopping', 'recipes']
const defaultWorkspaces: readonly DefaultWorkspace[] = ['last', ...workspaces]
const sortFields: readonly TaskSortField[] = [
  'manual',
  'dueDate',
  'priority',
  'createdAt',
  'updatedAt',
  'alphabetical',
]
const sortDirections: readonly TaskSortDirection[] = ['asc', 'desc']
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOneOf<T extends string>(
  value: unknown,
  allowed: readonly T[],
): value is T {
  return typeof value === 'string' && allowed.includes(value as T)
}

export function isThemePreference(value: unknown): value is ThemePreference {
  return isTheme(value)
}

export function isWorkspace(value: unknown): value is Workspace {
  return isOneOf(value, workspaces)
}

export function isDefaultWorkspace(value: unknown): value is DefaultWorkspace {
  return isOneOf(value, defaultWorkspaces)
}

export function isTaskSortField(value: unknown): value is TaskSortField {
  return isOneOf(value, sortFields)
}

export function isTaskSortDirection(value: unknown): value is TaskSortDirection {
  return isOneOf(value, sortDirections)
}

export function isUuidOrNull(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && uuidPattern.test(value))
}

export function isTimezoneOrNull(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && value.trim().length > 0)
}

export function isStringArrayOrNull(value: unknown): value is string[] | null {
  return value === null || (
    Array.isArray(value) && value.every(item => typeof item === 'string')
  )
}

export function validateUserSettingsRow(value: unknown): UserSettingsRow {
  if (!isRecord(value)) {
    throw new Error('The settings response was not a valid record.')
  }

  if (
    typeof value.user_id !== 'string'
    || !isThemePreference(value.theme)
    || (value.appearance !== null && value.appearance !== undefined && typeof value.appearance !== 'object')
    || !isDefaultWorkspace(value.default_workspace)
    || !isWorkspace(value.last_workspace)
    || !isUuidOrNull(value.selected_task_board_id)
    || !isUuidOrNull(value.selected_shopping_list_id)
    || !isUuidOrNull(value.selected_recipe_book_id)
    || (
      value.hidden_shopping_categories !== undefined
      && !isStringArrayOrNull(value.hidden_shopping_categories)
    )
    || !isTaskSortField(value.task_sort_field)
    || !isTaskSortDirection(value.task_sort_direction)
    || typeof value.hide_purchased_items !== 'boolean'
    || !isTimezoneOrNull(value.timezone)
    || typeof value.created_at !== 'string'
    || typeof value.updated_at !== 'string'
  ) {
    throw new Error('The settings response contains unsupported values.')
  }

  return {
    user_id: value.user_id,
    theme: value.theme,
    appearance: value.appearance ? normalizeAppearance(value.appearance, value.theme) : null,
    default_workspace: value.default_workspace,
    last_workspace: value.last_workspace,
    selected_task_board_id: value.selected_task_board_id,
    selected_shopping_list_id: value.selected_shopping_list_id,
    selected_recipe_book_id: value.selected_recipe_book_id,
    hidden_shopping_categories: value.hidden_shopping_categories ?? null,
    task_sort_field: value.task_sort_field,
    task_sort_direction: value.task_sort_direction,
    hide_purchased_items: value.hide_purchased_items,
    timezone: value.timezone,
    created_at: value.created_at,
    updated_at: value.updated_at,
  }
}

export function validateUserSettingsUpdate(
  value: UserSettingsUpdate,
): UserSettingsUpdate {
  if (value.theme !== undefined && !isThemePreference(value.theme)) {
    throw new Error('Choose a supported theme.')
  }
  if (value.appearance !== undefined && value.appearance !== null) {
    const normalized = normalizeAppearance(value.appearance, value.appearance.preset)
    if (JSON.stringify(normalized) !== JSON.stringify(value.appearance)) throw new Error('The appearance preference is invalid.')
  }
  if (
    value.default_workspace !== undefined
    && !isDefaultWorkspace(value.default_workspace)
  ) {
    throw new Error('Choose a supported default workspace.')
  }
  if (
    value.hidden_shopping_categories !== undefined
    && !isStringArrayOrNull(value.hidden_shopping_categories)
  ) {
    throw new Error('The shopping category visibility preference is invalid.')
  }
  if (value.last_workspace !== undefined && !isWorkspace(value.last_workspace)) {
    throw new Error('Choose a supported workspace.')
  }
  for (const selection of [
    value.selected_task_board_id,
    value.selected_shopping_list_id,
    value.selected_recipe_book_id,
  ]) {
    if (selection !== undefined && !isUuidOrNull(selection)) {
      throw new Error('The selected organizer record is invalid.')
    }
  }
  if (
    value.task_sort_field !== undefined
    && !isTaskSortField(value.task_sort_field)
  ) {
    throw new Error('Choose a supported task sort field.')
  }
  if (
    value.task_sort_direction !== undefined
    && !isTaskSortDirection(value.task_sort_direction)
  ) {
    throw new Error('Choose a supported task sort direction.')
  }
  if (
    value.hide_purchased_items !== undefined
    && typeof value.hide_purchased_items !== 'boolean'
  ) {
    throw new Error('The purchased-item visibility preference is invalid.')
  }
  if (value.timezone !== undefined && !isTimezoneOrNull(value.timezone)) {
    throw new Error('The timezone is invalid.')
  }
  return value
}
