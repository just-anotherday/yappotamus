import { useCallback, useEffect, useRef, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import Footer from './components/Footer'
import Login from './components/Login'
import { OrganizerShell } from './components/layout/OrganizerShell'
import { ProjectsView } from './components/projects/ProjectsView'
import { RecipeBooksView } from './components/recipes/RecipeBooksView'
import { ShoppingListsView } from './components/shopping/ShoppingListsView'
import { useAuth } from './hooks/useAuth'
import { useTheme } from './hooks/useTheme'
import { useUserSettings } from './hooks/useUserSettings'
import type { BoardType } from './types/boards'
import { TaskNavigationContext, type TaskNavigationTarget } from './context/TaskNavigationContext'
import { supabase } from './lib/supabase'
import { readTaskDeepLink } from './utils/taskDeepLink'

type DirectorySelections = Record<BoardType, string | null>

const emptySelections: DirectorySelections = {
  projects: null,
  shopping: null,
  recipes: null,
}

const workspaceStatePrefix = 'yapvibes:organizer:workspace'

function workspaceStateKey(userId: string) {
  return `${workspaceStatePrefix}:${userId}`
}

function readWorkspaceState(userId: string): { boardType: BoardType; selections: DirectorySelections } | null {
  try {
    const raw = window.localStorage.getItem(workspaceStateKey(userId))
    if (!raw) return null
    const value = JSON.parse(raw) as Record<string, unknown>
    if (!['projects', 'shopping', 'recipes'].includes(value.boardType as string)) return null
    const selections = value.selections
    if (!selections || typeof selections !== 'object') return null
    return {
      boardType: value.boardType as BoardType,
      selections: {
        projects: typeof (selections as DirectorySelections).projects === 'string' ? (selections as DirectorySelections).projects : null,
        shopping: typeof (selections as DirectorySelections).shopping === 'string' ? (selections as DirectorySelections).shopping : null,
        recipes: typeof (selections as DirectorySelections).recipes === 'string' ? (selections as DirectorySelections).recipes : null,
      },
    }
  } catch {
    return null
  }
}

function storeWorkspaceState(userId: string, boardType: BoardType, selections: DirectorySelections) {
  try { window.localStorage.setItem(workspaceStateKey(userId), JSON.stringify({ boardType, selections })) } catch { /* session state remains usable */ }
}

export default function App() {
  const { user, loading: authLoading, signOut } = useAuth()

  if (authLoading) return <LoadingScreen label="Opening your personal organizer…" />

  if (!user) {
    return (
      <div className="app-shell flex min-h-screen flex-col">
        <main className="flex flex-1 items-center justify-center p-4 md:p-8"><Login /></main>
        <Footer />
      </div>
    )
  }

  return <AuthenticatedOrganizer key={user.id} user={user} onSignOut={signOut} />
}

function AuthenticatedOrganizer({
  user,
  onSignOut,
}: {
  user: User
  onSignOut: () => Promise<unknown>
}) {
  const { theme, appearance, isCustomized, setTheme, previewColor, previewSectionOverride, beginColorGesture, finishColorGesture, setSectionOverride, resetAppearance, importAppearance, undo, redo, canUndo, canRedo } = useTheme()
  const {
    settings,
    loading: settingsLoading,
    updateWorkspacePreferences,
  } = useUserSettings()
  const localWorkspace = useRef(readWorkspaceState(user.id))
  const [boardType, setBoardType] = useState<BoardType>(() => localWorkspace.current?.boardType ?? 'projects')
  const [workspaceInitialized, setWorkspaceInitialized] = useState(false)
  const [selections, setSelections] = useState<DirectorySelections>(() => localWorkspace.current?.selections ?? emptySelections)
  const [taskNavigationTarget, setTaskNavigationTarget] = useState<TaskNavigationTarget | null>(null)
  const taskNavigationRequestRef = useRef(0)
  const [deepLinkRequest, setDeepLinkRequest] = useState(() => ({
    target: readTaskDeepLink(window.location.search),
    sequence: 0,
  }))

  useEffect(() => {
    const handlePopState = () => {
      setDeepLinkRequest(previous => ({
        target: readTaskDeepLink(window.location.search),
        sequence: previous.sequence + 1,
      }))
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (settingsLoading || workspaceInitialized) return

    const initialBoardType = localWorkspace.current?.boardType ?? (settings?.default_workspace === 'last'
      ? settings.last_workspace
      : settings?.default_workspace ?? 'projects')
    const remoteSelections: DirectorySelections = {
      projects: settings?.selected_task_board_id ?? null,
      shopping: settings?.selected_shopping_list_id ?? null,
      recipes: settings?.selected_recipe_book_id ?? null,
    }
    setSelections(localWorkspace.current?.selections ?? remoteSelections)
    setBoardType(initialBoardType)
    setWorkspaceInitialized(true)
  }, [settings, settingsLoading, workspaceInitialized])

  useEffect(() => {
    if (workspaceInitialized) storeWorkspaceState(user.id, boardType, selections)
  }, [boardType, selections, user.id, workspaceInitialized])

  const handleBoardTypeChange = useCallback((nextBoardType: BoardType) => {
    setBoardType(nextBoardType)
    if (nextBoardType !== settings?.last_workspace) {
      void updateWorkspacePreferences({ last_workspace: nextBoardType })
    }
  }, [settings?.last_workspace, updateWorkspacePreferences])

  const selectRecord = useCallback((type: BoardType, recordId: string | null) => {
    setSelections(previous => previous[type] === recordId ? previous : { ...previous, [type]: recordId })
  }, [])

  const navigateToTask = useCallback(async (target: TaskNavigationTarget) => {
    const requestId = ++taskNavigationRequestRef.current

    // The URL project is a hint. Resolve the task's current board through the
    // authenticated client so moved tasks still open without trusting the URL.
    const { data: task } = await supabase
      .from('tasks')
      .select('project_id')
      .eq('id', target.taskId)
      .maybeSingle()
    const projectId = task?.project_id

    if (requestId !== taskNavigationRequestRef.current || !projectId) return false

    const { data: project } = await supabase
      .from('projects')
      .select('id')
      .eq('id', projectId)
      .eq('kind', 'board')
      .maybeSingle()

    if (requestId !== taskNavigationRequestRef.current || !project) return false
    handleBoardTypeChange('projects')
    selectRecord('projects', projectId)
    setTaskNavigationTarget({ taskId: target.taskId, projectId })
    return true
  }, [handleBoardTypeChange, selectRecord])

  useEffect(() => {
    if (!workspaceInitialized) return
    if (!deepLinkRequest.target) {
      taskNavigationRequestRef.current += 1
      setTaskNavigationTarget(null)
      return
    }
    void navigateToTask(deepLinkRequest.target)
  }, [deepLinkRequest, navigateToTask, workspaceInitialized])

  if (!workspaceInitialized) {
    return <LoadingScreen label="Restoring your organizerâ€¦" />
  }

  return (
    <TaskNavigationContext.Provider value={{ navigateToTask }}>
      <OrganizerShell
        boardType={boardType}
        userEmail={user.email}
        theme={theme}
        onBoardTypeChange={handleBoardTypeChange}
        onThemeChange={setTheme}
        appearance={appearance}
        appearanceCustomized={isCustomized}
        onAppearanceColorPreview={previewColor}
        onSectionOverridePreview={previewSectionOverride}
        onAppearanceColorStart={beginColorGesture}
        onAppearanceColorEnd={finishColorGesture}
        onSectionOverrideChange={setSectionOverride}
        onAppearanceReset={resetAppearance}
        onAppearanceImport={importAppearance}
        onAppearanceUndo={undo}
        onAppearanceRedo={redo}
        canAppearanceUndo={canUndo}
        canAppearanceRedo={canRedo}
        onSignOut={onSignOut}
      >
        <ActiveBoard
          boardType={boardType}
          userId={user.id}
          selectedRecordId={selections[boardType]}
          taskNavigationTarget={taskNavigationTarget}
          onSelectedRecordChange={recordId => selectRecord(boardType, recordId)}
          onTaskNavigationHandled={() => setTaskNavigationTarget(null)}
        />
      </OrganizerShell>
    </TaskNavigationContext.Provider>
  )
}

function ActiveBoard({
  boardType,
  userId,
  selectedRecordId,
  taskNavigationTarget,
  onSelectedRecordChange,
  onTaskNavigationHandled,
}: {
  boardType: BoardType
  userId: string
  selectedRecordId: string | null
  taskNavigationTarget: TaskNavigationTarget | null
  onSelectedRecordChange: (recordId: string | null) => void
  onTaskNavigationHandled: () => void
}) {
  if (boardType === 'shopping') {
    return (
      <ShoppingListsView
        selectedRecordId={selectedRecordId}
        onSelectedRecordChange={onSelectedRecordChange}
      />
    )
  }

  if (boardType === 'recipes') {
    return (
      <RecipeBooksView
        userId={userId}
        selectedRecordId={selectedRecordId}
        onSelectedRecordChange={onSelectedRecordChange}
      />
    )
  }

  return (
    <ProjectsView
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={onSelectedRecordChange}
      focusedTaskId={taskNavigationTarget?.taskId ?? null}
      onFocusedTaskHandled={onTaskNavigationHandled}
    />
  )
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="app-shell flex min-h-screen flex-col">
      <main className="grid flex-1 place-items-center p-4">
        <div className="text-center" role="status" aria-live="polite">
          <div className="mx-auto mb-3 size-8 animate-pulse rounded-lg bg-emerald-700" />
          <p className="text-sm font-medium text-stone-500">{label}</p>
        </div>
      </main>
      <Footer />
    </div>
  )
}
