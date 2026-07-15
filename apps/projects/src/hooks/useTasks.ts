import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { Task, TaskStatus, TaskPriority } from '../lib/types/database.types'

interface AddTaskOptions {
  title: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  due_date?: string | null
  is_pinned?: boolean
  is_archived?: boolean
}

interface UpdateTaskOptions {
  title?: string
  description?: string
  completed?: boolean
  status?: TaskStatus
  priority?: TaskPriority
  due_date?: string | null
  is_pinned?: boolean
  is_archived?: boolean
  order?: number
}

export function useTasks(projectId: string | null) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  const fetchTasks = async () => {
    if (!projectId) {
      setTasks([])
      setLoading(false)
      return
    }
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { setLoading(false); return }

    const { data, error } = await supabase
      .from('tasks')
      .select('*')
      .eq('project_id', projectId)
      .eq('user_id', user.id)
      .order('order', { ascending: true })
    if (!error && data) setTasks(data)
    setLoading(false)
  }

  useEffect(() => {
    fetchTasks()

    // Real-time subscription for changes
    if (projectId) {
      const channel = supabase
        .channel(`tasks-${projectId}`)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, () => {
          fetchTasks()
        })
        .subscribe()

      return () => {
        supabase.removeChannel(channel)
      }
    }
  }, [projectId])

  const addTask = async (options: AddTaskOptions | string, description?: string) => {
    if (!projectId) return
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    // Support both old signature (title, description?) and new signature (options)
    let title: string
    let taskDescription: string = ''
    let taskStatus: TaskStatus | undefined
    let taskPriority: TaskPriority | undefined
    let taskDueDate: string | null | undefined
    let taskPinned: boolean | undefined
    let taskArchived: boolean | undefined

    if (typeof options === 'string') {
      title = options
      taskDescription = description || ''
    } else {
      title = options.title
      taskDescription = options.description || ''
      taskStatus = options.status
      taskPriority = options.priority
      taskDueDate = options.due_date
      taskPinned = options.is_pinned
      taskArchived = options.is_archived
    }

    const maxOrder = tasks.length > 0 ? Math.max(...tasks.map(i => i.order)) : -1
    
    const insertData: Record<string, any> = {
      project_id: projectId,
      title,
      description: taskDescription,
      order: maxOrder + 1,
      user_id: user.id,
    }

    if (taskStatus) insertData.status = taskStatus
    if (taskPriority) insertData.priority = taskPriority
    if (taskDueDate !== undefined) insertData.due_date = taskDueDate
    if (taskPinned !== undefined) insertData.is_pinned = taskPinned
    if (taskArchived !== undefined) insertData.is_archived = taskArchived

    await supabase.from('tasks').insert(insertData)
    await fetchTasks()
  }

  const toggleTask = async (id: string, nextCompleted: boolean) => {
    // Optimistic update for immediate UI feedback
    setTasks(prev => prev.map(task => task.id === id ? { ...task, completed: nextCompleted } : task))
    
    // Sync with server
    await supabase.from('tasks').update({ completed: nextCompleted }).eq('id', id)
    await fetchTasks()
  }

  const updateTask = async (id: string, options: UpdateTaskOptions | string, description?: string) => {
    // Build updates object
    const updates: Record<string, any> = {}

    if (typeof options === 'string') {
      // Legacy signature: updateTask(id, title, description?)
      if (options !== undefined) updates.title = options
      if (description !== undefined) updates.description = description
    } else {
      // New signature: updateTask(id, options)
      if (options.title !== undefined) updates.title = options.title
      if (options.description !== undefined) updates.description = options.description
      if (options.completed !== undefined) updates.completed = options.completed
      if (options.status !== undefined) updates.status = options.status
      if (options.priority !== undefined) updates.priority = options.priority
      if (options.due_date !== undefined) updates.due_date = options.due_date
      if (options.is_pinned !== undefined) updates.is_pinned = options.is_pinned
      if (options.is_archived !== undefined) updates.is_archived = options.is_archived
      if (options.order !== undefined) updates.order = options.order
    }

    // Optimistic update - only if there are changes to apply
    if (Object.keys(updates).length > 0) {
      setTasks(prev => prev.map(task => task.id === id ? { ...task, ...updates } : task))
      
      // Sync with server
      await supabase.from('tasks').update(updates).eq('id', id)
    }
    
    await fetchTasks()
  }

  const deleteTask = async (id: string) => {
    // Optimistic update for immediate UI feedback
    setTasks(prev => prev.filter(task => task.id !== id))
    
    // Sync with server
    await supabase.from('tasks').delete().eq('id', id)
    await fetchTasks()
  }

  return { tasks, loading, addTask, toggleTask, updateTask, deleteTask }
}