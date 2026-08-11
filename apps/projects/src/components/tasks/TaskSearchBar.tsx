import { useEffect, useState } from 'react'
import { IconButton } from '../shared/IconButton'

interface TaskSearchBarProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  resultCount?: number
}

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

export function TaskSearchBar({ value, onChange, onClear }: TaskSearchBarProps) {
  const [inputValue, setInputValue] = useState(value)

  useEffect(() => {
    if (inputValue !== value) setInputValue(value)
  }, [inputValue, value])

  const debouncedValue = useDebouncedValue(inputValue, 300)

  useEffect(() => {
    onChange(debouncedValue)
  }, [debouncedValue, onChange])

  return (
    <div className="relative mb-4">
      <input
        type="text"
        placeholder="Search tasks..."
        value={inputValue}
        onChange={e => setInputValue(e.target.value)}
        className="min-h-10 w-full rounded-lg border border-stone-300 bg-white px-3 pr-12 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
      />
      {value && (
        <IconButton
          onClick={() => { setInputValue(''); onClear() }}
          ariaLabel="Clear task search"
          tone="emerald"
          className="absolute right-1 top-1/2 size-8 min-h-8 -translate-y-1/2 text-base"
        >
          ×
        </IconButton>
      )}
    </div>
  )
}
