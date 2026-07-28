import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { Project, ProjectKind } from '../lib/types/database.types'

function normalizeProject(project: Omit<Project, 'kind'> & { kind?: ProjectKind }): Project {
  return { ...project, kind: project.kind ?? 'board' }
}

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProjects = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      setLoading(false)
      return
    }

    const { data, error: fetchError } = await supabase
      .from('projects')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })

    if (fetchError) {
      setError(fetchError.message)
    } else if (data) {
      setProjects(data.map(normalizeProject))
      setError(null)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchProjects()

    const channel = supabase
      .channel('projects')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'projects' }, fetchProjects)
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  const addProject = async (name: string, description?: string, kind: ProjectKind = 'board') => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return null

    const { data, error: insertError } = await supabase
      .from('projects')
      .insert({ name, description: description || '', kind, user_id: user.id })
      .select()
      .single()

    if (insertError) {
      setError(insertError.message)
      return null
    }

    await fetchProjects()
    return data ? normalizeProject(data) : null
  }

  const updateProject = async (
    id: string,
    name: string,
    description?: string,
    kind?: ProjectKind,
  ) => {
    const updates = { name, description, ...(kind ? { kind } : {}) }
    setProjects(previous => previous.map(project => (
      project.id === id ? { ...project, ...updates } : project
    )))

    const { error: updateError } = await supabase
      .from('projects')
      .update(updates)
      .eq('id', id)

    if (updateError) setError(updateError.message)
    await fetchProjects()
  }

  const deleteProject = async (id: string) => {
    await supabase.from('tasks').delete().eq('project_id', id)
    const { error: deleteError } = await supabase.from('projects').delete().eq('id', id)
    if (deleteError) setError(deleteError.message)
    await fetchProjects()
  }

  return { projects, loading, error, addProject, updateProject, deleteProject }
}
