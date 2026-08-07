import { useContext } from 'react'
import { NotificationContext, type NotificationContextValue } from '../context/NotificationProvider'

export function useNotifications(): NotificationContextValue {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider.')
  }
  return context
}
