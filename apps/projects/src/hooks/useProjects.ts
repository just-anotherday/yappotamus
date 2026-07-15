import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { Project } from '../lib/types/database.types'

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  const fetchProjects = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { setLoading(false); return }

    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
    if (!error && data) setProjects(data)
    setLoading(false)
  }

  useEffect(() => {
    fetchProjects()

    // Real-time subscription for changes
    const channel = supabase
      .channel('projects')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'projects' }, () => {
        fetchProjects()
      })
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  const addProject = async (name: string, description?: string) => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return
    await supabase.from('projects').insert({ name, description: description || '', user_id: user.id })
    await fetchProjects()
  }

  const updateProject = async (id: string, name: string, description?: string) => {
    // Optimistic update
    setProjects(prev => prev.map(project => project.id === id ? { ...project, name, description: description ?? project.description } : project))
    
    // Sync with server
    await supabase.from('projects').update({ name, description }).eq('id', id)
    await fetchProjects()
  }

  const deleteProject = async (id: string) => {
    // First delete all tasks in the project to avoid foreign key constraint error
    await supabase.from('tasks').delete().eq('project_id', id)
    
    // Then delete the project itself
    await supabase.from('projects').delete().eq('id', id)
    await fetchProjects()
  }

  return { projects, loading, addProject, updateProject, deleteProject }
}
