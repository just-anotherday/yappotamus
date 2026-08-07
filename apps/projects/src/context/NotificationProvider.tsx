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
  archiveNotification,
  clearActiveNotifications,
  deleteArchivedNotification,
  fetchActiveNotifications,
  fetchArchivedNotifications,
  fetchUnreadNotificationCount,
  NotificationServiceError,
  restoreNotification,
  updateNotificationReadState,
} from '../services/notifications'
import type { NotificationRow } from '../types/notifications'

export interface NotificationContextValue {
  notifications: NotificationRow[]
  archivedNotifications: NotificationRow[]
  unreadCount: number
  loading: boolean
  archivedLoading: boolean
  refreshing: boolean
  error: string | null
  refresh: () => Promise<void>
  markRead: (notificationId: string) => Promise<void>
  markUnread: (notificationId: string) => Promise<void>
  clearActive: () => Promise<void>
  archive: (notificationId: string) => Promise<void>
  restore: (notificationId: string) => Promise<void>
  deleteArchived: (notificationId: string) => Promise<void>
  isUpdating: (notificationId: string) => boolean
  clearing: boolean
}

// oxlint-disable-next-line react/only-export-components
export const NotificationContext = createContext<NotificationContextValue | null>(null)
NotificationContext.displayName = 'NotificationContext'

interface NotificationProviderProps { userId: string; children: ReactNode }

function toSafeErrorMessage(error: unknown, fallback: string): string {
  return error instanceof NotificationServiceError ? error.message : fallback
}

export function NotificationProvider({ userId, children }: NotificationProviderProps) {
  const normalizedUserId = userId.trim()
  const [notifications, setNotifications] = useState<NotificationRow[]>([])
  const [archivedNotifications, setArchivedNotifications] = useState<NotificationRow[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [archivedLoading, setArchivedLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [updatingIds, setUpdatingIds] = useState<Set<string>>(() => new Set())

  const notificationsRef = useRef<NotificationRow[]>([])
  const archivedRef = useRef<NotificationRow[]>([])
  const unreadCountRef = useRef(0)
  const mountedRef = useRef(false)
  const generationRef = useRef(0)
  const requestSequenceRef = useRef(0)
  const currentUserIdRef = useRef(normalizedUserId)
  const activeRefreshRef = useRef<Promise<void> | null>(null)
  const pendingUpdateIdsRef = useRef<Set<string>>(new Set())
  const clearingRef = useRef(false)
  currentUserIdRef.current = normalizedUserId

  const isCurrentProvider = useCallback((generation: number, requestUserId: string) =>
    mountedRef.current && generationRef.current === generation && currentUserIdRef.current === requestUserId, [])

  const applyLists = useCallback((active: NotificationRow[], archived: NotificationRow[]) => {
    notificationsRef.current = active
    archivedRef.current = archived
    setNotifications(active)
    setArchivedNotifications(archived)
  }, [])

  const runRefresh = useCallback((initial: boolean): Promise<void> => {
    if (!normalizedUserId || !mountedRef.current) return Promise.resolve()
    if (!initial && (pendingUpdateIdsRef.current.size > 0 || clearingRef.current)) return Promise.resolve()
    if (activeRefreshRef.current) return activeRefreshRef.current

    const generation = generationRef.current
    const requestId = ++requestSequenceRef.current
    const requestUserId = normalizedUserId
    if (initial) { setLoading(true); setArchivedLoading(true) } else setRefreshing(true)
    setError(null)
    let refreshPromise: Promise<void> | null = null
    refreshPromise = (async () => {
      try {
        const [active, archived, count] = await Promise.all([
          fetchActiveNotifications(requestUserId),
          fetchArchivedNotifications(requestUserId),
          fetchUnreadNotificationCount(requestUserId),
        ])
        if (!isCurrentProvider(generation, requestUserId) || requestSequenceRef.current !== requestId) return
        applyLists(active, archived)
        unreadCountRef.current = count
        setUnreadCount(count)
      } catch (refreshError) {
        if (!isCurrentProvider(generation, requestUserId) || requestSequenceRef.current !== requestId) return
        setError(toSafeErrorMessage(refreshError, 'Unable to load notifications.'))
      } finally {
        const ownsActiveRefresh = activeRefreshRef.current === refreshPromise
        if (ownsActiveRefresh) activeRefreshRef.current = null
        if (ownsActiveRefresh && isCurrentProvider(generation, requestUserId)) {
          setLoading(false); setArchivedLoading(false); setRefreshing(false)
        }
      }
    })()
    activeRefreshRef.current = refreshPromise
    return refreshPromise
  }, [applyLists, isCurrentProvider, normalizedUserId])

  const refresh = useCallback(() => runRefresh(false), [runRefresh])

  useEffect(() => {
    mountedRef.current = true
    generationRef.current += 1
    requestSequenceRef.current += 1
    currentUserIdRef.current = normalizedUserId
    activeRefreshRef.current = null
    pendingUpdateIdsRef.current.clear()
    clearingRef.current = false
    applyLists([], [])
    unreadCountRef.current = 0
    setUnreadCount(0); setError(null); setRefreshing(false); setClearing(false); setUpdatingIds(new Set())
    setLoading(Boolean(normalizedUserId)); setArchivedLoading(Boolean(normalizedUserId))
    if (normalizedUserId) void runRefresh(true)
    const pendingUpdateIds = pendingUpdateIdsRef.current
    return () => {
      mountedRef.current = false
      generationRef.current += 1
      requestSequenceRef.current += 1
      activeRefreshRef.current = null
      pendingUpdateIds.clear()
      clearingRef.current = false
    }
  }, [applyLists, normalizedUserId, runRefresh])

  useEffect(() => {
    if (!normalizedUserId) return undefined
    const handleFocus = () => { void runRefresh(false) }
    const handleVisibilityChange = () => { if (document.visibilityState === 'visible') void runRefresh(false) }
    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => { window.removeEventListener('focus', handleFocus); document.removeEventListener('visibilitychange', handleVisibilityChange) }
  }, [normalizedUserId, runRefresh])

  const beginIdMutation = useCallback((notificationId: string): { generation: number; userId: string } | null => {
    const id = notificationId.trim()
    if (!normalizedUserId || !id || !mountedRef.current || clearingRef.current || pendingUpdateIdsRef.current.has(id)) return null
    requestSequenceRef.current += 1
    pendingUpdateIdsRef.current.add(id)
    setUpdatingIds(new Set(pendingUpdateIdsRef.current)); setError(null)
    return { generation: generationRef.current, userId: normalizedUserId }
  }, [normalizedUserId])

  const endIdMutation = useCallback((id: string, state: { generation: number; userId: string }) => {
    pendingUpdateIdsRef.current.delete(id)
    if (isCurrentProvider(state.generation, state.userId)) setUpdatingIds(new Set(pendingUpdateIdsRef.current))
  }, [isCurrentProvider])

  const setReadState = useCallback(async (notificationId: string, requestedReadState: boolean) => {
    const id = notificationId.trim()
    const previous = notificationsRef.current.find(item => item.id === id)
    if (!previous || previous.is_read === requestedReadState) return
    const state = beginIdMutation(id); if (!state) return
    const countDelta = requestedReadState ? -1 : 1
    const previousCount = unreadCountRef.current
    const nextCount = Math.max(0, previousCount + countDelta)
    applyLists(notificationsRef.current.map(item => item.id === id ? { ...item, is_read: requestedReadState } : item), archivedRef.current)
    unreadCountRef.current = nextCount; setUnreadCount(nextCount)
    try {
      const confirmed = await updateNotificationReadState(state.userId, id, requestedReadState)
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current.map(item => item.id === id ? confirmed : item), archivedRef.current)
    } catch (mutationError) {
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current.map(item => item.id === id ? previous : item), archivedRef.current)
      unreadCountRef.current = previousCount; setUnreadCount(previousCount)
      setError(toSafeErrorMessage(mutationError, 'Unable to update the notification.'))
    } finally { endIdMutation(id, state) }
  }, [applyLists, beginIdMutation, endIdMutation, isCurrentProvider])

  const archive = useCallback(async (notificationId: string) => {
    const id = notificationId.trim(); const previous = notificationsRef.current.find(item => item.id === id)
    if (!previous) return
    const state = beginIdMutation(id); if (!state) return
    const previousCount = unreadCountRef.current
    applyLists(notificationsRef.current.filter(item => item.id !== id), [{ ...previous, archived_at: new Date().toISOString() }, ...archivedRef.current])
    if (!previous.is_read) { unreadCountRef.current = Math.max(0, previousCount - 1); setUnreadCount(unreadCountRef.current) }
    try {
      const confirmed = await archiveNotification(state.userId, id)
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current, archivedRef.current.map(item => item.id === id ? confirmed : item))
    } catch (mutationError) {
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists([previous, ...notificationsRef.current], archivedRef.current.filter(item => item.id !== id))
      unreadCountRef.current = previousCount; setUnreadCount(previousCount)
      setError(toSafeErrorMessage(mutationError, 'Unable to archive the notification.'))
    } finally { endIdMutation(id, state) }
  }, [applyLists, beginIdMutation, endIdMutation, isCurrentProvider])

  const restore = useCallback(async (notificationId: string) => {
    const id = notificationId.trim(); const previous = archivedRef.current.find(item => item.id === id)
    if (!previous) return
    const state = beginIdMutation(id); if (!state) return
    const previousCount = unreadCountRef.current
    applyLists([{ ...previous, archived_at: null }, ...notificationsRef.current], archivedRef.current.filter(item => item.id !== id))
    if (!previous.is_read) { unreadCountRef.current = previousCount + 1; setUnreadCount(unreadCountRef.current) }
    try {
      const confirmed = await restoreNotification(state.userId, id)
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current.map(item => item.id === id ? confirmed : item), archivedRef.current)
    } catch (mutationError) {
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current.filter(item => item.id !== id), [previous, ...archivedRef.current])
      unreadCountRef.current = previousCount; setUnreadCount(previousCount)
      setError(toSafeErrorMessage(mutationError, 'Unable to restore the notification.'))
    } finally { endIdMutation(id, state) }
  }, [applyLists, beginIdMutation, endIdMutation, isCurrentProvider])

  const deleteArchived = useCallback(async (notificationId: string) => {
    const id = notificationId.trim(); const previous = archivedRef.current.find(item => item.id === id)
    if (!previous) return
    const state = beginIdMutation(id); if (!state) return
    applyLists(notificationsRef.current, archivedRef.current.filter(item => item.id !== id))
    try { await deleteArchivedNotification(state.userId, id) }
    catch (mutationError) {
      if (!isCurrentProvider(state.generation, state.userId)) return
      applyLists(notificationsRef.current, [previous, ...archivedRef.current])
      setError(toSafeErrorMessage(mutationError, 'Unable to delete the notification.'))
    } finally { endIdMutation(id, state) }
  }, [applyLists, beginIdMutation, endIdMutation, isCurrentProvider])

  const clearActive = useCallback(async () => {
    if (
      !normalizedUserId ||
      !mountedRef.current ||
      clearingRef.current ||
      pendingUpdateIdsRef.current.size > 0 ||
      unreadCountRef.current === 0
    ) return
    const generation = generationRef.current; const requestUserId = normalizedUserId
    requestSequenceRef.current += 1; clearingRef.current = true; setClearing(true); setError(null)
    let cleared = false
    try { await clearActiveNotifications(requestUserId); cleared = true }
    catch (mutationError) { if (isCurrentProvider(generation, requestUserId)) setError(toSafeErrorMessage(mutationError, 'Unable to mark active notifications as read.')) }
    finally {
      clearingRef.current = false
      if (isCurrentProvider(generation, requestUserId)) {
        setClearing(false)
        if (cleared) await runRefresh(false)
      }
    }
  }, [isCurrentProvider, normalizedUserId, runRefresh])

  const markRead = useCallback((id: string) => setReadState(id, true), [setReadState])
  const markUnread = useCallback((id: string) => setReadState(id, false), [setReadState])
  const isUpdating = useCallback((id: string) => updatingIds.has(id.trim()), [updatingIds])
  const contextValue = useMemo<NotificationContextValue>(() => ({ notifications, archivedNotifications, unreadCount, loading, archivedLoading, refreshing, error, refresh, markRead, markUnread, clearActive, archive, restore, deleteArchived, isUpdating, clearing }), [notifications, archivedNotifications, unreadCount, loading, archivedLoading, refreshing, error, refresh, markRead, markUnread, clearActive, archive, restore, deleteArchived, isUpdating, clearing])
  return <NotificationContext.Provider value={contextValue}>{children}</NotificationContext.Provider>
}
