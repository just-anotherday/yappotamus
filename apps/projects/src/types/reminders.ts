export type ReminderTargetKind = 'task' | 'shopping_project' | 'recipe'
export type ReminderStatus = 'scheduled' | 'sent' | 'cancelled'
export interface Reminder { id: string; user_id: string; task_id: string | null; shopping_project_id: string | null; recipe_id: string | null; remind_at: string; timezone: string; in_app_enabled: boolean; status: ReminderStatus; fired_at: string | null; cancelled_at: string | null; created_at: string; updated_at: string }
export type ReminderTarget = { kind: ReminderTargetKind; id: string; label: string }
export function parseReminder(value: unknown): Reminder | null { const row=value as Record<string,unknown>; if (!row || typeof row.id!=='string' || typeof row.user_id!=='string' || typeof row.remind_at!=='string' || typeof row.timezone!=='string' || !['scheduled','sent','cancelled'].includes(String(row.status)) || typeof row.in_app_enabled!=='boolean') return null; return row as unknown as Reminder }
