import { themes, type Theme } from '../../lib/themes'

export function ThemePaletteSelector({
  theme,
  onChange,
}: {
  theme: Theme
  onChange: (theme: Theme) => void
}) {
  return (
    <div className="theme-palette" role="group" aria-label="Color theme">
      {themes.map(option => {
        const selected = option.id === theme
        return (
          <button
            key={option.id}
            type="button"
            className="theme-palette-option"
            onClick={() => onChange(option.id)}
            aria-label={option.id === 'light' ? 'Use light mode' : option.id === 'dark' ? 'Use dark mode' : `Use ${option.label} theme`}
            aria-pressed={selected}
            title={option.label}
          >
            <span
              className="theme-palette-circle"
              style={{ background: option.preview }}
              aria-hidden="true"
            >
              {option.id === 'light' ? <span className="theme-mode-icon">☀</span> : option.id === 'dark' ? <span className="theme-mode-icon">☾</span> : selected && <span className="theme-palette-check">✓</span>}
            </span>
            <span className="theme-palette-label">{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
