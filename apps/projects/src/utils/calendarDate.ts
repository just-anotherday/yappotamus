const calendarDatePattern = /^\d{4}-\d{2}-\d{2}$/
const monthNames = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31
}

export function isCalendarDate(value: string): boolean {
  if (!calendarDatePattern.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month)
}

export function formatCalendarDate(value: string): string {
  if (!isCalendarDate(value)) return ''
  const [year, month, day] = value.split('-').map(Number)
  return `${monthNames[month - 1]} ${day}, ${year}`
}

export function currentCalendarDate(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function legacyDueDateFromDueOn(dueOn: string | null): string | null {
  return dueOn === null ? null : `${dueOn}T00:00:00.000Z`
}
