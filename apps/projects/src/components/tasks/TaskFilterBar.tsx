import type { TaskFilters } from '../../utils/filters'
import { Button } from '../shared/Button'

interface TaskFilterBarProps {
  filters: TaskFilters
  onSetFilter: <K extends keyof TaskFilters>(key: K, value: TaskFilters[K]) => void
  onClear: () => void
  hasActiveFilters: boolean
}

const STATUS_OPTIONS = [
  { value: 'ALL', label: 'All' },
  { value: 'TODO', label: 'Todo' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'COMPLETED', label: 'Completed' },
] as const

const PRIORITY_OPTIONS = [
  { value: 'ALL', label: 'All Priorities' },
  { value: 'LOW', label: 'Low' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HIGH', label: 'High' },
] as const

const DUEDATE_OPTIONS = [
  { value: 'ALL', label: 'All Dates' },
  { value: 'DUE_TODAY', label: 'Due Today' },
  { value: 'OVERDUE', label: 'Overdue' },
  { value: 'NO_DUE_DATE', label: 'No Due Date' },
] as const

const fieldClass = 'min-h-10 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100'

export function TaskFilterBar({ filters, onSetFilter, onClear, hasActiveFilters }: TaskFilterBarProps) {
  return (
    <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50/70 p-3 dark:border-stone-800 dark:bg-stone-900/60">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-stone-600 dark:text-stone-300">Filters</span>
        {hasActiveFilters && <Button onClick={onClear} tone="emerald" variant="tertiary" className="min-h-8 px-2 py-1 text-xs">Clear filters</Button>}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <select value={filters.status} onChange={e => onSetFilter('status', e.target.value as TaskFilters['status'])} className={fieldClass}>
          {STATUS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
        <select value={filters.priority} onChange={e => onSetFilter('priority', e.target.value as TaskFilters['priority'])} className={fieldClass}>
          {PRIORITY_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
        <select value={filters.dueDate} onChange={e => onSetFilter('dueDate', e.target.value as TaskFilters['dueDate'])} className={fieldClass}>
          {DUEDATE_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
        <label className={`${fieldClass} flex items-center gap-2`}>
          <input type="checkbox" checked={filters.showArchived} onChange={e => onSetFilter('showArchived', e.target.checked)} className="rounded border-stone-300 text-emerald-700 focus:ring-2 focus:ring-emerald-600/30 dark:border-stone-700" />
          <span>Show Archived</span>
        </label>
      </div>
    </div>
  )
}
