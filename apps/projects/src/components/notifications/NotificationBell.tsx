import { useRef, useState, useCallback } from 'react'
import { useNotifications } from '../../hooks/useNotifications'
import { IconButton } from '../shared/IconButton'
import { NotificationPanel } from './NotificationPanel'

function formatBadgeCount(count: number): string {
  if (count <= 0) return ''
  if (count >= 100) return '99+'
  return String(count)
}

export function NotificationBell() {
  const { unreadCount } = useNotifications()
  const [isOpen, setIsOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const togglePanel = useCallback(() => {
    setIsOpen(prev => !prev)
  }, [])

  // Return focus to trigger when panel closes
  const handlePanelClose = useCallback(() => {
    setIsOpen(false)
    triggerRef.current?.focus()
  }, [])

  const badgeCount = formatBadgeCount(unreadCount)

  return (
    <>
      <IconButton
        ref={triggerRef}
        id="notification-bell-trigger"
        type="button"
        onClick={togglePanel}
        aria-expanded={isOpen}
        ariaLabel={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ''}`}
        tone="emerald"
        variant="secondary"
        className={`relative ${isOpen ? 'border-emerald-500 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200' : ''}`}
      >
        {/* Bell SVG icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="size-5"
        >
          <path d="M6 8a4 4 0 0 1 8 0c0 3 2 7 2 9H4c0-2 2-6 2-9Z" />
          <path d="M10 18h4" />
        </svg>

        {/* Badge */}
        {badgeCount && (
          <span
            className={[
              'absolute -right-1 -top-1 flex size-5 items-center justify-center rounded-full',
              'text-[10px] font-bold leading-none',
              unreadCount > 0
                ? 'bg-emerald-600 text-white'
                : 'bg-stone-400 text-white',
            ].join(' ')}
          >
            {badgeCount}
          </span>
        )}
      </IconButton>

      <NotificationPanel isOpen={isOpen} onClose={handlePanelClose} />
    </>
  )
}
