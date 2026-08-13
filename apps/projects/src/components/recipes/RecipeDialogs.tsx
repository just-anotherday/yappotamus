import { useEffect, useState, type ReactNode } from 'react'
import type {
  Recipe,
  RecipeBook,
  RecipeBookUpdate,
  RecipeDifficulty,
  RecipeIngredient,
  RecipeIngredientUpdate,
  RecipeStep,
  RecipeStepUpdate,
  RecipeUpdate,
  TemperatureUnit,
} from '../../types/recipeBooks'
import { Button } from '../shared/Button'
import { DialogFrame } from '../shared/DialogFrame'
import { validateRecipeImage } from '../../services/recipeImages'

interface DialogFrameProps {
  title: string
  eyebrow: string
  pending: boolean
  error: string | null
  onClose: () => void
  children: ReactNode
  footer: ReactNode
}

function RecipeDialogFrame({
  title,
  eyebrow,
  pending,
  error,
  onClose,
  children,
  footer,
}: DialogFrameProps) {
  return (
    <DialogFrame labelledBy="recipe-dialog-title" pending={pending} onClose={onClose} className="my-6 w-full max-w-3xl rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900 sm:p-6">
      <div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-700 dark:text-orange-300">{eyebrow}</p>
            <h2 id="recipe-dialog-title" className="mt-1 text-2xl font-semibold text-stone-950 dark:text-white">{title}</h2>
          </div>
          <Button type="button" onClick={onClose} disabled={pending} tone="orange" variant="tertiary" className="px-3">
            Close
          </Button>
        </div>
        <div className="mt-5">{children}</div>
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
        <div className="mt-6">{footer}</div>
      </div>
    </DialogFrame>
  )
}

const inputClass = 'w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 outline-none focus:border-orange-600 focus:ring-2 focus:ring-orange-600/15 disabled:opacity-60 dark:border-stone-700 dark:bg-stone-950 dark:text-white'

function Footer({
  pending,
  valid,
  saveLabel,
  onClose,
  onSave,
}: {
  pending: boolean
  valid: boolean
  saveLabel: string
  onClose: () => void
  onSave: () => void
}) {
  return (
    <div className="flex justify-end gap-2">
      <Button type="button" onClick={onClose} disabled={pending} tone="orange" variant="secondary">Cancel</Button>
      <Button type="button" onClick={onSave} disabled={pending || !valid} tone="orange" variant="primary">
        {pending ? 'Saving…' : saveLabel}
      </Button>
    </div>
  )
}

export function RecipeBookDialog({
  book,
  pending,
  error,
  onClose,
  onSave,
}: {
  book: RecipeBook | null
  pending: boolean
  error: string | null
  onClose: () => void
  onSave: (input: RecipeBookUpdate & { name: string; description: string }) => Promise<boolean>
}) {
  const [name, setName] = useState(book?.name ?? '')
  const [description, setDescription] = useState(book?.description ?? '')
  const [coverLabel, setCoverLabel] = useState(book?.cover_label ?? '')

  const save = async () => {
    const saved = await onSave({
      name: name.trim(),
      description: description.trim(),
      cover_label: coverLabel.trim() || null,
    })
    if (saved) onClose()
  }

  return (
    <RecipeDialogFrame
      title={book ? 'Edit Recipe Collection' : 'Create Recipe Collection'}
      eyebrow="Recipe Collection settings"
      pending={pending}
      error={error}
      onClose={onClose}
      footer={<Footer pending={pending} valid={Boolean(name.trim())} saveLabel={book ? 'Save changes' : 'Create Recipe Collection'} onClose={onClose} onSave={() => void save()} />}
    >
      <div className="grid gap-4">
        <label><span className="mb-1 block text-sm font-semibold">Name</span><input autoFocus maxLength={200} disabled={pending} value={name} onChange={event => setName(event.target.value)} className={inputClass} /></label>
        <label><span className="mb-1 block text-sm font-semibold">Description</span><textarea maxLength={10000} rows={3} disabled={pending} value={description} onChange={event => setDescription(event.target.value)} className={inputClass} /></label>
        <label><span className="mb-1 block text-sm font-semibold">Cover label</span><input maxLength={200} disabled={pending} value={coverLabel} onChange={event => setCoverLabel(event.target.value)} className={inputClass} placeholder="Optional short label" /></label>
      </div>
    </RecipeDialogFrame>
  )
}

interface RecipeDraft {
  name: string
  description: string
  category: string
  cuisine: string
  servings: string
  prepMinutes: string
  cookMinutes: string
  difficulty: '' | RecipeDifficulty
  notes: string
  source: string
  isFavorite: boolean
  isArchived: boolean
  imageMode: 'none' | 'url' | 'upload'
  imageUrl: string
  imageFile: File | null
}

function recipeDraft(recipe: Recipe | null): RecipeDraft {
  return {
    name: recipe?.name ?? '',
    description: recipe?.description ?? '',
    category: recipe?.category ?? '',
    cuisine: recipe?.cuisine ?? '',
    servings: recipe?.servings?.toString() ?? '',
    prepMinutes: recipe?.prep_minutes?.toString() ?? '',
    cookMinutes: recipe?.cook_minutes?.toString() ?? '',
    difficulty: recipe?.difficulty ?? '',
    notes: recipe?.notes ?? '',
    source: recipe?.source ?? '',
    isFavorite: recipe?.is_favorite ?? false,
    isArchived: recipe?.is_archived ?? false,
    imageMode: recipe?.image_path ? 'upload' : recipe?.image_url ? 'url' : 'none',
    imageUrl: recipe?.image_url ?? '',
    imageFile: null,
  }
}

function nullableNumber(value: string, integer: boolean): number | null | 'invalid' {
  if (!value.trim()) return null
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0 || (integer && !Number.isInteger(parsed))) {
    return 'invalid'
  }
  return parsed
}

export function RecipeDialog({
  recipe,
  pending,
  error,
  onClose,
  onSave,
}: {
  recipe: Recipe | null
  pending: boolean
  error: string | null
  onClose: () => void
  onSave: (input: RecipeUpdate & { name: string; imageMode: RecipeDraft['imageMode']; imageFile: File | null }) => Promise<boolean>
}) {
  const [draft, setDraft] = useState(() => recipeDraft(recipe))
  const [validation, setValidation] = useState<string | null>(null)
  const set = <K extends keyof RecipeDraft>(key: K, value: RecipeDraft[K]) => {
    setDraft(previous => ({ ...previous, [key]: value }))
  }

  const save = async () => {
    const servings = nullableNumber(draft.servings, false)
    const prepMinutes = nullableNumber(draft.prepMinutes, true)
    const cookMinutes = nullableNumber(draft.cookMinutes, true)
    if (servings === 'invalid') return setValidation('Servings must be empty or a nonnegative number.')
    if (prepMinutes === 'invalid' || cookMinutes === 'invalid') return setValidation('Prep and cook minutes must be empty or nonnegative whole numbers.')
    let imageUrl: string | null = null
    if (draft.imageMode === 'url') { try { const url = new URL(draft.imageUrl.trim()); if (!['http:', 'https:'].includes(url.protocol)) throw new Error(); imageUrl = url.href } catch { return setValidation('Enter a valid HTTP or HTTPS image URL.') } }
    if (draft.imageMode === 'upload' && !draft.imageFile && !recipe?.image_path) return setValidation('Choose an image to upload.')
    setValidation(null)
    const saved = await onSave({
      name: draft.name.trim(),
      description: draft.description.trim(),
      category: draft.category.trim(),
      cuisine: draft.cuisine.trim(),
      servings,
      prep_minutes: prepMinutes,
      cook_minutes: cookMinutes,
      difficulty: draft.difficulty || null,
      notes: draft.notes.trim(),
      source: draft.source.trim() || null,
      image_url: imageUrl,
      image_path: null,
      imageMode: draft.imageMode,
      imageFile: draft.imageFile,
      is_favorite: draft.isFavorite,
      is_archived: draft.isArchived,
    })
    if (saved) onClose()
  }

  return (
    <RecipeDialogFrame
      title={recipe ? 'Edit Recipe' : 'Create Recipe'}
      eyebrow="Recipe editor"
      pending={pending}
      error={validation || error}
      onClose={onClose}
      footer={<Footer pending={pending} valid={Boolean(draft.name.trim())} saveLabel={recipe ? 'Save changes' : 'Create Recipe'} onClose={onClose} onSave={() => void save()} />}
    >
      <div className="grid gap-4">
        <label><span className="mb-1 block text-sm font-semibold">Name</span><input autoFocus maxLength={300} disabled={pending} value={draft.name} onChange={event => set('name', event.target.value)} className={inputClass} /></label>
        <label><span className="mb-1 block text-sm font-semibold">Description</span><textarea maxLength={20000} rows={2} disabled={pending} value={draft.description} onChange={event => set('description', event.target.value)} className={inputClass} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label><span className="mb-1 block text-sm font-semibold">Category</span><input maxLength={100} disabled={pending} value={draft.category} onChange={event => set('category', event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Cuisine</span><input maxLength={100} disabled={pending} value={draft.cuisine} onChange={event => set('cuisine', event.target.value)} className={inputClass} /></label>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <label><span className="mb-1 block text-sm font-semibold">Servings</span><input type="number" min="0" step="0.01" disabled={pending} value={draft.servings} onChange={event => set('servings', event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Prep minutes</span><input type="number" min="0" step="1" disabled={pending} value={draft.prepMinutes} onChange={event => set('prepMinutes', event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Cook minutes</span><input type="number" min="0" step="1" disabled={pending} value={draft.cookMinutes} onChange={event => set('cookMinutes', event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Difficulty</span><select disabled={pending} value={draft.difficulty} onChange={event => set('difficulty', event.target.value as RecipeDraft['difficulty'])} className={inputClass}><option value="">Not set</option><option value="EASY">Easy</option><option value="MEDIUM">Medium</option><option value="HARD">Hard</option></select></label>
        </div>
        <label><span className="mb-1 block text-sm font-semibold">Notes</span><textarea maxLength={20000} rows={3} disabled={pending} value={draft.notes} onChange={event => set('notes', event.target.value)} className={inputClass} /></label>
        <label><span className="mb-1 block text-sm font-semibold">Source</span><input maxLength={500} disabled={pending} value={draft.source} onChange={event => set('source', event.target.value)} className={inputClass} placeholder="Optional URL or source name" /></label>
        <fieldset className="rounded-xl border border-stone-200 p-3 dark:border-stone-700"><legend className="px-1 text-sm font-semibold">Recipe image</legend><div className="flex flex-wrap gap-4 text-sm"><label><input type="radio" checked={draft.imageMode === 'none'} disabled={pending} onChange={() => set('imageMode', 'none')} /> No image</label><label><input type="radio" checked={draft.imageMode === 'url'} disabled={pending} onChange={() => set('imageMode', 'url')} /> Image URL</label><label><input type="radio" checked={draft.imageMode === 'upload'} disabled={pending} onChange={() => set('imageMode', 'upload')} /> Upload image</label></div>{draft.imageMode === 'url' && <label className="mt-3 block"><span className="mb-1 block text-sm">Image URL</span><input type="url" maxLength={2000} disabled={pending} value={draft.imageUrl} onChange={event => set('imageUrl', event.target.value)} className={inputClass} placeholder="https://example.com/recipe.jpg" /></label>}{draft.imageMode === 'upload' && <label className="mt-3 block"><span className="mb-1 block text-sm">JPEG, PNG, or WebP (max 5 MB)</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={pending} onChange={event => { const file = event.target.files?.[0] ?? null; const message = file && validateRecipeImage(file); if (message) { setValidation(message); event.target.value = '' } else { setValidation(null); set('imageFile', file) } }} /></label>}</fieldset>
        <div className="flex flex-wrap gap-5">
          <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={draft.isFavorite} disabled={pending} onChange={event => set('isFavorite', event.target.checked)} /> Favorite</label>
          {recipe && <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={draft.isArchived} disabled={pending} onChange={event => set('isArchived', event.target.checked)} /> Archived</label>}
        </div>
      </div>
    </RecipeDialogFrame>
  )
}

export function IngredientDialog({
  ingredient,
  pending,
  error,
  onClose,
  onSave,
}: {
  ingredient: RecipeIngredient | null
  pending: boolean
  error: string | null
  onClose: () => void
  onSave: (input: RecipeIngredientUpdate & { name: string }) => Promise<boolean>
}) {
  const [name, setName] = useState(ingredient?.name ?? '')
  const [quantityText, setQuantityText] = useState(ingredient?.quantity_text ?? '')
  const [quantityValue, setQuantityValue] = useState(ingredient?.quantity_value?.toString() ?? '')
  const [unit, setUnit] = useState(ingredient?.unit ?? '')
  const [preparationNote, setPreparationNote] = useState(ingredient?.preparation_note ?? '')
  const [validation, setValidation] = useState<string | null>(null)

  const save = async () => {
    const numeric = nullableNumber(quantityValue, false)
    if (numeric === 'invalid') return setValidation('Numeric quantity must be empty or nonnegative.')
    setValidation(null)
    const saved = await onSave({
      name: name.trim(),
      quantity_text: quantityText.trim(),
      quantity_value: numeric,
      unit: unit.trim(),
      preparation_note: preparationNote.trim(),
    })
    if (saved) onClose()
  }

  return (
    <RecipeDialogFrame title={ingredient ? 'Edit Ingredient' : 'Add Ingredient'} eyebrow="Ingredient editor" pending={pending} error={validation || error} onClose={onClose} footer={<Footer pending={pending} valid={Boolean(name.trim())} saveLabel={ingredient ? 'Save changes' : 'Add Ingredient'} onClose={onClose} onSave={() => void save()} />}>
      <div className="grid gap-4">
        <label><span className="mb-1 block text-sm font-semibold">Name</span><input autoFocus maxLength={300} value={name} disabled={pending} onChange={event => setName(event.target.value)} className={inputClass} /></label>
        <div className="grid gap-3 sm:grid-cols-3">
          <label><span className="mb-1 block text-sm font-semibold">Quantity text</span><input maxLength={100} value={quantityText} disabled={pending} onChange={event => setQuantityText(event.target.value)} className={inputClass} placeholder="to taste, 1–2, one package" /></label>
          <label><span className="mb-1 block text-sm font-semibold">Numeric quantity</span><input type="number" min="0" step="any" value={quantityValue} disabled={pending} onChange={event => setQuantityValue(event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Unit</span><input maxLength={50} value={unit} disabled={pending} onChange={event => setUnit(event.target.value)} className={inputClass} /></label>
        </div>
        <label><span className="mb-1 block text-sm font-semibold">Preparation note</span><input maxLength={500} value={preparationNote} disabled={pending} onChange={event => setPreparationNote(event.target.value)} className={inputClass} /></label>
      </div>
    </RecipeDialogFrame>
  )
}

export function StepDialog({
  step,
  pending,
  error,
  onClose,
  onSave,
}: {
  step: RecipeStep | null
  pending: boolean
  error: string | null
  onClose: () => void
  onSave: (input: RecipeStepUpdate & { instruction: string }) => Promise<boolean>
}) {
  const [instruction, setInstruction] = useState(step?.instruction ?? '')
  const [duration, setDuration] = useState(step?.duration_minutes?.toString() ?? '')
  const [temperature, setTemperature] = useState(step?.temperature_value?.toString() ?? '')
  const [unit, setUnit] = useState<'' | TemperatureUnit>(step?.temperature_unit ?? '')
  const [validation, setValidation] = useState<string | null>(null)

  useEffect(() => {
    if (!temperature.trim()) setUnit('')
  }, [temperature])

  const save = async () => {
    const durationMinutes = nullableNumber(duration, true)
    const temperatureValue = nullableNumber(temperature, false)
    if (durationMinutes === 'invalid') return setValidation('Duration must be empty or a nonnegative whole number.')
    if (temperatureValue === 'invalid') return setValidation('Temperature must be empty or nonnegative.')
    setValidation(null)
    const saved = await onSave({
      instruction: instruction.trim(),
      duration_minutes: durationMinutes,
      temperature_value: temperatureValue,
      temperature_unit: temperatureValue === null ? null : unit || null,
    })
    if (saved) onClose()
  }

  return (
    <RecipeDialogFrame title={step ? 'Edit Step' : 'Add Step'} eyebrow="Step editor" pending={pending} error={validation || error} onClose={onClose} footer={<Footer pending={pending} valid={Boolean(instruction.trim())} saveLabel={step ? 'Save changes' : 'Add Step'} onClose={onClose} onSave={() => void save()} />}>
      <div className="grid gap-4">
        <label><span className="mb-1 block text-sm font-semibold">Instruction</span><textarea autoFocus maxLength={20000} rows={5} value={instruction} disabled={pending} onChange={event => setInstruction(event.target.value)} className={inputClass} /></label>
        <div className="grid gap-3 sm:grid-cols-3">
          <label><span className="mb-1 block text-sm font-semibold">Duration (minutes)</span><input type="number" min="0" step="1" value={duration} disabled={pending} onChange={event => setDuration(event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Temperature</span><input type="number" min="0" step="any" value={temperature} disabled={pending} onChange={event => setTemperature(event.target.value)} className={inputClass} /></label>
          <label><span className="mb-1 block text-sm font-semibold">Temperature unit</span><select value={unit} disabled={pending || !temperature.trim()} onChange={event => setUnit(event.target.value as '' | TemperatureUnit)} className={inputClass}><option value="">None</option><option value="F">°F</option><option value="C">°C</option></select></label>
        </div>
      </div>
    </RecipeDialogFrame>
  )
}
