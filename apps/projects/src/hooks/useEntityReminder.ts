import { useCallback, useEffect, useState } from 'react'
import { cancelReminder, getScheduledReminder, saveReminder } from '../services/reminders'
import type { Reminder, ReminderTarget } from '../types/reminders'

export function useEntityReminder(target: ReminderTarget) {
  const { id, kind } = target
  const [reminder, setReminder] = useState<Reminder | null>(null)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setReminder(await getScheduledReminder({ id, kind, label: '' })); setError(null) }
    catch { setError('Unable to load reminder.') }
    finally { setLoading(false) }
  }, [id, kind])
  useEffect(() => { void refresh() }, [refresh])

  const save = useCallback(async (date: string, time: string, timezone: string, instant: string, inAppEnabled: boolean, emailEnabled: boolean) => {
    setPending(true)
    try { await saveReminder({ id, kind, label: '' }, date, time, timezone, instant, inAppEnabled, emailEnabled); await refresh(); return true }
    catch { setError('Unable to save reminder.'); return false }
    finally { setPending(false) }
  }, [id, kind, refresh])
  const cancel = useCallback(async () => {
    if (!reminder) return false
    setPending(true)
    try { await cancelReminder(reminder.id); setReminder(null); return true }
    catch { setError('Unable to remove reminder.'); return false }
    finally { setPending(false) }
  }, [reminder])
  return { reminder, loading, pending, error, save, cancel }
}
