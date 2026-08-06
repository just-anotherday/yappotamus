import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

interface AuthActionResult {
  user: User | null
  session: Session | null
  error: string | null
}

export interface AuthContextValue {
  user: User | null
  session: Session | null
  loading: boolean
  error: string | null
  displayName: string | null
  accountLabel: string
  signIn: (email: string, password: string) => Promise<AuthActionResult>
  signUp: (email: string, password: string) => Promise<AuthActionResult>
  signOut: () => Promise<{ error: string | null }>
  refreshUser: () => Promise<User | null>
  updateDisplayName: (displayName: string) => Promise<AuthActionResult>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

function safeAuthError(error: unknown): string {
  const message = error instanceof Error
    ? error.message.toLowerCase()
    : String(error).toLowerCase()

  if (message.includes('invalid login credentials')) {
    return 'The email or password is incorrect.'
  }
  if (message.includes('email not confirmed')) {
    return 'Confirm your email address before signing in.'
  }
  if (message.includes('already registered')) {
    return 'An account already exists for this email address.'
  }
  if (message.includes('password')) {
    return 'The password does not meet the account requirements.'
  }
  if (message.includes('email')) {
    return 'Enter a valid email address.'
  }
  if (message.includes('network') || message.includes('fetch')) {
    return 'Authentication is temporarily unavailable. Check your connection.'
  }
  return 'The authentication request could not be completed. Please try again.'
}

export function readDisplayName(user: User | null): string | null {
  const value = user?.user_metadata?.display_name
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return
      if (sessionError) {
        setError(safeAuthError(sessionError))
        setSession(null)
        setUser(null)
      } else {
        setSession(data.session)
        setUser(data.session?.user ?? null)
        setError(null)
      }
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, nextSession) => {
        if (!active) return
        setSession(nextSession)
        setUser(nextSession?.user ?? null)
        setError(null)
        setLoading(false)
      },
    )

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  const applyUser = useCallback((nextUser: User | null) => {
    setUser(nextUser)
    setSession(previous => (
      previous && nextUser ? { ...previous, user: nextUser } : previous
    ))
  }, [])

  const signIn = useCallback(async (
    email: string,
    password: string,
  ): Promise<AuthActionResult> => {
    const { data, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    if (signInError) {
      const safeError = safeAuthError(signInError)
      setError(safeError)
      return { user: null, session: null, error: safeError }
    }
    setError(null)
    setSession(data.session)
    setUser(data.user)
    return { user: data.user, session: data.session, error: null }
  }, [])

  const signUp = useCallback(async (
    email: string,
    password: string,
  ): Promise<AuthActionResult> => {
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
    })
    if (signUpError) {
      const safeError = safeAuthError(signUpError)
      setError(safeError)
      return { user: null, session: null, error: safeError }
    }
    setError(null)
    if (data.session) {
      setSession(data.session)
      setUser(data.user)
    }
    return { user: data.user, session: data.session, error: null }
  }, [])

  const signOut = useCallback(async () => {
    const { error: signOutError } = await supabase.auth.signOut()
    if (signOutError) {
      const safeError = safeAuthError(signOutError)
      setError(safeError)
      return { error: safeError }
    }
    setSession(null)
    setUser(null)
    setError(null)
    return { error: null }
  }, [])

  const refreshUser = useCallback(async () => {
    const { data, error: refreshError } = await supabase.auth.getUser()
    if (refreshError) {
      setError(safeAuthError(refreshError))
      return null
    }
    applyUser(data.user)
    setError(null)
    return data.user
  }, [applyUser])

  const updateDisplayName = useCallback(async (
    nextDisplayName: string,
  ): Promise<AuthActionResult> => {
    const normalized = nextDisplayName.trim()
    if (normalized.length > 80) {
      return {
        user,
        session,
        error: 'Display name must be 80 characters or fewer.',
      }
    }

    const { data, error: updateError } = await supabase.auth.updateUser({
      data: { display_name: normalized || null },
    })
    if (updateError) {
      const safeError = safeAuthError(updateError)
      setError(safeError)
      return { user, session, error: safeError }
    }
    applyUser(data.user)
    setError(null)
    return {
      user: data.user,
      session: session ? { ...session, user: data.user } : null,
      error: null,
    }
  }, [applyUser, session, user])

  const displayName = readDisplayName(user)
  const accountLabel = displayName ?? user?.email ?? 'Account'

  const value = useMemo<AuthContextValue>(() => ({
    user,
    session,
    loading,
    error,
    displayName,
    accountLabel,
    signIn,
    signUp,
    signOut,
    refreshUser,
    updateDisplayName,
  }), [
    accountLabel,
    displayName,
    error,
    loading,
    refreshUser,
    session,
    signIn,
    signOut,
    signUp,
    updateDisplayName,
    user,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
