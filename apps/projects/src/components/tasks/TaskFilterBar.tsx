import type { TaskFilters } from '../../utils/filters'

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

export function TaskFilterBar({ filters, onSetFilter, onClear, hasActiveFilters }: TaskFilterBarProps) {
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-500 dark:text-gray-400">Filters</span>
        {hasActiveFilters && (
          <button
            onClick={onClear}
            className="text-xs text-blue-500 hover:text-blue-700 dark:hover:text-blue-300 transition cursor-pointer"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {/* Status */}
        <select
          value={filters.status}
          onChange={e => onSetFilter('status', e.target.value as TaskFilters['status'])}
          className="px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* Priority */}
        <select
          value={filters.priority}
          onChange={e => onSetFilter('priority', e.target.value as TaskFilters['priority'])}
          className="px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {PRIORITY_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* Due Date */}
        <select
          value={filters.dueDate}
          onChange={e => onSetFilter('dueDate', e.target.value as TaskFilters['dueDate'])}
          className="px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {DUEDATE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* Show Archived */}
        <label className="flex items-center gap-2 px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.showArchived}
            onChange={e => onSetFilter('showArchived', e.target.checked)}
            className="rounded focus:ring-2 focus:ring-blue-500"
          />
          <span className="dark:text-white">Show Archived</span>
        </label>
      </div>
    </div>
  )
}
