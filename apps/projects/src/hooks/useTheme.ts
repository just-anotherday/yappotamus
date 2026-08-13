import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from './useAuth'
import { useOptionalUserSettings } from './useUserSettings'
import { APPEARANCE_STORAGE_KEY, DEFAULT_THEME, THEME_STORAGE_KEY, isCustomized, isDarkTheme, isTheme, normalizeAppearance, presetAppearance, type AppearanceColors, type AppearancePreference, type SectionColorOverrides, type Theme } from '../lib/themes'

const HISTORY_LIMIT = 50
const equal = (left: AppearancePreference, right: AppearancePreference) => JSON.stringify(left) === JSON.stringify(right)
function readTheme(): Theme { try { const value = window.localStorage.getItem(THEME_STORAGE_KEY); return isTheme(value) ? value : DEFAULT_THEME } catch { return DEFAULT_THEME } }
function readAppearance(): AppearancePreference { try { const value = window.localStorage.getItem(APPEARANCE_STORAGE_KEY); return value ? normalizeAppearance(JSON.parse(value), readTheme()) : presetAppearance(readTheme()) } catch { return presetAppearance(readTheme()) } }
function hasValidStoredAppearance(): boolean {
  try {
    const value = window.localStorage.getItem(APPEARANCE_STORAGE_KEY)
    if (!value) return false
    const parsed = JSON.parse(value)
    return Boolean(parsed && typeof parsed === 'object' && !Array.isArray(parsed) && isTheme((parsed as { preset?: unknown }).preset))
  } catch {
    return false
  }
}
function storeAppearance(appearance: AppearancePreference) { try { window.localStorage.setItem(THEME_STORAGE_KEY, appearance.preset); window.localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(appearance)) } catch { /* session-only when storage is unavailable */ } }
function applyAppearance(appearance: AppearancePreference) {
  const root = document.documentElement; root.dataset.theme = appearance.preset; root.classList.toggle('dark', isDarkTheme(appearance.preset)); const c = appearance.colors
  const stoneTokens = ['--color-stone-950', '--color-stone-900', '--color-stone-800', '--color-stone-700', '--color-stone-500']
  stoneTokens.forEach(token => root.style.removeProperty(token))
  const values: Record<string, string> = { '--app-background': c.pageBackground, '--header-background': c.headerBackground, '--content-background': c.contentBackground, '--section-background': c.sectionBackground, '--card-background': c.cardBackground, '--input-background': c.inputBackground, '--border-color': c.borderColor, '--primary-accent': c.primaryAccent, '--text-primary': c.primaryText, '--text-muted': c.mutedText, '--background': c.pageBackground, '--surface': c.sectionBackground, '--surface-elevated': c.cardBackground, '--text': c.primaryText, '--border': c.borderColor, '--primary': c.primaryAccent, '--projects-section-background': appearance.sectionOverrides.projects ?? c.sectionBackground, '--shopping-section-background': appearance.sectionOverrides.shopping ?? c.sectionBackground, '--recipes-section-background': appearance.sectionOverrides.recipes ?? c.sectionBackground }
  if (isDarkTheme(appearance.preset)) Object.assign(values, { '--color-stone-950': c.inputBackground, '--color-stone-900': c.sectionBackground, '--color-stone-800': c.cardBackground, '--color-stone-700': c.borderColor, '--color-stone-500': c.mutedText })
  Object.entries(values).forEach(([key, value]) => root.style.setProperty(key, value))
}
function editableTarget(target: EventTarget | null) { return target instanceof HTMLElement && (target.isContentEditable || target.tagName === 'TEXTAREA' || (target.tagName === 'INPUT' && (target as HTMLInputElement).type !== 'color')) }

export function useTheme() {
  const { user } = useAuth(); const settingsContext = useOptionalUserSettings()
  const [appearance, setAppearance] = useState<AppearancePreference>(readAppearance)
  const [past, setPast] = useState<AppearancePreference[]>([]); const [future, setFuture] = useState<AppearancePreference[]>([])
  const appearanceRef = useRef(appearance); const pastRef = useRef<AppearancePreference[]>([]); const futureRef = useRef<AppearancePreference[]>([])
  const colorGestureStart = useRef<AppearancePreference | null>(null); const localAppearanceExists = useRef(hasValidStoredAppearance()); const remoteHydrated = useRef(false)
  useEffect(() => { appearanceRef.current = appearance; applyAppearance(appearance) }, [appearance])
  const persist = useCallback((next: AppearancePreference) => { storeAppearance(next); if (user && settingsContext?.settings) void settingsContext.patchSettings({ theme: next.preset, appearance: next }) }, [settingsContext, user])
  const restore = useCallback((next: AppearancePreference) => { appearanceRef.current = next; setAppearance(next); persist(next) }, [persist])
  const updateHistory = useCallback((nextPast: AppearancePreference[], nextFuture: AppearancePreference[]) => { pastRef.current = nextPast; futureRef.current = nextFuture; setPast(nextPast); setFuture(nextFuture) }, [])
  const commit = useCallback((next: AppearancePreference) => {
    const current = appearanceRef.current; if (equal(current, next)) return
    updateHistory([...pastRef.current, current].slice(-HISTORY_LIMIT), []); restore(next)
  }, [restore, updateHistory])
  const previewColor = useCallback((key: keyof AppearanceColors, color: string) => { const current = appearanceRef.current; const next = { ...current, colors: { ...current.colors, [key]: color } }; appearanceRef.current = next; setAppearance(next) }, [])
  const previewSectionOverride = useCallback((key: keyof SectionColorOverrides, color: string) => { const current = appearanceRef.current; const next = { ...current, sectionOverrides: { ...current.sectionOverrides, [key]: color } }; appearanceRef.current = next; setAppearance(next) }, [])
  const beginColorGesture = useCallback(() => { if (!colorGestureStart.current) colorGestureStart.current = appearanceRef.current }, [])
  const finishColorGesture = useCallback(() => {
    const start = colorGestureStart.current; colorGestureStart.current = null; const current = appearanceRef.current
    if (start && !equal(start, current)) { updateHistory([...pastRef.current, start].slice(-HISTORY_LIMIT), []); persist(current) }
  }, [persist, updateHistory])
  useEffect(() => { const onStorage = (event: StorageEvent) => { if (event.key === APPEARANCE_STORAGE_KEY && event.newValue) { try { const next = normalizeAppearance(JSON.parse(event.newValue), readTheme()); appearanceRef.current = next; setAppearance(next) } catch { /* ignore corrupt external writes */ } } }; window.addEventListener('storage', onStorage); return () => window.removeEventListener('storage', onStorage) }, [])
  useEffect(() => { const settings = settingsContext?.settings; if (!user || !settings || remoteHydrated.current) return; remoteHydrated.current = true; if (!localAppearanceExists.current) { const remote = settings.appearance ?? presetAppearance(settings.theme); appearanceRef.current = remote; setAppearance(remote); storeAppearance(remote) } }, [settingsContext?.settings, user])
  const undo = useCallback(() => { const current = appearanceRef.current; const previous = pastRef.current.at(-1); if (!previous) return; updateHistory(pastRef.current.slice(0, -1), [current, ...futureRef.current].slice(0, HISTORY_LIMIT)); restore(previous) }, [restore, updateHistory])
  const redo = useCallback(() => { const current = appearanceRef.current; const next = futureRef.current[0]; if (!next) return; updateHistory([...pastRef.current, current].slice(-HISTORY_LIMIT), futureRef.current.slice(1)); restore(next) }, [restore, updateHistory])
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((!event.ctrlKey && !event.metaKey) || editableTarget(event.target)) return; const key = event.key.toLowerCase(); if (key === 'z') { event.preventDefault(); if (event.shiftKey) redo(); else undo() } else if (key === 'y' && event.ctrlKey) { event.preventDefault(); redo() } }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler) }, [redo, undo])
  const setTheme = useCallback((preset: Theme) => commit(presetAppearance(preset)), [commit])
  const setColor = useCallback((key: keyof AppearanceColors, color: string) => commit({ ...appearanceRef.current, colors: { ...appearanceRef.current.colors, [key]: color } }), [commit])
  const setSectionOverride = useCallback((key: keyof SectionColorOverrides, color: string | null) => commit({ ...appearanceRef.current, sectionOverrides: { ...appearanceRef.current.sectionOverrides, [key]: color } }), [commit])
  const resetAppearance = useCallback(() => commit(presetAppearance(appearanceRef.current.preset)), [commit])
  const importAppearance = useCallback((next: AppearancePreference) => commit(next), [commit])
  return useMemo(() => ({ theme: appearance.preset, appearance, isCustomized: isCustomized(appearance), setTheme, setColor, previewColor, previewSectionOverride, beginColorGesture, finishColorGesture, setSectionOverride, resetAppearance, importAppearance, undo, redo, canUndo: past.length > 0, canRedo: future.length > 0 }), [appearance, beginColorGesture, finishColorGesture, future.length, importAppearance, past.length, previewColor, previewSectionOverride, redo, resetAppearance, setColor, setSectionOverride, setTheme, undo])
}
