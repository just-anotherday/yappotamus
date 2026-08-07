import type { ReactNode } from 'react'
import Footer from '../Footer'
import type { BoardType } from '../../types/boards'
import { BoardTypeSelector } from './BoardTypeSelector'
import { NotificationBell } from '../notifications/NotificationBell'

interface OrganizerShellProps {
  boardType: BoardType
  userEmail?: string
  theme: 'light' | 'dark'
  onBoardTypeChange: (boardType: BoardType) => void
  onToggleTheme: () => void
  onSignOut: () => void
  children: ReactNode
  fatalError?: string | null
}

export function OrganizerShell({
  boardType,
  userEmail,
  theme,
  onBoardTypeChange,
  onToggleTheme,
  onSignOut,
  children,
  fatalError,
}: OrganizerShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-stone-100 text-stone-950 dark:bg-stone-950 dark:text-stone-50">
      <header className="border-b border-stone-200/80 bg-white/90 backdrop-blur dark:border-stone-800 dark:bg-stone-950/90">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-emerald-700 text-sm font-black tracking-tight text-white shadow-sm">
              YV
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-400">
                yapvibes
              </p>
              <h1 className="text-xl font-semibold text-stone-950 dark:text-stone-50">Personal Organizer</h1>
            </div>
          </div>

          <div className="flex flex-1 flex-wrap items-center gap-2 lg:max-w-3xl lg:justify-end">
            <BoardTypeSelector value={boardType} onChange={onBoardTypeChange} />
            <button
              type="button"
              onClick={onToggleTheme}
              className="h-10 rounded-lg border border-stone-300 px-3 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
              aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
            >
              {theme === 'light' ? 'Dark' : 'Light'}
            </button>
            {userEmail && <NotificationBell />}
            <div className="min-w-0 text-right">
              <p className="max-w-44 truncate text-xs text-stone-500 dark:text-stone-400">{userEmail}</p>
              <button
                type="button"
                onClick={onSignOut}
                className="text-xs font-semibold text-stone-700 hover:text-emerald-700 dark:text-stone-300 dark:hover:text-emerald-400"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {fatalError ? (
          <section
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
          >
            <h2 className="font-semibold">The organizer could not be opened.</h2>
            <p className="mt-1 text-sm">{fatalError}</p>
          </section>
        ) : children}
      </main>

      <Footer />
    </div>
  )
}
