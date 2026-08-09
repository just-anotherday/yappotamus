import type { NotificationRow } from '../../types/notifications'
import { useNotifications } from '../../hooks/useNotifications'
import { useTaskNavigation } from '../../context/TaskNavigationContext'
import { formatCalendarDate, isCalendarDate } from '../../utils/calendarDate'

const TYPE_LABELS: Record<NotificationRow['type'], string> = {
  system_message: 'System',
  task_due_soon: 'Due soon',
  task_overdue: 'Overdue',
  shopping_date_upcoming: 'Shopping reminder',
  custom_reminder: 'Reminder',
}

function formatCreatedAt(isoString: string): string {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) {
    return isoString
  }

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  if (diffMin < 1) return 'Just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHr < 24) return `${diffHr}h ago`

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const itemDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const yesterday = new Date(today.getTime() - 86400000)

  if (itemDay.getTime() === yesterday.getTime()) return 'Yesterday'
  if (diffDay < 7) {
    const daysAgo = diffDay
    return `${daysAgo}d ago`
  }

  const month = date.getMonth() + 1
  const day = date.getDate()
  return `${month < 10 ? '0' : ''}${month}/${day < 10 ? '0' : ''}${day}`
}

function TypeBadge({ type }: { type: NotificationRow['type'] }) {
  const label = TYPE_LABELS[type] ?? type

  return (
    <span className="inline-flex shrink-0 items-center rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-stone-600 dark:bg-stone-800 dark:text-stone-400">
      {label}
    </span>
  )
}

interface NotificationItemProps {
  notification: NotificationRow
  archived?: boolean
  onNavigate?: () => void
}

function taskNotificationTarget(notification: NotificationRow): { projectId?: string; taskId: string } | null {
  if (
    (notification.type !== 'task_due_soon' && notification.type !== 'task_overdue' && notification.type !== 'custom_reminder') ||
    notification.workspace !== 'projects' ||
    notification.entity_type !== 'task' ||
    !notification.entity_id
  ) return null

  const projectId = typeof notification.metadata.project_id === 'string' && notification.metadata.project_id.trim()
    ? notification.metadata.project_id
    : undefined
  if ((notification.type === 'task_due_soon' || notification.type === 'task_overdue') && !projectId) return null

  return { projectId, taskId: notification.entity_id }
}

function dueOnLabel(notification: NotificationRow): string | null {
  if ((notification.type !== 'task_due_soon' && notification.type !== 'task_overdue') || typeof notification.metadata.due_on !== 'string') return null
  return isCalendarDate(notification.metadata.due_on) ? formatCalendarDate(notification.metadata.due_on) : null
}

export function NotificationItem({ notification, archived = false, onNavigate }: NotificationItemProps) {
  const { markRead, markUnread, archive, restore, deleteArchived, isUpdating } = useNotifications()
  const { navigateToTask } = useTaskNavigation()
  const updating = isUpdating(notification.id)
  const target = taskNotificationTarget(notification)
  const dueOn = dueOnLabel(notification)

  const handleToggleRead = () => {
    if (notification.is_read) {
      void markUnread(notification.id)
    } else {
      void markRead(notification.id)
    }
  }

  const handleDelete = () => {
    if (window.confirm('Delete this archived notification permanently?')) {
      void deleteArchived(notification.id)
    }
  }

  const handleViewTask = () => {
    if (!target) return
    void navigateToTask(target)
    onNavigate?.()
  }

  return (
    <div
      className={[
        'group flex gap-3 border-b border-stone-200 p-4 transition-colors last:border-b-0 hover:bg-stone-50 dark:border-stone-800 dark:hover:bg-stone-900/50',
        notification.is_read ? '' : 'bg-emerald-50/60 dark:bg-emerald-950/20',
      ].join(' ')}
      role="listitem"
    >
      <div className="mt-1.5">
        <div
          className={[
            'size-2 rounded-full transition-colors',
            notification.is_read
              ? 'bg-stone-300 dark:bg-stone-700'
              : 'bg-emerald-600 dark:bg-emerald-500',
          ].join(' ')}
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <TypeBadge type={notification.type} />
          <span className="text-[11px] text-stone-400 dark:text-stone-500">
            {formatCreatedAt(notification.created_at)}
          </span>
        </div>

        <h4 className="mt-1.5 text-sm font-semibold text-stone-900 dark:text-stone-100">
          {notification.title}
        </h4>
        <p className="mt-0.5 line-clamp-3 text-xs leading-relaxed text-stone-600 dark:text-stone-400">
          {notification.message}
        </p>
        {dueOn && <p className="mt-1 text-xs font-medium text-stone-600 dark:text-stone-300">Due {dueOn}</p>}

        <div className="mt-2 flex flex-wrap gap-1.5">
          {archived ? (
            <>
              <button
                type="button"
                onClick={() => void restore(notification.id)}
                disabled={updating}
                className="rounded px-2 py-0.5 text-[11px] font-semibold text-emerald-700 transition hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-60 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
              >
                Restore
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={updating}
                className="rounded px-2 py-0.5 text-[11px] font-semibold text-red-600 transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-60 dark:text-red-400 dark:hover:bg-red-950/30"
              >
                Delete
              </button>
            </>
          ) : (
            <>
              {target && (
                <button
                  type="button"
                  onClick={handleViewTask}
                  className="rounded px-2 py-0.5 text-[11px] font-semibold text-emerald-700 transition hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
                >
                  View task
                </button>
              )}
              <button
                type="button"
                onClick={handleToggleRead}
                disabled={updating}
                className={[
                  'inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-semibold transition',
                  notification.is_read
                    ? 'text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800'
                    : 'text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950/30',
                  updating ? 'cursor-wait opacity-60' : '',
                ].join(' ')}
                aria-label={notification.is_read ? 'Mark as unread' : 'Mark as read'}
              >
                {updating ? <span className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent" /> : notification.is_read ? 'Mark as unread' : 'Mark as read'}
              </button>
              <button
                type="button"
                onClick={() => void archive(notification.id)}
                disabled={updating}
                className="rounded px-2 py-0.5 text-[11px] font-semibold text-stone-500 transition hover:bg-stone-100 disabled:cursor-wait disabled:opacity-60 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                Archive
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
