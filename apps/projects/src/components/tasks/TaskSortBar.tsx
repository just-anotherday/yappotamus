import type { SortConfig, SortField } from '../../utils/sorting'
import { Button } from '../shared/Button'
import { IconButton } from '../shared/IconButton'

interface TaskSortBarProps {
  sortConfig: SortConfig
  onSetSortConfig: (config: SortConfig) => void
  onReset: () => void
}

const SORT_FIELD_OPTIONS = [
  { value: 'manual', label: 'Manual Order' },
  { value: 'dueDate', label: 'Due Date' },
  { value: 'priority', label: 'Priority' },
  { value: 'createdAt', label: 'Created' },
  { value: 'updatedAt', label: 'Updated' },
  { value: 'alphabetical', label: 'Alphabetical' },
] as const

export function TaskSortBar({ sortConfig, onSetSortConfig, onReset }: TaskSortBarProps) {
  const isDefault = sortConfig.field === 'manual' && sortConfig.direction === 'asc'
  const ascending = sortConfig.direction === 'asc'

  return (
    <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50/70 p-3 dark:border-stone-800 dark:bg-stone-900/60">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-stone-600 dark:text-stone-300">Sort</span>
        {!isDefault && <Button onClick={onReset} tone="emerald" variant="tertiary" className="min-h-8 px-2 py-1 text-xs">Reset sort</Button>}
      </div>

      <div className="flex items-center gap-2">
        <select
          value={sortConfig.field}
          onChange={e => onSetSortConfig({ ...sortConfig, field: e.target.value as SortField })}
          className="min-h-10 min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
        >
          {SORT_FIELD_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
        <IconButton
          onClick={() => onSetSortConfig({ ...sortConfig, direction: ascending ? 'desc' : 'asc' })}
          disabled={sortConfig.field === 'manual'}
          ariaLabel={ascending ? 'Sort ascending' : 'Sort descending'}
          title={ascending ? 'Ascending' : 'Descending'}
          tone="emerald"
        >
          {ascending ? '↑' : '↓'}
        </IconButton>
      </div>
    </div>
  )
}
