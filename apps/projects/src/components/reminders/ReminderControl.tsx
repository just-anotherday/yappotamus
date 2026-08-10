import { useEffect, useState } from 'react'
import { Temporal } from '@js-temporal/polyfill'
import { useUserSettings } from '../../hooks/useUserSettings'
import { useEntityReminder } from '../../hooks/useEntityReminder'
import type { ReminderTarget } from '../../types/reminders'
import { Button } from '../shared/Button'

export function ReminderControl({ target }: { target: ReminderTarget }) {
  const { settings } = useUserSettings()
  const state = useEntityReminder(target)
  const [open, setOpen] = useState(false)
  const zone = settings?.timezone
  const current = state.reminder
  const [date, setDate] = useState(Temporal.Now.zonedDateTimeISO(zone ?? 'UTC').toPlainDate().toString())
  const [time, setTime] = useState('09:00')
  const [inAppEnabled, setInAppEnabled] = useState(true)
  const [emailEnabled, setEmailEnabled] = useState(false)
  const [validation, setValidation] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const local = current ? Temporal.Instant.from(current.remind_at).toZonedDateTimeISO(current.timezone) : null
    setDate(local?.toPlainDate().toString() ?? Temporal.Now.zonedDateTimeISO(zone ?? 'UTC').toPlainDate().toString())
    setTime(local?.toPlainTime().toString({ smallestUnit: 'minute' }) ?? '09:00')
    setInAppEnabled(current?.in_app_enabled ?? true)
    setEmailEnabled(current?.email_enabled ?? false)
    setValidation(null)
  }, [open, current, zone])

  const save = async () => {
    if (!zone) {
      setValidation('Your timezone is still being set up. Please try again shortly.')
      return
    }
    if (!inAppEnabled && !emailEnabled) {
      setValidation('Choose at least one reminder method.')
      return
    }
    try {
      const plain = Temporal.PlainDateTime.from(`${date}T${time}`)
      const instant = Temporal.ZonedDateTime.from({ year: plain.year, month: plain.month, day: plain.day, hour: plain.hour, minute: plain.minute, second: plain.second, timeZone: zone }, { disambiguation: 'reject' }).toInstant()
      if (instant.epochMilliseconds < Date.now() - 60000) {
        setValidation('Choose a future time.')
        return
      }
      if (await state.save(date, time, zone, instant.toString(), inAppEnabled, emailEnabled)) setOpen(false)
    } catch {
      setValidation('This time is invalid or occurs twice because of daylight saving time. Choose another time.')
    }
  }

  const methods = [current?.in_app_enabled ? 'In app' : null, current?.email_enabled ? 'Email' : null].filter(Boolean).join(' + ')
  const isShoppingReminder = target.kind === 'shopping_project'
  const reminderStatus = current
    ? `Scheduled ${Temporal.Instant.from(current.remind_at).toZonedDateTimeISO(current.timezone).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })} · ${methods}`
    : 'No reminder set'

  return <div className={isShoppingReminder ? 'mb-5 flex flex-col gap-3 rounded-xl border border-stone-200 bg-stone-50/80 px-4 py-3 dark:border-stone-800 dark:bg-stone-900/60 sm:flex-row sm:items-center sm:justify-between' : 'mt-2 text-xs'}>
    {isShoppingReminder ? <>
      <div className="flex min-w-0 items-start gap-2.5">
        <span aria-hidden="true" className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-amber-100 text-sm text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">🔔</span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-stone-800 dark:text-stone-100">Reminder</p>
          <p className="mt-0.5 text-xs leading-5 text-stone-500 dark:text-stone-400">{reminderStatus}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
        {current ? <>
          <Button aria-label={`Edit reminder for ${target.label}`} onClick={() => setOpen(true)} tone="amber" variant="secondary">Edit reminder</Button>
          <Button aria-label={`Remove reminder for ${target.label}`} disabled={state.pending} onClick={() => void state.cancel()} variant="destructive">Remove</Button>
        </> : <Button aria-label={`Set reminder for ${target.label}`} onClick={() => setOpen(true)} tone="amber" variant="secondary">Set Reminder</Button>}
      </div>
    </> : current ? <>
      <p className="text-stone-500">Reminder {Temporal.Instant.from(current.remind_at).toZonedDateTimeISO(current.timezone).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })} · {methods}</p>
      <button type="button" onClick={() => setOpen(true)} className="mr-2 text-emerald-700">Edit Reminder</button>
      <button type="button" disabled={state.pending} onClick={() => void state.cancel()} className="text-red-700">Remove Reminder</button>
    </> : <button type="button" onClick={() => setOpen(true)} className="text-emerald-700">Set Reminder</button>}
    {open && <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <form onSubmit={event => { event.preventDefault(); void save() }} className="w-full max-w-sm rounded-xl bg-white p-5 dark:bg-stone-900">
        <h3 className="text-lg font-semibold">{current ? 'Edit Reminder' : 'Set Reminder'}</h3>
        <label className="mt-4 block">Date<input type="date" value={date} onChange={event => setDate(event.target.value)} className="mt-1 w-full border p-2" required /></label>
        <label className="mt-3 block">Time<input type="time" value={time} onChange={event => setTime(event.target.value)} className="mt-1 w-full border p-2" required /></label>
        <fieldset className="mt-4">
          <legend className="font-medium">Remind me via</legend>
          <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={inAppEnabled} onChange={event => { setInAppEnabled(event.target.checked); setValidation(null) }} />In app</label>
          <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={emailEnabled} onChange={event => { setEmailEnabled(event.target.checked); setValidation(null) }} />Email</label>
          <p className="mt-2 text-stone-500">Email reminders are sent to your account email.</p>
        </fieldset>
        {validation && <p className="mt-2 text-red-700">{validation}</p>}
        {state.error && <p className="mt-2 text-red-700">{state.error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => setOpen(false)}>Cancel</button>
          <button disabled={state.pending} className="rounded bg-emerald-700 px-3 py-2 text-white">Save Reminder</button>
        </div>
      </form>
    </div>}
  </div>
}
