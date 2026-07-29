import { useCallback, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import Footer from './components/Footer'
import Login from './components/Login'
import { OrganizerShell } from './components/layout/OrganizerShell'
import { ProjectsView } from './components/projects/ProjectsView'
import { RecipeBooksView } from './components/recipes/RecipeBooksView'
import { ShoppingListsView } from './components/shopping/ShoppingListsView'
import { useAuth } from './hooks/useAuth'
import { useBoardPreference } from './hooks/useBoardPreference'
import { useTheme } from './hooks/useTheme'
import type { BoardType } from './types/boards'

type DirectorySelections = Record<BoardType, string | null>

const emptySelections: DirectorySelections = {
  projects: null,
  shopping: null,
  recipes: null,
}

export default function App() {
  const { user, loading: authLoading, signOut } = useAuth()

  if (authLoading) return <LoadingScreen label="Opening your personal organizer…" />

  if (!user) {
    return (
      <div className="flex min-h-screen flex-col bg-stone-100 dark:bg-stone-950">
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
  const { theme, toggleTheme } = useTheme()
  const { boardType, setBoardType } = useBoardPreference(user.id)
  const [selections, setSelections] = useState<DirectorySelections>(emptySelections)

  const selectRecord = useCallback((type: BoardType, recordId: string | null) => {
    setSelections(previous => (
      previous[type] === recordId ? previous : { ...previous, [type]: recordId }
    ))
  }, [])

  return (
    <OrganizerShell
      boardType={boardType}
      userEmail={user.email}
      theme={theme}
      onBoardTypeChange={setBoardType}
      onToggleTheme={toggleTheme}
      onSignOut={onSignOut}
    >
      <ActiveBoard
        boardType={boardType}
        userId={user.id}
        selectedRecordId={selections[boardType]}
        onSelectedRecordChange={recordId => selectRecord(boardType, recordId)}
      />
    </OrganizerShell>
  )
}

function ActiveBoard({
  boardType,
  userId,
  selectedRecordId,
  onSelectedRecordChange,
}: {
  boardType: BoardType
  userId: string
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
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
    />
  )
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen flex-col bg-stone-100 dark:bg-stone-950">
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
