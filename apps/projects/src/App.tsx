import { useEffect, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import Footer from './components/Footer'
import Login from './components/Login'
import { BoardProject } from './components/projects/BoardProject'
import { ProjectDialog } from './components/projects/ProjectDialog'
import { ProjectDirectoryHeader } from './components/projects/ProjectDirectoryHeader'
import { RecipeBookProject } from './components/projects/RecipeBookProject'
import { ShoppingListProject } from './components/projects/ShoppingListProject'
import { useAuth } from './hooks/useAuth'
import { useProjects } from './hooks/useProjects'
import { useTasks } from './hooks/useTasks'
import { useTheme } from './hooks/useTheme'
import type { ProjectKind } from './lib/types/database.types'

const projectLabels = {
  board: 'Task board',
  shopping: 'Shopping list',
  recipes: 'Recipe book',
} as const

const projectAccents = {
  board: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
  shopping: 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300',
  recipes: 'bg-orange-100 text-orange-800 dark:bg-orange-950/50 dark:text-orange-300',
} as const

export default function App() {
  const { user, loading: authLoading, signOut } = useAuth()

  if (authLoading) return <LoadingScreen label="Opening your project directory…" />

  if (!user) {
    return (
      <div className="flex min-h-screen flex-col bg-stone-100 dark:bg-stone-950">
        <main className="flex flex-1 items-center justify-center p-4 md:p-8"><Login /></main>
        <Footer />
      </div>
    )
  }

  return <AppContent user={user} onSignOut={signOut} />
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen flex-col bg-stone-100 dark:bg-stone-950">
      <main className="grid flex-1 place-items-center p-4">
        <div className="text-center">
          <div className="mx-auto mb-3 size-8 animate-pulse rounded-lg bg-emerald-700" />
          <p className="text-sm font-medium text-stone-500">{label}</p>
        </div>
      </main>
      <Footer />
    </div>
  )
}

function AppContent({ user, onSignOut }: { user: User; onSignOut: () => Promise<unknown> }) {
  const { theme, toggleTheme } = useTheme()
  const {
    projects,
    loading: projectsLoading,
    error: projectsError,
    addProject,
    updateProject,
    deleteProject,
  } = useProjects()
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [dialogMode, setDialogMode] = useState<'create' | 'edit' | null>(null)
  const [suggestedKind, setSuggestedKind] = useState<ProjectKind>('board')
  const {
    tasks,
    loading: tasksLoading,
    error: tasksError,
    addTask,
    toggleTask,
    updateTask,
    deleteTask,
    deleteTasks,
  } = useTasks(selectedProjectId)

  useEffect(() => {
    if (projects.length === 0) {
      setSelectedProjectId(null)
    } else if (!selectedProjectId || !projects.some(project => project.id === selectedProjectId)) {
      setSelectedProjectId(projects[0].id)
    }
  }, [projects, selectedProjectId])

  const selectedProject = projects.find(project => project.id === selectedProjectId)

  const saveProject = async (name: string, description: string, kind: ProjectKind) => {
    if (dialogMode === 'create') {
      const project = await addProject(name, description, kind)
      if (!project) return
      setSelectedProjectId(project.id)
    } else if (selectedProject) {
      await updateProject(selectedProject.id, name, description)
    }
    setDialogMode(null)
  }

  const removeProject = async () => {
    if (!selectedProject) return
    await deleteProject(selectedProject.id)
    setSelectedProjectId(null)
    setDialogMode(null)
  }

  if (projectsLoading) return <LoadingScreen label="Loading projects…" />

  return (
    <div className="flex min-h-screen flex-col bg-stone-100 text-stone-950 dark:bg-stone-950 dark:text-stone-50">
      <ProjectDirectoryHeader
        projects={projects}
        selectedProjectId={selectedProjectId}
        userEmail={user.email}
        theme={theme}
        onSelect={setSelectedProjectId}
        onCreate={() => {
          setSuggestedKind('board')
          setDialogMode('create')
        }}
        onEdit={() => selectedProject && setDialogMode('edit')}
        onToggleTheme={toggleTheme}
        onSignOut={onSignOut}
      />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {(projectsError || tasksError) && (
          <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            <strong>Could not sync this directory.</strong> {projectsError || tasksError}
          </div>
        )}

        {selectedProject ? (
          <section className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 sm:p-7">
            <div className="mb-6 flex flex-col gap-3 border-b border-stone-200 pb-5 dark:border-stone-800 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-[0.12em] ${projectAccents[selectedProject.kind]}`}>
                  {projectLabels[selectedProject.kind]}
                </span>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight text-stone-950 dark:text-white">{selectedProject.name}</h2>
                {selectedProject.description && (
                  <p className="mt-1 max-w-3xl text-stone-500 dark:text-stone-400">{selectedProject.description}</p>
                )}
              </div>
              <p className="text-xs text-stone-400">{tasks.length} {tasks.length === 1 ? 'entry' : 'entries'} · synced</p>
            </div>

            {tasksLoading ? (
              <div className="grid min-h-80 place-items-center text-sm text-stone-500">Loading project entries…</div>
            ) : selectedProject.kind === 'shopping' ? (
              <ShoppingListProject
                tasks={tasks}
                onAddTask={addTask}
                onToggleTask={toggleTask}
                onUpdateTask={updateTask}
                onDeleteTask={deleteTask}
                onDeleteTasks={deleteTasks}
              />
            ) : selectedProject.kind === 'recipes' ? (
              <RecipeBookProject tasks={tasks} onAddTask={addTask} onUpdateTask={updateTask} onDeleteTask={deleteTask} />
            ) : (
              <BoardProject
                tasks={tasks}
                onAddTask={addTask}
                onToggleTask={toggleTask}
                onUpdateTask={updateTask}
                onDeleteTask={deleteTask}
              />
            )}
          </section>
        ) : (
          <EmptyDirectory onCreate={kind => {
            setSuggestedKind(kind)
            setDialogMode('create')
          }} />
        )}
      </main>

      <Footer />
      <ProjectDialog
        open={dialogMode !== null}
        mode={dialogMode ?? 'create'}
        project={dialogMode === 'edit' ? selectedProject : undefined}
        initialKind={suggestedKind}
        error={projectsError}
        onClose={() => setDialogMode(null)}
        onSave={saveProject}
        onDelete={dialogMode === 'edit' ? removeProject : undefined}
      />
    </div>
  )
}

function EmptyDirectory({ onCreate }: { onCreate: (kind: ProjectKind) => void }) {
  const cards: Array<{ kind: ProjectKind; title: string; description: string }> = [
    { kind: 'board', title: 'Task board', description: 'Keep the workflow view you already use for technical projects.' },
    { kind: 'shopping', title: 'Shopping list', description: 'Group groceries by category, add quantities, and check items off.' },
    { kind: 'recipes', title: 'Recipe book', description: 'Save ingredients, cooking times, and step-by-step instructions.' },
  ]

  return (
    <section className="rounded-3xl border border-stone-200 bg-white p-7 shadow-sm dark:border-stone-800 dark:bg-stone-900 sm:p-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-400">One home for many kinds of work</p>
      <h2 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight text-stone-950 dark:text-white">Build your personal project directory.</h2>
      <p className="mt-3 max-w-2xl leading-7 text-stone-600 dark:text-stone-300">
        Your existing Jira-style board becomes one project. Add lists and recipe instructions beside it, then switch from the menu above.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {cards.map(card => (
          <button
            key={card.kind}
            type="button"
            onClick={() => onCreate(card.kind)}
            className="rounded-2xl border border-stone-200 p-5 text-left transition hover:-translate-y-0.5 hover:border-emerald-400 hover:shadow-md dark:border-stone-700 dark:hover:border-emerald-700"
          >
            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-[0.12em] ${projectAccents[card.kind]}`}>
              {projectLabels[card.kind]}
            </span>
            <span className="mt-5 block text-xl font-semibold text-stone-900 dark:text-white">{card.title}</span>
            <span className="mt-2 block text-sm leading-6 text-stone-500 dark:text-stone-400">{card.description}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
