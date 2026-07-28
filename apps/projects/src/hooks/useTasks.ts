import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type {
  Task,
  TaskMetadata,
  TaskPriority,
  TaskStatus,
} from '../lib/types/database.types'

export interface AddTaskOptions {
  title: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  due_date?: string | null
  is_pinned?: boolean
  is_archived?: boolean
  metadata?: TaskMetadata
}

export interface UpdateTaskOptions {
  title?: string
  description?: string
  completed?: boolean
  status?: TaskStatus
  priority?: TaskPriority
  due_date?: string | null
  is_pinned?: boolean
  is_archived?: boolean
  order?: number
  metadata?: TaskMetadata
}

function normalizeTask(task: Omit<Task, 'metadata'> & { metadata?: TaskMetadata }): Task {
  return { ...task, metadata: task.metadata ?? {} }
}

export function useTasks(projectId: string | null) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTasks = useCallback(async () => {
    if (!projectId) {
      setTasks([])
      setLoading(false)
      return
    }

    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      setLoading(false)
      return
    }

    const { data, error: fetchError } = await supabase
      .from('tasks')
      .select('*')
      .eq('project_id', projectId)
      .eq('user_id', user.id)
      .order('order', { ascending: true })

    if (fetchError) {
      setError(fetchError.message)
    } else if (data) {
      setTasks(data.map(normalizeTask))
      setError(null)
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => {
    setLoading(true)
    fetchTasks()

    if (!projectId) return

    const channel = supabase
      .channel(`tasks-${projectId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, fetchTasks)
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [fetchTasks, projectId])

  const addTask = async (options: AddTaskOptions | string, description?: string) => {
    if (!projectId) return
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const normalizedOptions: AddTaskOptions = typeof options === 'string'
      ? { title: options, description }
      : options
    const maxOrder = tasks.length > 0 ? Math.max(...tasks.map(task => task.order)) : -1

    const insertData: Record<string, unknown> = {
      project_id: projectId,
      title: normalizedOptions.title,
      description: normalizedOptions.description || '',
      order: maxOrder + 1,
      user_id: user.id,
    }

    if (normalizedOptions.status !== undefined) insertData.status = normalizedOptions.status
    if (normalizedOptions.priority !== undefined) insertData.priority = normalizedOptions.priority
    if (normalizedOptions.due_date !== undefined) insertData.due_date = normalizedOptions.due_date
    if (normalizedOptions.is_pinned !== undefined) insertData.is_pinned = normalizedOptions.is_pinned
    if (normalizedOptions.is_archived !== undefined) insertData.is_archived = normalizedOptions.is_archived
    if (normalizedOptions.metadata !== undefined) insertData.metadata = normalizedOptions.metadata

    const { error: insertError } = await supabase.from('tasks').insert(insertData)
    if (insertError) setError(insertError.message)
    await fetchTasks()
  }

  const updateTask = async (
    id: string,
    options: UpdateTaskOptions | string,
    description?: string,
  ) => {
    const updates: Record<string, unknown> = {}

    if (typeof options === 'string') {
      updates.title = options
      if (description !== undefined) updates.description = description
    } else {
      for (const [key, value] of Object.entries(options)) {
        if (value !== undefined) updates[key] = value
      }
    }

    if (Object.keys(updates).length === 0) return

    setTasks(previous => previous.map(task => (
      task.id === id ? { ...task, ...updates } as Task : task
    )))

    const { error: updateError } = await supabase.from('tasks').update(updates).eq('id', id)
    if (updateError) setError(updateError.message)
    await fetchTasks()
  }

  const toggleTask = async (id: string, completed: boolean) => {
    await updateTask(id, {
      completed,
      status: completed ? 'COMPLETED' : 'TODO',
    })
  }

  const deleteTask = async (id: string) => {
    setTasks(previous => previous.filter(task => task.id !== id))
    const { error: deleteError } = await supabase.from('tasks').delete().eq('id', id)
    if (deleteError) setError(deleteError.message)
    await fetchTasks()
  }

  const deleteTasks = async (ids: string[]) => {
    if (ids.length === 0) return
    setTasks(previous => previous.filter(task => !ids.includes(task.id)))
    const { error: deleteError } = await supabase.from('tasks').delete().in('id', ids)
    if (deleteError) setError(deleteError.message)
    await fetchTasks()
  }

  return {
    tasks,
    loading,
    error,
    addTask,
    toggleTask,
    updateTask,
    deleteTask,
    deleteTasks,
  }
}
