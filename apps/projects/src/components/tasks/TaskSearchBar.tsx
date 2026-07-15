import { useState, useEffect } from 'react'

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
    if (inputValue !== value) {
      setInputValue(value)
    }
  }, [value])
  
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
        onChange={(e) => setInputValue(e.target.value)}
        className="w-full px-4 py-2.5 rounded-lg border dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
      {value && (
        <button
          onClick={() => {
            setInputValue('')
            onClear()
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
        >
          ✕
        </button>
      )}
    </div>
  )
}
