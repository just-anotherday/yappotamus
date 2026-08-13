export const THEME_STORAGE_KEY = 'yapvibes:organizer:theme'
export const APPEARANCE_STORAGE_KEY = 'yapvibes:organizer:appearance'
export const APPEARANCE_LOCK_STORAGE_KEY = 'yapvibes:organizer:appearance-locked'

export type AppearanceColors = {
  pageBackground: string
  headerBackground: string
  contentBackground: string
  sectionBackground: string
  cardBackground: string
  inputBackground: string
  borderColor: string
  primaryAccent: string
  primaryText: string
  mutedText: string
}

export type SectionColorOverrides = {
  projects: string | null
  shopping: string | null
  recipes: string | null
}

export type AppearancePreference = {
  version: 1
  preset: Theme
  colors: AppearanceColors
  sectionOverrides: SectionColorOverrides
}

// The lock is an account/device preference rather than a visual token. Keep it
// out of portable appearance files while allowing the existing JSONB setting to
// carry it for authenticated users.
export type PersistedAppearancePreference = AppearancePreference & {
  locked?: boolean
}

export type AppearanceSaveFile = AppearancePreference & {
  format: 'yapvibes-appearance'
  savedAt: string
}

const paletteDefaults = {
  light: {
    pageBackground: '#f5f5f4', headerBackground: '#ffffff', contentBackground: '#f5f5f4', sectionBackground: '#ffffff', cardBackground: '#ffffff', inputBackground: '#ffffff', borderColor: '#d6d3d1', primaryAccent: '#2563eb', primaryText: '#1c1917', mutedText: '#57534e',
  },
  dark: {
    pageBackground: '#0c0a09', headerBackground: '#1c1917', contentBackground: '#0c0a09', sectionBackground: '#1c1917', cardBackground: '#292524', inputBackground: '#0c0a09', borderColor: '#57534e', primaryAccent: '#60a5fa', primaryText: '#fafaf9', mutedText: '#a8a29e',
  },
  forest: {
    pageBackground: '#142019', headerBackground: '#1b2b21', contentBackground: '#142019', sectionBackground: '#1b2b21', cardBackground: '#263a2b', inputBackground: '#142019', borderColor: '#39503d', primaryAccent: '#55a36d', primaryText: '#f7f4e8', mutedText: '#b8c0ab',
  },
  midnight: {
    pageBackground: '#101827', headerBackground: '#17243a', contentBackground: '#101827', sectionBackground: '#17243a', cardBackground: '#213452', inputBackground: '#101827', borderColor: '#34496a', primaryAccent: '#5796dd', primaryText: '#eff5ff', mutedText: '#afc0d9',
  },
  sunset: {
    pageBackground: '#231a19', headerBackground: '#342323', contentBackground: '#231a19', sectionBackground: '#342323', cardBackground: '#4a302d', inputBackground: '#231a19', borderColor: '#68453d', primaryAccent: '#e77b46', primaryText: '#fff3e8', mutedText: '#d6bbb0',
  },
} as const satisfies Record<string, AppearanceColors>

export const themes = [
  { id: 'light', label: 'Light', preview: 'linear-gradient(135deg, #ffffff 0 52%, #e7e5e4 52% 72%, #2563eb 72%)', colors: paletteDefaults.light },
  { id: 'dark', label: 'Dark', preview: 'linear-gradient(135deg, #0c0a09 0 52%, #44403c 52% 72%, #60a5fa 72%)', colors: paletteDefaults.dark },
  { id: 'forest', label: 'Forest', preview: 'linear-gradient(135deg, #2f6b45 0 48%, #82904a 48% 70%, #d8b36a 70%)', colors: paletteDefaults.forest },
  { id: 'midnight', label: 'Midnight', preview: 'linear-gradient(135deg, #2667a8 0 48%, #5b4bb7 48% 70%, #9e88dc 70%)', colors: paletteDefaults.midnight },
  { id: 'sunset', label: 'Sunset', preview: 'linear-gradient(135deg, #d96b38 0 48%, #e48a55 48% 70%, #d65b7c 70%)', colors: paletteDefaults.sunset },
] as const

export type Theme = (typeof themes)[number]['id']
export const DEFAULT_THEME: Theme = 'forest'
const colorKeys = Object.keys(paletteDefaults.forest) as Array<keyof AppearanceColors>

export function isDarkTheme(theme: Theme): boolean {
  return theme !== 'light'
}

const sectionKeys: Array<keyof SectionColorOverrides> = ['projects', 'shopping', 'recipes']
const hexPattern = /^#[0-9a-f]{6}$/i

export function isTheme(value: unknown): value is Theme {
  return typeof value === 'string' && themes.some(theme => theme.id === value)
}

export function presetAppearance(preset: Theme): AppearancePreference {
  return { version: 1, preset, colors: { ...paletteDefaults[preset] }, sectionOverrides: { projects: null, shopping: null, recipes: null } }
}

export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && hexPattern.test(value)
}

export function normalizeAppearance(value: unknown, fallbackPreset = DEFAULT_THEME): AppearancePreference {
  const fallback = presetAppearance(fallbackPreset)
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fallback
  const candidate = value as Record<string, unknown>
  const preset = isTheme(candidate.preset) ? candidate.preset : fallbackPreset
  const normalized = presetAppearance(preset)
  const colors = candidate.colors
  if (colors && typeof colors === 'object' && !Array.isArray(colors)) {
    for (const key of colorKeys) {
      const color = (colors as Record<string, unknown>)[key]
      if (isHexColor(color)) normalized.colors[key] = color.toLowerCase()
    }
  }
  const overrides = candidate.sectionOverrides
  if (overrides && typeof overrides === 'object' && !Array.isArray(overrides)) {
    for (const key of sectionKeys) {
      const color = (overrides as Record<string, unknown>)[key]
      if (color === null || isHexColor(color)) normalized.sectionOverrides[key] = color === null ? null : color.toLowerCase()
    }
  }
  return normalized
}

export function isCustomized(appearance: AppearancePreference): boolean {
  return JSON.stringify(appearance) !== JSON.stringify(presetAppearance(appearance.preset))
}

export function createAppearanceSaveFile(appearance: AppearancePreference): AppearanceSaveFile {
  return { format: 'yapvibes-appearance', savedAt: new Date().toISOString(), ...appearance }
}

export function parseAppearanceSaveFile(value: unknown): AppearancePreference {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('This is not a valid YapVibes appearance file.')
  const file = value as Record<string, unknown>
  if (file.format !== 'yapvibes-appearance') throw new Error('This is not a valid YapVibes appearance file.')
  if (file.version !== 1) throw new Error('This appearance file version is not supported.')
  if (typeof file.savedAt !== 'string' || Number.isNaN(Date.parse(file.savedAt)) || !isTheme(file.preset)) throw new Error('This is not a valid YapVibes appearance file.')
  if (!file.colors || typeof file.colors !== 'object' || Array.isArray(file.colors)) throw new Error('This is not a valid YapVibes appearance file.')
  const colors = file.colors as Record<string, unknown>
  for (const key of colorKeys) if (!isHexColor(colors[key])) throw new Error('This appearance file contains an invalid color.')
  if (file.sectionOverrides !== undefined && (!file.sectionOverrides || typeof file.sectionOverrides !== 'object' || Array.isArray(file.sectionOverrides))) throw new Error('This is not a valid YapVibes appearance file.')
  const overrides = (file.sectionOverrides ?? {}) as Record<string, unknown>
  for (const key of sectionKeys) if (overrides[key] !== undefined && overrides[key] !== null && !isHexColor(overrides[key])) throw new Error('This appearance file contains an invalid color.')
  return normalizeAppearance(file, file.preset)
}
