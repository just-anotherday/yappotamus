import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from './useAuth'
import { useOptionalUserSettings } from './useUserSettings'
import {
  isThemePreference,
  type ThemePreference,
} from '../types/userSettings'

type ResolvedTheme = 'light' | 'dark'

function systemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function readDeviceTheme(): ThemePreference {
  try {
    const stored = window.localStorage.getItem('theme')
    return isThemePreference(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

function storeDeviceTheme(theme: ThemePreference) {
  try {
    window.localStorage.setItem('theme', theme)
  } catch {
    // The applied in-memory theme still works when storage is unavailable.
  }
}

export function useTheme() {
  const { user } = useAuth()
  const settingsContext = useOptionalUserSettings()
  const [deviceTheme, setDeviceTheme] = useState<ThemePreference>(readDeviceTheme)
  const [systemResolvedTheme, setSystemResolvedTheme] =
    useState<ResolvedTheme>(systemTheme)

  const preference = user && settingsContext?.settings
    ? settingsContext.settings.theme
    : deviceTheme

  const resolvedTheme: ResolvedTheme = preference === 'system'
    ? systemResolvedTheme
    : preference

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setSystemResolvedTheme(media.matches ? 'dark' : 'light')
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'theme' && isThemePreference(event.newValue)) {
        setDeviceTheme(event.newValue)
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  useEffect(() => {
    if (!user || !settingsContext?.settings) return
    setDeviceTheme(settingsContext.settings.theme)
    storeDeviceTheme(settingsContext.settings.theme)
  }, [settingsContext?.settings, user])

  const setTheme = useCallback((nextTheme: ThemePreference) => {
    setDeviceTheme(nextTheme)
    storeDeviceTheme(nextTheme)
    if (user && settingsContext?.settings) {
      void settingsContext.updateTheme(nextTheme)
    }
  }, [settingsContext, user])

  const toggleTheme = useCallback(() => {
    const nextTheme: ThemePreference = preference === 'system'
      ? 'light'
      : preference === 'light'
        ? 'dark'
        : 'system'
    setTheme(nextTheme)
  }, [preference, setTheme])

  return useMemo(() => ({
    theme: preference,
    resolvedTheme,
    setTheme,
    toggleTheme,
  }), [preference, resolvedTheme, setTheme, toggleTheme])
}