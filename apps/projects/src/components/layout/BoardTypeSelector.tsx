import { boardTypeOptions, type BoardType } from '../../types/boards'

interface BoardTypeSelectorProps {
  value: BoardType
  onChange: (value: BoardType) => void
}

export function BoardTypeSelector({ value, onChange }: BoardTypeSelectorProps) {
  return (
    <label className="flex min-w-56 flex-1 items-center gap-3 lg:max-w-xs">
      <span className="shrink-0 text-sm font-semibold text-stone-600 dark:text-stone-300">
        Project
      </span>
      <select
        aria-label="Project type"
        value={value}
        onChange={event => onChange(event.target.value as BoardType)}
        className="h-10 min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 text-sm font-semibold text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      >
        {boardTypeOptions.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  )
}
