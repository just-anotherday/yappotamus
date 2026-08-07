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
  fetchNotifications,
  fetchUnreadNotificationCount,
  NotificationServiceError,
  updateNotificationReadState,
} from '../services/notifications'
import type { NotificationRow } from '../types/notifications'

export interface NotificationContextValue {
  notifications: NotificationRow[]
  unreadCount: number
  loading: boolean
  refreshing: boolean
  error: string | null
  refresh: () => Promise<void>
  markRead: (notificationId: string) => Promise<void>
  markUnread: (notificationId: string) => Promise<void>
  isUpdating: (notificationId: string) => boolean
}

// oxlint-disable-next-line react/only-export-components
export const NotificationContext =
  createContext<NotificationContextValue | null>(null)

NotificationContext.displayName = 'NotificationContext'

interface NotificationProviderProps {
  userId: string
  children: ReactNode
}

function toSafeErrorMessage(
  error: unknown,
  fallback: string,
): string {
  if (error instanceof NotificationServiceError) {
    return error.message
  }

  return fallback
}

export function NotificationProvider({
  userId,
  children,
}: NotificationProviderProps) {
  const normalizedUserId = userId.trim()

  const [notifications, setNotifications] = useState<
    NotificationRow[]
  >([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [updatingIds, setUpdatingIds] = useState<Set<string>>(
    () => new Set(),
  )

  const notificationsRef = useRef<NotificationRow[]>([])
  const unreadCountRef = useRef(0)

  const mountedRef = useRef(false)
  const generationRef = useRef(0)
  const requestSequenceRef = useRef(0)
  const currentUserIdRef = useRef(normalizedUserId)

  const activeRefreshRef = useRef<Promise<void> | null>(null)
  const pendingUpdateIdsRef = useRef<Set<string>>(new Set())

  currentUserIdRef.current = normalizedUserId

  const isCurrentProvider = useCallback(
    (
      generation: number,
      requestUserId: string,
    ): boolean =>
      mountedRef.current &&
      generationRef.current === generation &&
      currentUserIdRef.current === requestUserId,
    [],
  )

  const runRefresh = useCallback(
    (initial: boolean): Promise<void> => {
      if (!normalizedUserId || !mountedRef.current) {
        return Promise.resolve()
      }

      // Avoid replacing optimistic state while an update is pending.
      if (!initial && pendingUpdateIdsRef.current.size > 0) {
        return Promise.resolve()
      }

      const existingRefresh = activeRefreshRef.current

      if (existingRefresh) {
        return existingRefresh
      }

      const generation = generationRef.current
      const requestId = ++requestSequenceRef.current
      const requestUserId = normalizedUserId

      if (initial) {
        setLoading(true)
      } else {
        setRefreshing(true)
      }

      setError(null)

      let refreshPromise: Promise<void> | null = null

      refreshPromise = (async () => {
        try {
          const [nextNotifications, nextUnreadCount] =
            await Promise.all([
              fetchNotifications(requestUserId),
              fetchUnreadNotificationCount(requestUserId),
            ])

          const requestIsCurrent =
            isCurrentProvider(generation, requestUserId) &&
            requestSequenceRef.current === requestId

          if (!requestIsCurrent) {
            return
          }

          notificationsRef.current = nextNotifications
          unreadCountRef.current = nextUnreadCount

          setNotifications(nextNotifications)
          setUnreadCount(nextUnreadCount)
        } catch (refreshError) {
          const requestIsCurrent =
            isCurrentProvider(generation, requestUserId) &&
            requestSequenceRef.current === requestId

          if (!requestIsCurrent) {
            return
          }

          setError(
            toSafeErrorMessage(
              refreshError,
              'Unable to load notifications.',
            ),
          )
        } finally {
          const ownsActiveRefresh =
            activeRefreshRef.current === refreshPromise

          if (ownsActiveRefresh) {
            activeRefreshRef.current = null
          }

          if (
            ownsActiveRefresh &&
            isCurrentProvider(generation, requestUserId)
          ) {
            setLoading(false)
            setRefreshing(false)
          }
        }
      })()

      activeRefreshRef.current = refreshPromise

      return refreshPromise
    },
    [isCurrentProvider, normalizedUserId],
  )

  const refresh = useCallback(
    (): Promise<void> => runRefresh(false),
    [runRefresh],
  )

  useEffect(() => {
    mountedRef.current = true
    generationRef.current += 1
    requestSequenceRef.current += 1
    currentUserIdRef.current = normalizedUserId

    activeRefreshRef.current = null
    pendingUpdateIdsRef.current.clear()

    notificationsRef.current = []
    unreadCountRef.current = 0

    setNotifications([])
    setUnreadCount(0)
    setError(null)
    setRefreshing(false)
    setUpdatingIds(new Set())
    setLoading(Boolean(normalizedUserId))

    if (normalizedUserId) {
      void runRefresh(true)
    }

    const pendingUpdateIds = pendingUpdateIdsRef.current
    return () => {
      mountedRef.current = false
      generationRef.current += 1
      requestSequenceRef.current += 1

      activeRefreshRef.current = null
      pendingUpdateIds.clear()
    }
  }, [normalizedUserId, runRefresh])

  useEffect(() => {
    if (!normalizedUserId) {
      return undefined
    }

    const handleFocus = () => {
      void runRefresh(false)
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void runRefresh(false)
      }
    }

    window.addEventListener('focus', handleFocus)
    document.addEventListener(
      'visibilitychange',
      handleVisibilityChange,
    )

    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener(
        'visibilitychange',
        handleVisibilityChange,
      )
    }
  }, [normalizedUserId, runRefresh])

  const setReadState = useCallback(
    async (
      notificationId: string,
      requestedReadState: boolean,
    ): Promise<void> => {
      const normalizedNotificationId = notificationId.trim()

      if (
        !normalizedUserId ||
        !normalizedNotificationId ||
        !mountedRef.current
      ) {
        return
      }

      if (
        pendingUpdateIdsRef.current.has(
          normalizedNotificationId,
        )
      ) {
        return
      }

      const previousNotification =
        notificationsRef.current.find(
          (notification) =>
            notification.id === normalizedNotificationId,
        )

      if (
        !previousNotification ||
        previousNotification.is_read === requestedReadState
      ) {
        return
      }

      const generation = generationRef.current
      const requestUserId = normalizedUserId

      // Prevent an older list refresh from overwriting this update.
      requestSequenceRef.current += 1

      pendingUpdateIdsRef.current.add(
        normalizedNotificationId,
      )
      setUpdatingIds(new Set(pendingUpdateIdsRef.current))
      setError(null)

      const countDelta = requestedReadState ? -1 : 1
      const optimisticUnreadCount = Math.max(
        0,
        unreadCountRef.current + countDelta,
      )
      const appliedCountDelta =
        optimisticUnreadCount - unreadCountRef.current

      const optimisticNotifications =
        notificationsRef.current.map((notification) =>
          notification.id === normalizedNotificationId
            ? {
                ...notification,
                is_read: requestedReadState,
              }
            : notification,
        )

      notificationsRef.current = optimisticNotifications
      unreadCountRef.current = optimisticUnreadCount

      setNotifications(optimisticNotifications)
      setUnreadCount(optimisticUnreadCount)

      try {
        const confirmedNotification =
          await updateNotificationReadState(
            requestUserId,
            normalizedNotificationId,
            requestedReadState,
          )

        if (
          !isCurrentProvider(generation, requestUserId)
        ) {
          return
        }

        const confirmedNotifications =
          notificationsRef.current.map((notification) =>
            notification.id === normalizedNotificationId
              ? confirmedNotification
              : notification,
          )

        notificationsRef.current = confirmedNotifications
        setNotifications(confirmedNotifications)
      } catch (updateError) {
        if (
          !isCurrentProvider(generation, requestUserId)
        ) {
          return
        }

        const rolledBackNotifications =
          notificationsRef.current.map((notification) =>
            notification.id === normalizedNotificationId
              ? previousNotification
              : notification,
          )

        const rolledBackUnreadCount = Math.max(
          0,
          unreadCountRef.current - appliedCountDelta,
        )

        notificationsRef.current = rolledBackNotifications
        unreadCountRef.current = rolledBackUnreadCount

        setNotifications(rolledBackNotifications)
        setUnreadCount(rolledBackUnreadCount)
        setError(
          toSafeErrorMessage(
            updateError,
            'Unable to update the notification.',
          ),
        )
      } finally {
        pendingUpdateIdsRef.current.delete(
          normalizedNotificationId,
        )

        if (
          isCurrentProvider(generation, requestUserId)
        ) {
          setUpdatingIds(
            new Set(pendingUpdateIdsRef.current),
          )
        }
      }
    },
    [isCurrentProvider, normalizedUserId],
  )

  const markRead = useCallback(
    (notificationId: string): Promise<void> =>
      setReadState(notificationId, true),
    [setReadState],
  )

  const markUnread = useCallback(
    (notificationId: string): Promise<void> =>
      setReadState(notificationId, false),
    [setReadState],
  )

  const isUpdating = useCallback(
    (notificationId: string): boolean =>
      updatingIds.has(notificationId.trim()),
    [updatingIds],
  )

  const contextValue = useMemo<NotificationContextValue>(
    () => ({
      notifications,
      unreadCount,
      loading,
      refreshing,
      error,
      refresh,
      markRead,
      markUnread,
      isUpdating,
    }),
    [
      notifications,
      unreadCount,
      loading,
      refreshing,
      error,
      refresh,
      markRead,
      markUnread,
      isUpdating,
    ],
  )

  return (
    <NotificationContext.Provider value={contextValue}>
      {children}
    </NotificationContext.Provider>
  )
}
