import { useEffect, useRef, useCallback, type KeyboardEvent } from 'react'
import { useNotifications } from '../../hooks/useNotifications'
import { NotificationItem } from './NotificationItem'

interface NotificationPanelProps {
  isOpen: boolean
  onClose: () => void
}

export function NotificationPanel({ isOpen, onClose }: NotificationPanelProps) {
  const { notifications, unreadCount, loading, refreshing, error, refresh } =
    useNotifications()
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        onClose()
      }
    },
    [onClose],
  )

  // Close when clicking outside (portal-like behavior via body click)
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      const panel = panelRef.current
      const trigger = document.getElementById('notification-bell-trigger')
      if (
        panel &&
        !panel.contains(event.target as Node) &&
        trigger &&
        !trigger.contains(event.target as Node)
      ) {
        onClose()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onClose])

  // Lock body scroll when panel is open on mobile
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = ''
      }
    }
    return
  }, [isOpen])

  const handleRefresh = useCallback(() => {
    void refresh()
  }, [refresh])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end pt-16 px-4 sm:px-6 lg:px-8 pointer-events-none"
      aria-modal="true"
      role="dialog"
      aria-label="Notifications"
    >
      <div
        ref={panelRef}
        className={[
          'pointer-events-auto w-full max-w-md overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-xl dark:border-stone-800 dark:bg-stone-950',
          'max-h-[calc(100vh-7rem)] flex flex-col',
        ].join(' ')}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-stone-200 px-5 py-4 dark:border-stone-800">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">
              Notifications
            </h2>
            {unreadCount > 0 && (
              <span className="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-emerald-600 px-1.5 py-0.5 text-[11px] font-bold text-white">
                {unreadCount}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className={[
              'inline-flex size-8 items-center justify-center rounded-lg transition-colors',
              'text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300',
              refreshing && 'cursor-wait opacity-50',
            ].join(' ')}
            aria-label="Refresh notifications"
          >
            {refreshing ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-[2px] border-current border-t-transparent" />
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="size-4"
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6" />
                <path d="M2.5 11.5a8 8 0 0 1 15-3.9L21.5 9" />
                <path d="M2.5 12.5a8 8 0 0 0 15 3.9L2.5 15" />
              </svg>
            )}
          </button>

          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-8 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
            aria-label="Close notifications"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="size-4"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="border-b border-red-200 bg-red-50 px-5 py-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
          >
            {error}
          </div>
        )}

        {/* Content */}
        <div className="overflow-y-auto" role="list">
          {loading && !refreshing ? (
            <div className="flex flex-col items-center gap-4 py-16 px-5 text-stone-400 dark:text-stone-600">
              <span className="inline-block h-6 w-6 animate-spin rounded-full border-[2px] border-current border-t-transparent" />
              <p className="text-xs font-medium">Loading notifications…</p>
            </div>
          ) : notifications.length === 0 && !loading ? (
            <div className="flex flex-col items-center gap-4 py-16 px-5 text-stone-400 dark:text-stone-600">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="size-10 opacity-40"
              >
                <path d="M6 8a4 4 0 0 1 8 0c0 3 2 7 2 9H4c0-2 2-6 2-9Z" />
                <path d="M10 18h4" />
              </svg>
              <p className="text-sm font-medium">You're all caught up.</p>
            </div>
          ) : (
            <ul className="divide-y divide-stone-200 dark:divide-stone-800/60">
              {notifications.map((notification) => (
                <li key={notification.id} className="p-0">
                  <NotificationItem notification={notification} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
