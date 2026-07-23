import { useState, useMemo } from 'react'
import { useAuth } from './hooks/useAuth'
import { useTheme } from './hooks/useTheme'
import { useProjects } from './hooks/useProjects'
import { useTasks } from './hooks/useTasks'
import { useTaskSearch } from './hooks/useTaskSearch'
import { useTaskFilters } from './hooks/useTaskFilters'
import { useTaskReorder } from './hooks/useTaskReorder'
import Login from './components/Login'
import Footer from './components/Footer'
import TaskCard from './components/tasks/TaskCard'
import TaskForm from './components/tasks/TaskForm'
import { TaskSearchBar } from './components/tasks/TaskSearchBar'
import { TaskFilterBar } from './components/tasks/TaskFilterBar'
import { useTaskSort } from './hooks/useTaskSort'
import { TaskSortBar } from './components/tasks/TaskSortBar'
import { DraggableTaskList } from './components/tasks/DraggableTaskList'
import { groupByPinned } from './utils/pinning'
import type { TaskStatus, TaskPriority, Task } from './lib/types/database.types'

export default function App() {
  const { user, loading: authLoading, signOut } = useAuth()

  if (authLoading) {
    return (
      <div className="flex min-h-screen flex-col">
        <main className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 text-lg">Loading...</p>
        </main>
        <Footer />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex min-h-screen flex-col bg-gray-50 dark:bg-gray-950">
        <main className="flex-1 flex items-center justify-center p-4 md:p-8">
          <Login />
        </main>
        <Footer />
      </div>
    )
  }

  return (
    <AppContent user={user} onSignOut={signOut} />
  )
}

function AppContent({ user, onSignOut }: { user: any; onSignOut: () => void }) {
  const { theme, toggleTheme } = useTheme()
  const { projects, loading: projectsLoading, addProject, updateProject, deleteProject } = useProjects()
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const { tasks, addTask, toggleTask, updateTask, deleteTask } = useTasks(selectedProjectId)
  
  // --- Pipeline: All Tasks → Search → Filters → Sort → Pin Grouping → Rendered Tasks ---
  const { filteredTasks: searchedTasks, query, setSearchQuery, clearSearch, isSearching } = useTaskSearch(tasks)
  const { filteredTasks, filters, setFilter, clearFilters, hasActiveFilters } = useTaskFilters(searchedTasks)
  const { sortedTasks, sortConfig, setSortConfig, clearSort } = useTaskSort(filteredTasks)
  const renderedTasks = useMemo(() => groupByPinned(sortedTasks), [sortedTasks])

  // --- Project form state ---
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectDescription, setNewProjectDescription] = useState('')
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null)
  const [editProjectName, setEditProjectName] = useState('')
  const [editProjectDescription, setEditProjectDescription] = useState('')

  // --- Task form state (inline editing only) ---
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editTaskTitle, setEditTaskTitle] = useState('')
  const [editTaskDescription, setEditTaskDescription] = useState('')

  // --- Project handlers ---
  const handleAddProject = async () => {
    if (!newProjectName.trim()) return
    await addProject(newProjectName.trim(), newProjectDescription.trim())
    setNewProjectName('')
    setNewProjectDescription('')
  }

  const handleSaveProjectEdit = async (id: string) => {
    if (!editProjectName.trim()) return
    await updateProject(id, editProjectName.trim(), editProjectDescription.trim())
    setEditingProjectId(null)
    setEditProjectName('')
    setEditProjectDescription('')
  }

  // --- Task handlers (object-based API only) ---
  const handleAddTask = async (title: string, description: string, priority: TaskPriority, dueDate: string | null) => {
    if (!title.trim() || !selectedProjectId) return
    await addTask({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      due_date: dueDate,
    })
  }

  const handleSaveTaskEdit = async (id: string) => {
    if (!editTaskTitle.trim()) return
    await updateTask(id, {
      title: editTaskTitle.trim(),
      description: editTaskDescription.trim(),
    })
    setEditingTaskId(null)
    setEditTaskTitle('')
    setEditTaskDescription('')
  }

  const handleUpdateTaskStatus = async (id: string, status: TaskStatus) => {
    const nextCompleted = status === 'COMPLETED'
    await updateTask(id, { status, completed: nextCompleted })
  }

  const handleUpdateTaskPriority = async (id: string, priority: TaskPriority) => {
    await updateTask(id, { priority })
  }

  const handleUpdateTaskDueDate = async (id: string, dueDate: string | null) => {
    await updateTask(id, { due_date: dueDate })
  }

  const handleTogglePin = async (id: string, currentPinned: boolean) => {
    await updateTask(id, { is_pinned: !currentPinned })
  }

  const handleToggleArchive = async (id: string, currentArchived: boolean) => {
    await updateTask(id, { is_archived: !currentArchived })
  }

  // --- Drag reorder handler ---
  const isManualSort = sortConfig.field === 'manual'
  const handleReorder = async (reorderedTasks: Task[]) => {
    // Optimistic update first
    const updates = reorderedTasks.map(task => updateTask(task.id, { order: task.order }))
    await Promise.all(updates)
  }
  
  const { handleDragEnd, dragEnabled } = useTaskReorder({
    tasks: renderedTasks,
    onReorder: handleReorder,
    isManualSort,
  })

  if (projectsLoading) {
    return (
      <div className="flex min-h-screen flex-col bg-gray-100 dark:bg-gray-900">
        <main className="flex-1 flex items-center justify-center p-4 md:p-8">
          <p className="text-gray-500 text-lg">Loading...</p>
        </main>
        <Footer />
      </div>
    )
  }

  const selectedProject = projects.find(p => p.id === selectedProjectId)

  return (
    <div className="flex min-h-screen flex-col bg-gray-100 dark:bg-gray-900">
      <main className="flex-1 p-4 md:p-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100">yapvibes</h1>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500 dark:text-gray-400">{user.email}</span>
              <button
                onClick={toggleTheme}
                className="px-3 py-1 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition cursor-pointer"
                title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              >
                {theme === 'light' ? '🌙' : '☀️'}
              </button>
              <button
                onClick={onSignOut}
                className="px-3 py-1 bg-red-500 text-white rounded-md text-sm hover:bg-red-600 transition"
              >
                Sign Out
              </button>
            </div>
          </div>

          {/* Layout */}
          <div className="flex flex-col md:flex-row gap-4">
            {/* LEFT: Projects sidebar */}
            <div className="md:w-1/3">
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                <h2 className="font-semibold text-gray-700 dark:text-gray-200 mb-3">Projects</h2>
                
                {/* Add new project */}
                <div className="mb-4 space-y-2">
                  <input
                    type="text"
                    placeholder="New project name..."
                    value={newProjectName}
                    onChange={e => setNewProjectName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddProject()}
                    className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
                  />
                  <input
                    type="text"
                    placeholder="Description (optional)..."
                    value={newProjectDescription}
                    onChange={e => setNewProjectDescription(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddProject()}
                    className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
                  />
                  <button
                    onClick={handleAddProject}
                    className="w-full px-4 py-2 bg-blue-500 text-white rounded-md text-sm hover:bg-blue-600 transition"
                  >
                    + Add Project
                  </button>
                </div>

                {/* Project list */}
                <div className="space-y-1">
                  {projects.map(project => (
                    <div
                      key={project.id}
                      className={`flex flex-col p-2 rounded-md cursor-pointer transition ${selectedProjectId === project.id ? 'bg-blue-100 dark:bg-blue-900' : 'hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                      onClick={() => setSelectedProjectId(project.id)}
                    >
                      {editingProjectId === project.id ? (
                        <div className="flex flex-col gap-1 w-full">
                          <input
                            type="text"
                            value={editProjectName}
                            onChange={e => setEditProjectName(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSaveProjectEdit(project.id)}
                            className="w-full px-2 py-1 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
                            autoFocus
                          />
                          <input
                            type="text"
                            value={editProjectDescription}
                            onChange={e => setEditProjectDescription(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSaveProjectEdit(project.id)}
                            className="w-full px-2 py-1 border rounded text-xs focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600"
                            placeholder="Description..."
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={e => { e.stopPropagation(); handleSaveProjectEdit(project.id) }}
                              className="text-green-500 hover:text-green-700 text-sm px-1 cursor-pointer"
                            >✓</button>
                            <button
                              onClick={e => { e.stopPropagation(); setEditingProjectId(null); setEditProjectName(''); setEditProjectDescription('') }}
                              className="text-gray-400 hover:text-gray-600 text-sm px-1 cursor-pointer"
                            >✕</button>
                          </div>
                        </div>
                      ) : (
                          <div className="flex items-center justify-between flex-1 group">
                            <div className="flex-1 min-w-0">
                              <span className="text-sm text-gray-700 dark:text-gray-200 block truncate">{project.name}</span>
                              {project.description && (
                                <span className="invisible group-hover:visible text-xs text-gray-400 dark:text-gray-500 block truncate transition-opacity">{project.description}</span>
                              )}
                            </div>
                          <div className="flex gap-1 ml-2">
                            <button
                              onClick={e => { e.stopPropagation(); setEditingProjectId(project.id); setEditProjectName(project.name); setEditProjectDescription(project.description || '') }}
                              className="text-gray-400 hover:text-blue-500 text-xs px-1 cursor-pointer"
                            >✏️</button>
                            <button
                              onClick={e => { e.stopPropagation(); deleteProject(project.id); if (selectedProjectId === project.id) setSelectedProjectId(null) }}
                              className="text-gray-400 hover:text-red-500 text-xs px-1 cursor-pointer"
                            >🗑️</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  {projects.length === 0 && (
                    <p className="text-gray-400 dark:text-gray-500 text-sm text-center py-4">No projects yet</p>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT: Tasks panel */}
            <div className="md:w-2/3">
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                {selectedProjectId ? (
                  <>
                    <h2 className="font-semibold text-gray-700 dark:text-gray-200 mb-1">
                      {selectedProject?.name || 'Selected Project'}
                    </h2>
                    {selectedProject?.description && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">{selectedProject.description}</p>
                    )}

                    {/* Add task form */}
                    <TaskForm onSubmit={handleAddTask} />

                    {/* Search bar */}
                    <TaskSearchBar
                      value={query}
                      onChange={setSearchQuery}
                      onClear={clearSearch}
                    />

                    {/* Filter bar */}
                    <TaskFilterBar
                      filters={filters}
                      onSetFilter={setFilter}
                      onClear={clearFilters}
                      hasActiveFilters={hasActiveFilters}
                    />

                    {/* Sort bar */}
                    <TaskSortBar
                      sortConfig={sortConfig}
                      onSetSortConfig={setSortConfig}
                      onReset={clearSort}
                    />

                    {/* Tasks list */}
                    <DraggableTaskList
                      tasks={renderedTasks}
                      onDragEnd={handleDragEnd}
                      dragEnabled={dragEnabled}
                    >
                      {(task) => (
                        <TaskCard
                          key={task.id}
                          task={task}
                          isEditing={editingTaskId === task.id}
                          editTitle={editTaskTitle}
                          editDescription={editTaskDescription}
                          onToggleComplete={() => {
                            const nextCompleted = !task.completed
                            const nextStatus = nextCompleted ? 'COMPLETED' : 'TODO'
                            toggleTask(task.id, nextCompleted)
                            handleUpdateTaskStatus(task.id, nextStatus)
                          }}
                          onStartEdit={() => { setEditingTaskId(task.id); setEditTaskTitle(task.title); setEditTaskDescription(task.description || '') }}
                          onSaveEdit={() => handleSaveTaskEdit(task.id)}
                          onCancelEdit={() => { setEditingTaskId(null); setEditTaskTitle(''); setEditTaskDescription('') }}
                          onUpdateStatus={(status) => handleUpdateTaskStatus(task.id, status)}
                          onUpdatePriority={(priority) => handleUpdateTaskPriority(task.id, priority)}
                          onUpdateDueDate={(dueDate) => handleUpdateTaskDueDate(task.id, dueDate)}
                          onTogglePin={() => handleTogglePin(task.id, task.is_pinned)}
                          onToggleArchive={() => handleToggleArchive(task.id, task.is_archived)}
                          onDelete={() => deleteTask(task.id)}
                          onChangeEditTitle={setEditTaskTitle}
                          onChangeEditDescription={setEditTaskDescription}
                        />
                      )}
                    </DraggableTaskList>

                    {renderedTasks.length === 0 && (
                      <p className="text-gray-400 dark:text-gray-500 text-sm text-center py-4">
                        {isSearching ? 'No matching tasks' : 'No tasks in this project'}
                      </p>
                    )}

                    {/* Stats */}
                    <div className="mt-4 pt-3 border-t dark:border-gray-700 flex justify-between text-xs text-gray-400 dark:text-gray-500">
                      <span>{tasks.filter(t => t.completed).length} completed</span>
                      <span>{tasks.length} total</span>
                    </div>
                  </>
                ) : (
                  <p className="text-gray-400 dark:text-gray-500 text-center py-16">Select or create a project to get started</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  )
}
