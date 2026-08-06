import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  fetchCurrentUserSettings,
  insertInitialSettings,
  updateCurrentUserSettings,
} from '../services/userSettings'
import {
  DEFAULT_USER_SETTINGS,
  isThemePreference,
  isUuidOrNull,
  isWorkspace,
  type DefaultWorkspace,
  type TaskSortDirection,
  type TaskSortField,
  type ThemePreference,
  type UserSettingsRow,
  type UserSettingsUpdate,
  type UserSettingsWritableFields,
  type Workspace,
} from '../types/userSettings'

interface UserSettingsContextValue {
  settings: UserSettingsRow | null
  loading: boolean
  saving: boolean
  error: string | null
  refresh: () => Promise<void>
  patchSettings: (patch: UserSettingsUpdate) => Promise<boolean>
  updateTheme: (theme: ThemePreference) => Promise<boolean>
  updateWorkspacePreferences: (
    patch: Partial<{
      default_workspace: DefaultWorkspace
      last_workspace: Workspace
    }>,
  ) => Promise<boolean>
  updateSelectedId: (
    workspace: Workspace,
    id: string | null,
  ) => Promise<boolean>
  updateTaskSorting: (
    field: TaskSortField,
    direction: TaskSortDirection,
  ) => Promise<boolean>
  updatePurchasedItemVisibility: (hidden: boolean) => Promise<boolean>
}

export const UserSettingsContext =
  createContext<UserSettingsContextValue | null>(null)

const boardPreferencePrefix = 'yapvibes:organizer:board'

function boardPreferenceKey(userId: string) {
  return `${boardPreferencePrefix}:${userId}`
}

function recipeBookSelectionKey(userId: string) {
  return `organizer:${userId}:recipe-book-selection`
}

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function removeStorage(key: string) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Storage can be unavailable. Server initialization is still complete.
  }
}

function readLegacyInitialSettings(userId: string): UserSettingsWritableFields {
  const initial = { ...DEFAULT_USER_SETTINGS }
  const deviceTheme = readStorage('theme')
  const workspace = readStorage(boardPreferenceKey(userId))
  const recipeBookId = readStorage(recipeBookSelectionKey(userId))

  if (isThemePreference(deviceTheme)) initial.theme = deviceTheme
  if (isWorkspace(workspace)) initial.last_workspace = workspace
  if (recipeBookId !== null && isUuidOrNull(recipeBookId)) {
    initial.selected_recipe_book_id = recipeBookId
  }
  return initial
}

function clearImportedUserKeys(userId: string) {
  removeStorage(boardPreferenceKey(userId))
  removeStorage(recipeBookSelectionKey(userId))
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Your settings could not be loaded. Please try again.'
}

function patchMatches(
  settings: UserSettingsRow,
  patch: UserSettingsUpdate,
): boolean {
  return Object.entries(patch).every(([key, value]) => (
    settings[key as keyof UserSettingsRow] === value
  ))
}

export function UserSettingsProvider({
  userId,
  children,
}: {
  userId: string
  children: ReactNode
}) {
  const [settings, setSettings] = useState<UserSettingsRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingCount, setSavingCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const generation = useRef(0)
  const requestSequence = useRef(0)
  const pendingCount = useRef(0)
  const writeQueue = useRef<Promise<void>>(Promise.resolve())
  const settingsRef = useRef<UserSettingsRow | null>(null)
  const confirmedSettingsRef = useRef<UserSettingsRow | null>(null)

  const refresh = useCallback(async () => {
    if (pendingCount.current > 0) return
    const currentGeneration = generation.current
    const request = ++requestSequence.current
    try {
      const nextSettings = await fetchCurrentUserSettings(userId)
      if (
        currentGeneration !== generation.current
        || request !== requestSequence.current
      ) return
      if (!nextSettings) {
        setError('No settings row exists for this account.')
        return
      }
      confirmedSettingsRef.current = nextSettings
      settingsRef.current = nextSettings
      setSettings(nextSettings)
      setError(null)
    } catch (caught) {
      if (
        currentGeneration === generation.current
        && request === requestSequence.current
      ) {
        setError(errorMessage(caught))
      }
    }
  }, [userId])

  useEffect(() => {
    const currentGeneration = ++generation.current
    requestSequence.current += 1
    pendingCount.current = 0
    writeQueue.current = Promise.resolve()
    settingsRef.current = null
    confirmedSettingsRef.current = null
    setSettings(null)
    setLoading(true)
    setSavingCount(0)
    setError(null)

    void (async () => {
      try {
        let nextSettings = await fetchCurrentUserSettings(userId)
        if (!nextSettings) {
          nextSettings = await insertInitialSettings(
            userId,
            readLegacyInitialSettings(userId),
          )
        }
        if (currentGeneration !== generation.current) return
        confirmedSettingsRef.current = nextSettings
        settingsRef.current = nextSettings
        setSettings(nextSettings)
        clearImportedUserKeys(userId)
        setError(null)
      } catch (caught) {
        if (currentGeneration === generation.current) {
          setError(errorMessage(caught))
        }
      } finally {
        if (currentGeneration === generation.current) setLoading(false)
      }
    })()

    return () => {
      generation.current += 1
      requestSequence.current += 1
      pendingCount.current = 0
      settingsRef.current = null
      confirmedSettingsRef.current = null
    }
  }, [userId])

  useEffect(() => {
    const reconcile = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    const onFocus = () => void refresh()

    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', reconcile)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', reconcile)
    }
  }, [refresh])

  const patchSettings = useCallback(async (
    patch: UserSettingsUpdate,
  ): Promise<boolean> => {
    const previousEffectiveSettings = settingsRef.current

    if (!previousEffectiveSettings) return false
    if (patchMatches(previousEffectiveSettings, patch)) return true

    const optimisticSettings: UserSettingsRow = {
      ...previousEffectiveSettings,
      ...patch,
    }

    settingsRef.current = optimisticSettings
    setSettings(optimisticSettings)

    const currentGeneration = generation.current
    const operationUserId = userId

    pendingCount.current += 1
    setSavingCount(count => count + 1)
    setError(null)

    let succeeded = false

    const operation = async () => {
      try {
        const serverSettings = await updateCurrentUserSettings(
          operationUserId,
          patch,
        )

        if (currentGeneration !== generation.current) return

        confirmedSettingsRef.current = serverSettings

        const currentEffectiveSettings = settingsRef.current
        if (!currentEffectiveSettings) return

        const reconciled: UserSettingsRow = {
          ...currentEffectiveSettings,
          created_at: serverSettings.created_at,
          updated_at: serverSettings.updated_at,
        }

        for (
          const key of Object.keys(patch) as Array<
            keyof UserSettingsUpdate
          >
        ) {
          if (
            currentEffectiveSettings[key]
            === optimisticSettings[key]
          ) {
            Object.assign(reconciled, {
              [key]: serverSettings[key],
            })
          }
        }

        settingsRef.current = reconciled
        setSettings(reconciled)
        setError(null)
        succeeded = true
      } catch (caught) {
        if (currentGeneration !== generation.current) return

        const currentEffectiveSettings = settingsRef.current
        const confirmedSettings = confirmedSettingsRef.current

        if (!currentEffectiveSettings || !confirmedSettings) return

        const rolledBack: UserSettingsRow = {
          ...currentEffectiveSettings,
        }

        for (
          const key of Object.keys(patch) as Array<
            keyof UserSettingsUpdate
          >
        ) {
          if (
            currentEffectiveSettings[key]
            === optimisticSettings[key]
          ) {
            Object.assign(rolledBack, {
              [key]: confirmedSettings[key],
            })
          }
        }

        settingsRef.current = rolledBack
        setSettings(rolledBack)
        setError(errorMessage(caught))
      } finally {
        if (currentGeneration === generation.current) {
          pendingCount.current = Math.max(
            0,
            pendingCount.current - 1,
          )
          setSavingCount(count => Math.max(0, count - 1))
        }
      }
    }

    const queued = writeQueue.current.then(operation, operation)

    writeQueue.current = queued.then(
      () => undefined,
      () => undefined,
    )

    await queued
    return succeeded
  }, [userId])

  const updateTheme = useCallback(
    (theme: ThemePreference) => patchSettings({ theme }),
    [patchSettings],
  )

  const updateWorkspacePreferences = useCallback((
    patch: Partial<{
      default_workspace: DefaultWorkspace
      last_workspace: Workspace
    }>,
  ) => patchSettings(patch), [patchSettings])

  const updateSelectedId = useCallback((
    workspace: Workspace,
    id: string | null,
  ) => {
    const field = workspace === 'projects'
      ? 'selected_task_board_id'
      : workspace === 'shopping'
        ? 'selected_shopping_list_id'
        : 'selected_recipe_book_id'
    return patchSettings({ [field]: id })
  }, [patchSettings])

  const updateTaskSorting = useCallback((
    field: TaskSortField,
    direction: TaskSortDirection,
  ) => patchSettings({
    task_sort_field: field,
    task_sort_direction: direction,
  }), [patchSettings])

  const updatePurchasedItemVisibility = useCallback(
    (hidden: boolean) => patchSettings({ hide_purchased_items: hidden }),
    [patchSettings],
  )

  const value = useMemo<UserSettingsContextValue>(() => ({
    settings,
    loading,
    saving: savingCount > 0,
    error,
    refresh,
    patchSettings,
    updateTheme,
    updateWorkspacePreferences,
    updateSelectedId,
    updateTaskSorting,
    updatePurchasedItemVisibility,
  }), [
    error,
    loading,
    patchSettings,
    refresh,
    savingCount,
    settings,
    updatePurchasedItemVisibility,
    updateSelectedId,
    updateTaskSorting,
    updateTheme,
    updateWorkspacePreferences,
  ])

  return (
    <UserSettingsContext.Provider value={value}>
      {children}
    </UserSettingsContext.Provider>
  )
}
