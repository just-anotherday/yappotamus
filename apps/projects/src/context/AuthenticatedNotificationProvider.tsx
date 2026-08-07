import type { ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'
import { NotificationProvider } from './NotificationProvider'

interface AuthenticatedNotificationProviderProps {
  children: ReactNode
}

export function AuthenticatedNotificationProvider({
  children,
}: AuthenticatedNotificationProviderProps) {
  const { user } = useAuth()

  if (!user?.id) {
    return <>{children}</>
  }

  return (
    <NotificationProvider userId={user.id} key={user.id}>
      {children}
    </NotificationProvider>
  )
}
