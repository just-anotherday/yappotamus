import { useContext } from 'react'
import { UserSettingsContext } from '../context/UserSettingsProvider'

export function useUserSettings() {
  const context = useContext(UserSettingsContext)
  if (!context) {
    throw new Error('useUserSettings must be used inside UserSettingsProvider.')
  }
  return context
}

export function useOptionalUserSettings() {
  return useContext(UserSettingsContext)
}
