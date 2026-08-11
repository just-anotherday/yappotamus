import { useEffect, useRef, useState } from 'react'
import { Temporal } from '@js-temporal/polyfill'
import { useUserSettings } from '../../hooks/useUserSettings'
import { useEntityReminder } from '../../hooks/useEntityReminder'
import type { ReminderTarget } from '../../types/reminders'
import { Button, type ButtonTone } from '../shared/Button'
import { DialogFrame } from '../shared/DialogFrame'

const reminderTone: Record<ReminderTarget['kind'], ButtonTone> = {
  task: 'emerald',
  shopping_project: 'amber',
  recipe: 'orange',
}

const reminderAccent: Record<ReminderTarget['kind'], string> = {
  task: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
  shopping_project: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  recipe: 'bg-orange-100 text-orange-800 dark:bg-orange-950/60 dark:text-orange-300',
}

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
  const dateInputRef = useRef<HTMLInputElement>(null)
  const tone = reminderTone[target.kind]

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
  const reminderStatus = current
    ? `Scheduled ${Temporal.Instant.from(current.remind_at).toZonedDateTimeISO(current.timezone).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })} · ${methods}`
    : 'No reminder set'

  return (
    <>
      <section className="flex w-full flex-col gap-3 rounded-xl border border-stone-200 bg-stone-50/80 px-3 py-3 dark:border-stone-800 dark:bg-stone-900/60 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2.5">
          <span aria-hidden="true" className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg text-sm ${reminderAccent[target.kind]}`}>🔔</span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-800 dark:text-stone-100">Reminder</p>
            <p className="mt-0.5 text-xs leading-5 text-stone-500 dark:text-stone-400">{reminderStatus}</p>
            {state.error && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{state.error}</p>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
          {current ? (
            <>
              <Button aria-label={`Edit reminder for ${target.label}`} onClick={() => setOpen(true)} disabled={state.pending} tone={tone} variant="secondary">Edit reminder</Button>
              <Button aria-label={`Remove reminder for ${target.label}`} disabled={state.pending} onClick={() => void state.cancel()} variant="destructive">Remove</Button>
            </>
          ) : <Button aria-label={`Set reminder for ${target.label}`} onClick={() => setOpen(true)} disabled={state.pending} tone={tone} variant="secondary">Set Reminder</Button>}
        </div>
      </section>

      {open && (
        <DialogFrame labelledBy="reminder-dialog-title" pending={state.pending} onClose={() => setOpen(false)} initialFocusRef={dateInputRef} className="my-6 w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
          <form onSubmit={event => { event.preventDefault(); void save() }}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className={`text-xs font-semibold uppercase tracking-[0.16em] ${tone === 'emerald' ? 'text-emerald-700 dark:text-emerald-300' : tone === 'amber' ? 'text-amber-800 dark:text-amber-300' : 'text-orange-700 dark:text-orange-300'}`}>Reminder</p>
                <h3 id="reminder-dialog-title" className="mt-1 text-xl font-semibold text-stone-950 dark:text-white">{current ? 'Edit Reminder' : 'Set Reminder'}</h3>
              </div>
              <Button type="button" onClick={() => setOpen(false)} disabled={state.pending} tone={tone} variant="tertiary" className="px-3">Close</Button>
            </div>
            <label className="mt-5 block text-sm font-medium text-stone-700 dark:text-stone-200">Date
              <input ref={dateInputRef} type="date" value={date} onChange={event => setDate(event.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-white" required />
            </label>
            <label className="mt-4 block text-sm font-medium text-stone-700 dark:text-stone-200">Time
              <input type="time" value={time} onChange={event => setTime(event.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-white" required />
            </label>
            <fieldset className="mt-5">
              <legend className="text-sm font-medium text-stone-700 dark:text-stone-200">Remind me via</legend>
              <label className="mt-3 flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={inAppEnabled} onChange={event => { setInAppEnabled(event.target.checked); setValidation(null) }} />In app</label>
              <label className="mt-2 flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={emailEnabled} onChange={event => { setEmailEnabled(event.target.checked); setValidation(null) }} />Email</label>
              <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">Email reminders are sent to your account email.</p>
            </fieldset>
            {validation && <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">{validation}</p>}
            {state.error && <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">{state.error}</p>}
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <Button type="button" onClick={() => setOpen(false)} disabled={state.pending} tone={tone} variant="secondary">Cancel</Button>
              <Button type="submit" disabled={state.pending} tone={tone} variant="primary">{state.pending ? 'Saving…' : 'Save Reminder'}</Button>
            </div>
          </form>
        </DialogFrame>
      )}
    </>
  )
}
