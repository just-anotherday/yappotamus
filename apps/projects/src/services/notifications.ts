import { supabase } from '../lib/supabase'
import {
  parseNotificationRows,
  parseNotificationRow,
  type NotificationRow,
} from '../types/notifications'

interface SupabaseFailure {
  code?: string
  message?: string
}

export class NotificationServiceError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NotificationServiceError'
  }
}

function safeFetchError(error: unknown): NotificationServiceError {
  const failure = error as SupabaseFailure | null
  if (failure?.code === '42501') {
    return new NotificationServiceError(
      'Your notifications could not be accessed for this account.',
    )
  }
  if (failure?.message?.toLowerCase().includes('network')) {
    return new NotificationServiceError(
      'Your notifications could not be loaded because the network is unavailable.',
    )
  }
  return new NotificationServiceError('Unable to load notifications.')
}

function safeUpdateError(error: unknown): NotificationServiceError {
  const failure = error as SupabaseFailure | null
  if (failure?.code === '42501' || failure?.code === 'PGRST301') {
    return new NotificationServiceError(
      'Notification was not found or is unavailable.',
    )
  }
  return new NotificationServiceError('Unable to update the notification.')
}

const NOTIFICATION_COLUMNS = [
  'id',
  'user_id',
  'type',
  'title',
  'message',
  'workspace',
  'entity_type',
  'entity_id',
  'metadata',
  'dedupe_key',
  'is_read',
  'read_at',
  'expires_at',
  'created_at',
].join(',')

export interface FetchNotificationsOptions {
  limit?: number
  includeExpired?: boolean
}

const DEFAULT_LIMIT = 25
const MAX_LIMIT = 100

export async function fetchNotifications(
  userId: string,
  options?: FetchNotificationsOptions,
): Promise<NotificationRow[]> {
  if (!userId || typeof userId !== 'string' || userId.trim() === '') {
    throw new NotificationServiceError('Unable to load notifications.')
  }

  const limit = options?.limit ?? DEFAULT_LIMIT

  if (typeof limit !== 'number' || !Number.isInteger(limit)) {
    throw new NotificationServiceError('Invalid limit value. Please provide a valid integer.')
  }

  if (limit < 1) {
    throw new NotificationServiceError(
      'Unable to load notifications.',
    )
  }

  if (limit > MAX_LIMIT) {
    throw new NotificationServiceError(
      `The maximum allowed number of notifications is ${MAX_LIMIT}.`,
    )
  }

  const now = new Date().toISOString()

  let query = supabase
    .from('notifications')
    .select(NOTIFICATION_COLUMNS)
    .eq('user_id', userId)

  if (options?.includeExpired !== true) {
    query = query.or(`expires_at.is.null,expires_at.gt.${now}`)
  }

  query = query
    .order('created_at', { ascending: false })
    .order('id', { ascending: false })
    .limit(limit)

  const { data, error } = await query

  if (error) throw safeFetchError(error)

  if (!Array.isArray(data)) {
    throw new NotificationServiceError(
      'Notification data returned by the server was invalid.',
    )
  }

  const parsed = parseNotificationRows(data)

  if (parsed.length !== data.length) {
    throw new NotificationServiceError(
      'Notification data returned by the server was invalid.',
    )
  }

  for (const row of parsed) {
    if (row.user_id !== userId) {
      throw new NotificationServiceError(
        'Notification data returned by the server was invalid.',
      )
    }
  }

  return parsed
}

export async function fetchUnreadNotificationCount(
  userId: string,
): Promise<number> {
  if (!userId || typeof userId !== 'string' || userId.trim() === '') {
    throw new NotificationServiceError('Unable to load notifications.')
  }

  const now = new Date().toISOString()

  const { count, error } = await supabase
    .from('notifications')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', userId)
    .eq('is_read', false)
    .or(`expires_at.is.null,expires_at.gt.${now}`)

  if (error) throw safeFetchError(error)
  if (count === null || count === undefined) {
    throw new NotificationServiceError(
      'Notification data returned by the server was invalid.',
    )
  }

  if (!Number.isInteger(count) || count < 0) {
    throw new NotificationServiceError(
      'Notification data returned by the server was invalid.',
    )
  }

  return count
}

export async function updateNotificationReadState(
  userId: string,
  notificationId: string,
  isRead: boolean,
): Promise<NotificationRow> {
  if (!userId || typeof userId !== 'string' || userId.trim() === '') {
    throw new NotificationServiceError('Unable to update the notification.')
  }

  if (
    !notificationId ||
    typeof notificationId !== 'string' ||
    notificationId.trim() === ''
  ) {
    throw new NotificationServiceError(
      'Notification was not found or is unavailable.',
    )
  }

  const { data, error } = await supabase
    .from('notifications')
    .update({ is_read: isRead })
    .eq('id', notificationId)
    .eq('user_id', userId)
    .select(NOTIFICATION_COLUMNS)
    .single()

  if (error) throw safeUpdateError(error)

  const parsed = parseNotificationRow(data)

  if (!parsed) {
    throw new NotificationServiceError(
      'Notification data returned by the server was invalid.',
    )
  }

  if (parsed.user_id !== userId) {
    throw new NotificationServiceError(
      'Notification was not found or is unavailable.',
    )
  }

  if (parsed.id !== notificationId) {
    throw new NotificationServiceError(
      'Notification was not found or is unavailable.',
    )
  }

  if (parsed.is_read !== isRead) {
    throw new NotificationServiceError(
      'Notification state could not be confirmed.',
    )
  }

  return parsed
}
