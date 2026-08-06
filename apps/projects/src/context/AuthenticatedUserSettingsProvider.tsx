import type { ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'
import { UserSettingsProvider } from './UserSettingsProvider'

interface AuthenticatedUserSettingsProviderProps {
  children: ReactNode
}

export function AuthenticatedUserSettingsProvider({
  children,
}: AuthenticatedUserSettingsProviderProps) {
  const { user } = useAuth()

  if (!user?.id) {
    return <>{children}</>
  }

  return (
    <UserSettingsProvider userId={user.id}>
      {children}
    </UserSettingsProvider>
  )
}
