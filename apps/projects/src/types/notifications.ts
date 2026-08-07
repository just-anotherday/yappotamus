export type NotificationType =
  | 'system_message'
  | 'task_due_soon'
  | 'task_overdue'
  | 'shopping_date_upcoming';

export type NotificationWorkspace =
  | 'projects'
  | 'shopping'
  | 'recipes'
  | null;

export type NotificationEntityType =
  | 'task'
  | 'shopping_list'
  | 'recipe'
  | null;

export type NotificationMetadata = Record<string, unknown>;

export interface NotificationRow {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string;
  workspace: NotificationWorkspace;
  entity_type: NotificationEntityType;
  entity_id: string | null;
  metadata: NotificationMetadata;
  dedupe_key: string | null;
  is_read: boolean;
  read_at: string | null;
  archived_at: string | null;
  expires_at: string | null;
  created_at: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isNotificationMetadata(
  value: unknown,
): value is NotificationMetadata {
  return isRecord(value);
}

export function isNotificationType(
  value: unknown,
): value is NotificationType {
  return (
    value === 'system_message' ||
    value === 'task_due_soon' ||
    value === 'task_overdue' ||
    value === 'shopping_date_upcoming'
  );
}

export function isNotificationWorkspace(
  value: unknown,
): value is NotificationWorkspace {
  return (
    value === null ||
    value === 'projects' ||
    value === 'shopping' ||
    value === 'recipes'
  );
}

export function isNotificationEntityType(
  value: unknown,
): value is NotificationEntityType {
  return (
    value === null ||
    value === 'task' ||
    value === 'shopping_list' ||
    value === 'recipe'
  );
}

export function parseNotificationRow(
  value: unknown,
): NotificationRow | null {
  if (!isRecord(value)) {
    return null;
  }

  const {
    id,
    user_id,
    type,
    title,
    message,
    workspace,
    entity_type,
    entity_id,
    metadata,
    dedupe_key,
    is_read,
    read_at,
    archived_at,
    expires_at,
    created_at,
  } = value;

  if (!isNonEmptyString(id) || !isNonEmptyString(user_id)) {
    return null;
  }

  if (!isNotificationType(type)) {
    return null;
  }

  if (typeof title !== 'string' || typeof message !== 'string') {
    return null;
  }

  if (!isNotificationWorkspace(workspace)) {
    return null;
  }

  if (!isNotificationEntityType(entity_type)) {
    return null;
  }

  if (!isNullableString(entity_id)) {
    return null;
  }

  const hasValidEntityPair =
    (entity_type === null && entity_id === null) ||
    (entity_type !== null && isNonEmptyString(entity_id));

  if (!hasValidEntityPair) {
    return null;
  }

  if (!isNotificationMetadata(metadata)) {
    return null;
  }

  if (!isNullableString(dedupe_key)) {
    return null;
  }

  if (typeof is_read !== 'boolean') {
    return null;
  }

  if (
    !isNullableString(read_at) ||
    !isNullableString(archived_at) ||
    !isNullableString(expires_at)
  ) {
    return null;
  }

  if (!isNonEmptyString(created_at)) {
    return null;
  }

  return {
    id,
    user_id,
    type,
    title,
    message,
    workspace,
    entity_type,
    entity_id,
    metadata,
    dedupe_key,
    is_read,
    read_at,
    archived_at,
    expires_at,
    created_at,
  };
}

export function parseNotificationRows(
  value: unknown,
): NotificationRow[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const notifications: NotificationRow[] = [];

  for (const item of value) {
    const notification = parseNotificationRow(item);

    if (notification !== null) {
      notifications.push(notification);
    }
  }

  return notifications;
}
