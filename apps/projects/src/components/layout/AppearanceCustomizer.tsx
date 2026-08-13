import { useRef, useState } from 'react'
import { createAppearanceSaveFile, parseAppearanceSaveFile, type AppearanceColors, type AppearancePreference, type SectionColorOverrides, type Theme } from '../../lib/themes'

const colorControls: Array<[keyof AppearanceColors, string]> = [['pageBackground', 'Page background'], ['headerBackground', 'Header'], ['contentBackground', 'Main content'], ['sectionBackground', 'Sections'], ['cardBackground', 'Cards'], ['inputBackground', 'Inputs'], ['primaryAccent', 'Accent'], ['borderColor', 'Borders'], ['primaryText', 'Primary text'], ['mutedText', 'Muted text']]
const sectionControls: Array<[keyof SectionColorOverrides, string]> = [['projects', 'Projects'], ['shopping', 'Shopping'], ['recipes', 'Recipes']]

function Swatch({ label, value, onPreview, onStart, onEnd, onReset }: { label: string; value: string; onPreview: (value: string) => void; onStart: () => void; onEnd: () => void; onReset?: () => void }) {
  return <div className="appearance-control"><span>{label}</span><div className="flex items-center gap-2"><input className="appearance-swatch" type="color" value={value} onPointerDown={onStart} onFocus={onStart} onInput={event => onPreview(event.currentTarget.value)} onChange={event => { onPreview(event.target.value); onEnd() }} onBlur={onEnd} aria-label={`Change ${label.toLowerCase()} color`} title={`Change ${label.toLowerCase()} color`} />{onReset && <button type="button" className="appearance-clear" onClick={onReset} aria-label={`Use shared section color for ${label}`}>Reset</button>}</div></div>
}

function downloadAppearance(appearance: AppearancePreference) {
  const blob = new Blob([JSON.stringify(createAppearanceSaveFile(appearance), null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `yapvibes-appearance-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function AppearanceCustomizer({ theme, customized, appearance, colors, sectionOverrides, onColorPreview, onSectionOverridePreview, onColorStart, onColorEnd, onSectionOverride, onReset, onImport, onUndo, onRedo, canUndo, canRedo }: {
  theme: Theme; customized: boolean; appearance: AppearancePreference; colors: AppearanceColors; sectionOverrides: SectionColorOverrides
  onColorPreview: (key: keyof AppearanceColors, color: string) => void
  onSectionOverridePreview: (key: keyof SectionColorOverrides, color: string) => void
  onColorStart: () => void
  onColorEnd: () => void
  onSectionOverride: (key: keyof SectionColorOverrides, color: string | null) => void
  onReset: () => void
  onImport: (appearance: AppearancePreference) => void
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
}) {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const label = theme[0].toUpperCase() + theme.slice(1)
  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      onImport(parseAppearanceSaveFile(JSON.parse(await file.text())))
      setStatus('Appearance loaded.')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not load this appearance file.')
    }
  }
  return <div className="appearance-customizer">
    <button type="button" className="appearance-trigger" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls="appearance-panel">Appearance{customized && <span className="appearance-dot" aria-label="Customized" />}</button>
    {open && <section id="appearance-panel" className="appearance-panel" aria-label="Appearance customizer">
      <div className="appearance-panel-heading"><div><strong>Appearance</strong><p>{label}{customized ? ' · Customized' : ''}</p></div><button type="button" onClick={onReset} className="appearance-reset">Reset to {label}</button></div>
      <div className="appearance-history"><button type="button" className="appearance-reset" onClick={onUndo} disabled={!canUndo} title="Undo appearance change">Undo</button><button type="button" className="appearance-reset" onClick={onRedo} disabled={!canRedo} title="Redo appearance change">Redo</button></div>
      <div className="appearance-grid">{colorControls.map(([key, name]) => <Swatch key={key} label={name} value={colors[key]} onPreview={value => onColorPreview(key, value)} onStart={onColorStart} onEnd={onColorEnd} />)}</div>
      <div className="appearance-overrides"><strong>Section overrides</strong>{sectionControls.map(([key, name]) => <Swatch key={key} label={name} value={sectionOverrides[key] ?? colors.sectionBackground} onPreview={value => onSectionOverridePreview(key, value)} onStart={onColorStart} onEnd={onColorEnd} onReset={sectionOverrides[key] ? () => onSectionOverride(key, null) : undefined} />)}</div>
      <div className="appearance-file-actions"><button type="button" className="appearance-reset" onClick={() => { downloadAppearance(appearance); setStatus('Appearance saved.') }}>Save appearance</button><button type="button" className="appearance-reset" onClick={() => inputRef.current?.click()}>Load appearance</button><input ref={inputRef} className="sr-only" type="file" accept=".json,application/json" onChange={handleImport} /></div>
      {status && <p className="appearance-status" role="status">{status}</p>}
    </section>}
  </div>
}
