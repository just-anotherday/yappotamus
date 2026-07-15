import { useState } from 'react'
import type { TaskPriority } from '../../lib/types/database.types'

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
    <div className="space-y-2 mb-4">
      <input
        type="text"
        placeholder="New task title..."
        value={title}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
      />
      <input
        type="text"
        placeholder="Description (optional)..."
        value={description}
        onChange={e => setDescription(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
      />

      {/* Priority selector */}
      <select
        value={priority}
        onChange={e => setPriority(e.target.value as TaskPriority)}
        className="px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600 cursor-pointer"
      >
        <option value="LOW">Priority: Low</option>
        <option value="MEDIUM">Priority: Medium</option>
        <option value="HIGH">Priority: High</option>
      </select>

      {/* Due date picker */}
      <input
        type="date"
        value={dueDate}
        onChange={e => setDueDate(e.target.value)}
        className="px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
      />

      <button
        onClick={handleSubmit}
        className="w-full px-4 py-2 bg-green-500 text-white rounded-md text-sm hover:bg-green-600 transition"
      >
        + Add Task
      </button>
    </div>
  )
}
