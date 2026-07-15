export interface Project {
  id: string
  name: string
  description?: string
  user_id: string
  created_at: string
}

export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'COMPLETED'
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH'

export interface Task {
  id: string
  project_id: string
  title: string
  description?: string
  
  // Legacy field (keep for backward compatibility)
  completed: boolean
  
  // New fields from Phase 1B
  status: TaskStatus
  priority: TaskPriority
  due_date?: string | null
  is_pinned: boolean
  is_archived: boolean
  updated_at: string
  
  order: number
  user_id: string
  created_at: string
}

export interface Database {
  public: {
    Tables: {
      projects: {
        Row: Project
        Insert: Omit<Project, 'id' | 'created_at'>
        Update: Partial<Project>
      }
      tasks: {
        Row: Task
        Insert: Omit<Task, 'id' | 'created_at' | 'updated_at' | 'status' | 'priority' | 'is_pinned' | 'is_archived'>
        Update: Partial<Task>
      }
    }
  }
}
