import type { SortConfig, SortField } from '../../utils/sorting'

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

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-500 dark:text-gray-400">Sort</span>
        {!isDefault && (
          <button
            onClick={onReset}
            className="text-xs text-blue-500 hover:text-blue-700 dark:hover:text-blue-300 transition cursor-pointer"
          >
            Reset sort
          </button>
        )}
      </div>

      <div className="flex gap-2 items-center">
        {/* Sort Field */}
        <select
          value={sortConfig.field}
          onChange={e => onSetSortConfig({ ...sortConfig, field: e.target.value as SortField })}
          className="flex-1 px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {SORT_FIELD_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* Direction Toggle (disabled for manual) */}
        <button
          onClick={() => onSetSortConfig({ ...sortConfig, direction: sortConfig.direction === 'asc' ? 'desc' : 'asc' })}
          disabled={sortConfig.field === 'manual'}
          className={`px-3 py-2 text-sm rounded-md border dark:bg-gray-700 dark:border-gray-600 dark:text-white transition cursor-pointer ${
            sortConfig.field === 'manual'
              ? 'opacity-40 cursor-not-allowed'
              : 'hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500'
          }`}
          title={sortConfig.direction === 'asc' ? 'Ascending' : 'Descending'}
        >
          {sortConfig.direction === 'asc' ? '↑' : '↓'}
        </button>
      </div>
    </div>
  )
}
