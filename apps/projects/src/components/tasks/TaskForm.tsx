import { useState } from 'react'
import type { TaskPriority } from '../../lib/types/database.types'
import { Button } from '../shared/Button'

interface TaskFormProps {
  onSubmit: (title: string, description: string, priority: TaskPriority, dueDate: string | null) => void
}

export default function TaskForm({ onSubmit }: TaskFormProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<TaskPriority>('MEDIUM')
  const [dueDate, setDueDate] = useState('')

  const handleSubmit = () => {
    onSubmit(title, description, priority, dueDate || null)
    setTitle('')
    setDescription('')
    setPriority('MEDIUM')
    setDueDate('')
  }

  return (
    <div className="mb-4 space-y-3">
      <input
        type="text"
        placeholder="New task title..."
        value={title}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
      />
      <input
        type="text"
        placeholder="Description (optional)..."
        value={description}
        onChange={e => setDescription(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <select
          value={priority}
          onChange={e => setPriority(e.target.value as TaskPriority)}
          className="min-h-10 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
        >
          <option value="LOW">Priority: Low</option>
          <option value="MEDIUM">Priority: Medium</option>
          <option value="HIGH">Priority: High</option>
        </select>
        <input
          type="date"
          value={dueDate}
          onChange={e => setDueDate(e.target.value)}
          className="min-h-10 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
        />
      </div>

      <Button onClick={handleSubmit} tone="emerald" variant="primary" className="w-full">Add task</Button>
    </div>
  )
}
