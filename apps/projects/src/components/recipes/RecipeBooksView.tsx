import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { useRecipeBooks } from '../../hooks/useRecipeBooks'
import { useRecipeIngredients } from '../../hooks/useRecipeIngredients'
import { useRecipes } from '../../hooks/useRecipes'
import { useRecipeSteps } from '../../hooks/useRecipeSteps'
import type {
  Recipe,
  RecipeIngredient,
  RecipeIngredientUpdate,
  RecipeStep,
  RecipeStepUpdate,
  RecipeUpdate,
} from '../../types/recipeBooks'
import {
  IngredientDialog,
  RecipeBookDialog,
  RecipeDialog,
  StepDialog,
} from './RecipeDialogs'
import { ReminderControl } from '../reminders/ReminderControl'
import { Button } from '../shared/Button'
import { DialogFrame } from '../shared/DialogFrame'
import { IconButton } from '../shared/IconButton'

interface RecipeBooksViewProps {
  userId: string
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function ErrorBanner({ children }: { children: string }) {
  return <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{children}</p>
}

function DeleteConfirmation({
  kind,
  name,
  pending,
  cancelRef,
  onClose,
  onConfirm,
}: {
  kind: 'collection' | 'recipe'
  name: string
  pending: boolean
  cancelRef: RefObject<HTMLButtonElement | null>
  onClose: () => void
  onConfirm: () => void
}) {
  const isCollection = kind === 'collection'
  const label = isCollection ? 'Recipe Collection' : 'Recipe'
  const detail = isCollection
    ? 'This permanently deletes the collection and all of its recipes, ingredients, and steps.'
    : 'This permanently deletes the recipe and all of its ingredients and steps.'

  return (
    <DialogFrame labelledBy="recipe-delete-confirmation-title" pending={pending} onClose={onClose} initialFocusRef={cancelRef} className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-red-700 dark:text-red-300">Permanent action</p>
      <h2 id="recipe-delete-confirmation-title" className="mt-1 text-xl font-semibold text-stone-950 dark:text-white">Delete {label}?</h2>
      <p className="mt-3 text-sm text-stone-700 dark:text-stone-300"><strong>{name}</strong> will be deleted. {detail} This cannot be undone.</p>
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <Button ref={cancelRef} onClick={onClose} disabled={pending} tone="orange" variant="secondary">Cancel</Button>
        <Button onClick={onConfirm} disabled={pending} variant="destructive">{pending ? 'Deleting…' : `Delete ${label}`}</Button>
      </div>
    </DialogFrame>
  )
}

export function RecipeBooksView({
  userId,
  selectedRecordId,
  onSelectedRecordChange,
}: RecipeBooksViewProps) {
  const [showArchivedBooks, setShowArchivedBooks] = useState(false)
  const [showArchivedRecipes, setShowArchivedRecipes] = useState(false)
  const [bookEditor, setBookEditor] = useState<'create' | 'edit' | null>(null)
  const [recipeEditor, setRecipeEditor] = useState<'create' | 'edit' | null>(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState<'collection' | 'recipe' | null>(null)
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const deleteCancelRef = useRef<HTMLButtonElement>(null)
  const selectionKey = `organizer:${userId}:recipe-book-selection`
  const booksState = useRecipeBooks(userId, showArchivedBooks)
  const selectedBook = booksState.books.find(book => book.id === selectedRecordId) ?? null
  const recipesState = useRecipes(selectedBook?.id ?? null, showArchivedRecipes)
  const selectedRecipe = recipesState.recipes.find(recipe => recipe.id === selectedRecipeId) ?? null
  const ingredientsState = useRecipeIngredients(selectedRecipe?.id ?? null)
  const stepsState = useRecipeSteps(selectedRecipe?.id ?? null)

  useEffect(() => {
    if (selectedRecordId) return
    const stored = localStorage.getItem(selectionKey)
    if (stored && uuidPattern.test(stored)) onSelectedRecordChange(stored)
  }, [onSelectedRecordChange, selectedRecordId, selectionKey])

  useEffect(() => {
    if (booksState.loading) return
    if (!booksState.books.length) {
      if (selectedRecordId) onSelectedRecordChange(null)
      localStorage.removeItem(selectionKey)
      return
    }
    if (!selectedBook) {
      const fallback = booksState.books.find(book => !book.is_archived) ?? booksState.books[0]
      onSelectedRecordChange(fallback.id)
      localStorage.setItem(selectionKey, fallback.id)
    }
  }, [booksState.books, booksState.loading, onSelectedRecordChange, selectedBook, selectedRecordId, selectionKey])

  useEffect(() => {
    if (selectedRecordId && selectedBook) localStorage.setItem(selectionKey, selectedRecordId)
  }, [selectedBook, selectedRecordId, selectionKey])

  useEffect(() => {
    setSelectedRecipeId(previous => {
      if (previous && recipesState.recipes.some(recipe => recipe.id === previous)) return previous
      return recipesState.recipes.find(recipe => !recipe.is_archived)?.id
        ?? recipesState.recipes[0]?.id
        ?? null
    })
  }, [recipesState.recipes])

  const filteredRecipes = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return normalized
      ? recipesState.recipes.filter(recipe => (
        `${recipe.name} ${recipe.description} ${recipe.category} ${recipe.cuisine}`
          .toLowerCase()
          .includes(normalized)
      ))
      : recipesState.recipes
  }, [query, recipesState.recipes])

  const saveBook = async (input: { name: string; description: string; cover_label?: string | null }) => {
    const result = bookEditor === 'edit' && selectedBook
      ? await booksState.update(selectedBook.id, input)
      : await booksState.create(input.name, input.description, input.cover_label ?? null)
    if (result) onSelectedRecordChange(result.id)
    return Boolean(result)
  }

  const saveRecipe = async (input: RecipeUpdate & { name: string }) => {
    const result = recipeEditor === 'edit' && selectedRecipe
      ? await recipesState.update(selectedRecipe.id, input)
      : await recipesState.create({
        ...input,
        recipe_book_id: selectedBook?.id ?? '',
        user_id: userId,
      })
    if (result) setSelectedRecipeId(result.id)
    return Boolean(result)
  }

  const deleteBook = async () => {
    if (!selectedBook) return
    const removed = await booksState.remove(selectedBook.id)
    if (removed) {
      onSelectedRecordChange(null)
      setSelectedRecipeId(null)
      localStorage.removeItem(selectionKey)
      setDeleteConfirmation(null)
    }
  }

  const deleteRecipe = async () => {
    if (!selectedRecipe) return
    const removed = await recipesState.remove(selectedRecipe.id)
    if (removed) {
      setSelectedRecipeId(null)
      setDeleteConfirmation(null)
    }
  }

  if (booksState.loading && !booksState.books.length) {
    return <div className="grid min-h-96 place-items-center text-sm text-stone-500" role="status">Loading Recipe Collections…</div>
  }

  return (
    <>
      {(booksState.error || recipesState.error) && <ErrorBanner>{booksState.error || recipesState.error || ''}</ErrorBanner>}
      <section className="rounded-3xl border border-stone-200 bg-white p-4 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 sm:p-6">
        <header className="flex flex-col gap-4 border-b border-stone-200 pb-5 dark:border-stone-800 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-700 dark:text-orange-300">Cooking collections</p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight text-stone-950 dark:text-white">Recipe Collections</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="min-w-56 flex-1">
              <span className="sr-only">Selected Recipe Collection</span>
              <select value={selectedRecordId ?? ''} onChange={event => onSelectedRecordChange(event.target.value || null)} className="h-10 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-orange-600 focus:ring-2 focus:ring-orange-600/15 dark:border-stone-700 dark:bg-stone-950 dark:text-white">
                <option value="">Select a Recipe Collection…</option>
                {booksState.books.map(book => <option key={book.id} value={book.id}>{book.is_archived ? 'Archived — ' : ''}{book.name}</option>)}
              </select>
            </label>
            <Button type="button" onClick={() => setBookEditor('create')} tone="orange" variant="primary">New Recipe Collection</Button>
            <label className="flex h-10 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-700 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-200">
              <input type="checkbox" checked={showArchivedBooks} onChange={event => setShowArchivedBooks(event.target.checked)} className="rounded border-stone-300 text-orange-700 focus:ring-orange-600/30 dark:border-stone-700" /> Archived books
            </label>
          </div>
        </header>

        {!selectedBook ? (
          <EmptyWorkspace onCreate={() => setBookEditor('create')} />
        ) : (
          <>
            <BookHeader
              book={selectedBook}
              pending={booksState.pending}
              onEdit={() => setBookEditor('edit')}
              onArchive={() => void booksState.setArchived(selectedBook.id, !selectedBook.is_archived)}
              onDelete={() => setDeleteConfirmation('collection')}
            />
            <div className="grid min-h-[32rem] gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]">
              <RecipeSidebar
                recipes={filteredRecipes}
                total={recipesState.recipes.length}
                selectedId={selectedRecipeId}
                loading={recipesState.loading}
                pending={recipesState.pending}
                query={query}
                showArchived={showArchivedRecipes}
                onQuery={setQuery}
                onShowArchived={setShowArchivedRecipes}
                onSelect={setSelectedRecipeId}
                onCreate={() => setRecipeEditor('create')}
              />
              <div className="min-w-0">
                {selectedRecipe ? (
                  <RecipeDetail
                    recipe={selectedRecipe}
                    userId={userId}
                    recipesPending={recipesState.pending}
                    recipesError={recipesState.error}
                    ingredientsState={ingredientsState}
                    stepsState={stepsState}
                    onEdit={() => setRecipeEditor('edit')}
                    onDelete={() => setDeleteConfirmation('recipe')}
                    onFavorite={() => void recipesState.setFavorite(selectedRecipe.id, !selectedRecipe.is_favorite)}
                    onArchive={() => void recipesState.setArchived(selectedRecipe.id, !selectedRecipe.is_archived)}
                  />
                ) : <EmptyRecipe onCreate={() => setRecipeEditor('create')} />}
              </div>
            </div>
          </>
        )}
      </section>

      {bookEditor && <RecipeBookDialog book={bookEditor === 'edit' ? selectedBook : null} pending={booksState.pending} error={booksState.error} onClose={() => setBookEditor(null)} onSave={saveBook} />}
      {recipeEditor && selectedBook && <RecipeDialog recipe={recipeEditor === 'edit' ? selectedRecipe : null} pending={recipesState.pending} error={recipesState.error} onClose={() => setRecipeEditor(null)} onSave={saveRecipe} />}
      {deleteConfirmation && (
        <DeleteConfirmation
          kind={deleteConfirmation}
          name={deleteConfirmation === 'collection' ? selectedBook?.name ?? '' : selectedRecipe?.name ?? ''}
          pending={deleteConfirmation === 'collection' ? booksState.pending : recipesState.pending}
          cancelRef={deleteCancelRef}
          onClose={() => setDeleteConfirmation(null)}
          onConfirm={() => void (deleteConfirmation === 'collection' ? deleteBook() : deleteRecipe())}
        />
      )}
    </>
  )
}

function EmptyWorkspace({ onCreate }: { onCreate: () => void }) {
  return <div className="grid min-h-[28rem] place-items-center text-center"><div><p className="text-xl font-semibold">Create your first Recipe Collection.</p><p className="mt-2 text-sm text-stone-500">Organize recipes, ingredients, and cooking steps in one place.</p><Button type="button" onClick={onCreate} tone="orange" variant="primary" className="mt-5">Create Recipe Collection</Button></div></div>
}

function BookHeader({
  book,
  pending,
  onEdit,
  onArchive,
  onDelete,
}: {
  book: ReturnType<typeof useRecipeBooks>['books'][number]
  pending: boolean
  onEdit: () => void
  onArchive: () => void
  onDelete: () => void
}) {
  return (
    <div className="flex flex-col gap-3 py-5 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-2xl font-semibold">{book.name}</h3>
          {book.cover_label && <span className="rounded-full bg-orange-100 px-2.5 py-1 text-xs font-semibold text-orange-800 dark:bg-orange-950 dark:text-orange-200">{book.cover_label}</span>}
          {book.is_archived && <span className="rounded-full bg-stone-200 px-2.5 py-1 text-xs font-semibold dark:bg-stone-700">Archived</span>}
        </div>
        {book.description && <p className="mt-1 max-w-2xl text-sm text-stone-500">{book.description}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={pending} onClick={onEdit} tone="orange" variant="secondary">Edit Book</Button>
        <Button type="button" disabled={pending} onClick={onArchive} tone="orange" variant="tertiary">{book.is_archived ? 'Unarchive Book' : 'Archive Book'}</Button>
        <Button type="button" disabled={pending} onClick={onDelete} variant="destructive">Delete Book</Button>
      </div>
    </div>
  )
}

function RecipeSidebar({
  recipes,
  total,
  selectedId,
  loading,
  pending,
  query,
  showArchived,
  onQuery,
  onShowArchived,
  onSelect,
  onCreate,
}: {
  recipes: Recipe[]
  total: number
  selectedId: string | null
  loading: boolean
  pending: boolean
  query: string
  showArchived: boolean
  onQuery: (value: string) => void
  onShowArchived: (value: boolean) => void
  onSelect: (id: string) => void
  onCreate: () => void
}) {
  return (
    <aside className="rounded-2xl border border-orange-200 bg-orange-50/60 p-4 dark:border-orange-900/60 dark:bg-orange-950/20">
      <div className="flex items-center justify-between gap-2">
        <div><p className="text-sm font-semibold">Recipes</p><p className="text-xs text-stone-500">{total} total</p></div>
        <Button type="button" disabled={pending} onClick={onCreate} tone="orange" variant="primary" className="min-h-9 px-3 py-1 text-xs">Add Recipe</Button>
      </div>
      <input aria-label="Filter recipes by name, description, category, or cuisine" value={query} onChange={event => onQuery(event.target.value)} placeholder="Name, description, category, or cuisine…" className="mt-4 min-h-10 w-full rounded-lg border border-orange-200 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-orange-600 focus:ring-2 focus:ring-orange-600/15 dark:border-orange-900 dark:bg-stone-950 dark:text-white" />
      <label className="mt-3 flex min-h-10 items-center gap-2 text-xs"><input type="checkbox" checked={showArchived} onChange={event => onShowArchived(event.target.checked)} className="rounded border-orange-300 text-orange-700 focus:ring-orange-600/30 dark:border-orange-900" /> Show archived recipes</label>
      {loading && !recipes.length ? <p className="mt-6 text-sm text-stone-500" role="status">Loading recipes…</p> : recipes.length ? (
        <nav className="mt-3 space-y-1" aria-label="Recipes">
          {recipes.map(recipe => (
            <button key={recipe.id} type="button" onClick={() => onSelect(recipe.id)} className={`w-full rounded-lg px-3 py-2.5 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-orange-600 focus-visible:ring-offset-2 focus-visible:ring-offset-orange-50 dark:focus-visible:ring-orange-400 dark:focus-visible:ring-offset-orange-950 ${recipe.id === selectedId ? 'bg-white shadow-sm ring-1 ring-orange-200 dark:bg-stone-900 dark:ring-orange-900' : 'hover:bg-white/70 dark:hover:bg-stone-900/70'}`}>
              <span className="flex items-center gap-1 truncate text-sm font-semibold">{recipe.is_favorite && <span aria-label="Favorite">★</span>}{recipe.name}</span>
              <span className="mt-0.5 block text-xs text-stone-500">{recipe.is_archived ? 'Archived' : timeSummary(recipe)}</span>
            </button>
          ))}
        </nav>
      ) : <p className="mt-6 text-sm text-stone-500">No recipes match this view. Add one or adjust the filters.</p>}
    </aside>
  )
}

function EmptyRecipe({ onCreate }: { onCreate: () => void }) {
  return <div className="grid min-h-80 place-items-center rounded-2xl border border-dashed border-stone-300 p-8 text-center dark:border-stone-700"><div><p className="text-lg font-semibold">No recipe selected.</p><p className="mt-2 text-sm text-stone-500">Create a recipe to begin adding ingredients and steps.</p><Button type="button" onClick={onCreate} tone="orange" variant="primary" className="mt-4">Add Recipe</Button></div></div>
}

function timeSummary(recipe: Recipe) {
  const minutes = (recipe.prep_minutes ?? 0) + (recipe.cook_minutes ?? 0)
  const parts = [minutes ? `${minutes} min` : '', recipe.servings !== null ? `${recipe.servings} servings` : ''].filter(Boolean)
  return parts.join(' · ') || 'No timing details'
}

interface ChildState<T> {
  loading: boolean
  pending: boolean
  error: string | null
  remove: (id: string) => Promise<unknown>
  reorder: (items: T[]) => Promise<unknown>
}

function RecipeDetail({
  recipe,
  userId,
  recipesPending,
  recipesError,
  ingredientsState,
  stepsState,
  onEdit,
  onDelete,
  onFavorite,
  onArchive,
}: {
  recipe: Recipe
  userId: string
  recipesPending: boolean
  recipesError: string | null
  ingredientsState: ReturnType<typeof useRecipeIngredients>
  stepsState: ReturnType<typeof useRecipeSteps>
  onEdit: () => void
  onDelete: () => void
  onFavorite: () => void
  onArchive: () => void
}) {
  const [ingredientEditor, setIngredientEditor] = useState<RecipeIngredient | 'new' | null>(null)
  const [stepEditor, setStepEditor] = useState<RecipeStep | 'new' | null>(null)

  const saveIngredient = async (input: RecipeIngredientUpdate & { name: string }) => {
    const result = ingredientEditor !== 'new' && ingredientEditor
      ? await ingredientsState.update(ingredientEditor.id, input)
      : await ingredientsState.create({ ...input, recipe_id: recipe.id, user_id: userId, position: ingredientsState.ingredients.length })
    return Boolean(result)
  }

  const saveStep = async (input: RecipeStepUpdate & { instruction: string }) => {
    const result = stepEditor !== 'new' && stepEditor
      ? await stepsState.update(stepEditor.id, input)
      : await stepsState.create({ ...input, recipe_id: recipe.id, user_id: userId, position: stepsState.steps.length })
    return Boolean(result)
  }

  return (
    <article>
      {(recipesError || ingredientsState.error || stepsState.error) && <ErrorBanner>{recipesError || ingredientsState.error || stepsState.error || ''}</ErrorBanner>}
      <header className="flex flex-col gap-4 border-b border-stone-200 pb-5 dark:border-stone-800 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-3xl font-semibold tracking-tight">{recipe.name}</h3>
            {recipe.is_favorite && <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200">★ Favorite</span>}
            {recipe.is_archived && <span className="rounded-full bg-stone-200 px-2.5 py-1 text-xs font-semibold dark:bg-stone-700">Archived</span>}
          </div>
          {recipe.description && <p className="mt-2 max-w-2xl leading-7 text-stone-600 dark:text-stone-300">{recipe.description}</p>}
          <p className="mt-2 text-sm text-stone-500">{[recipe.category, recipe.cuisine, recipe.difficulty?.toLowerCase()].filter(Boolean).join(' · ')}</p>
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <ReminderControl target={{ kind: 'recipe', id: recipe.id, label: recipe.name }} />
          <Button type="button" disabled={recipesPending} onClick={onFavorite} tone="orange" variant="tertiary">{recipe.is_favorite ? 'Unfavorite' : 'Favorite'}</Button>
          <Button type="button" disabled={recipesPending} onClick={onEdit} tone="orange" variant="secondary">Edit</Button>
          <Button type="button" disabled={recipesPending} onClick={onArchive} tone="orange" variant="tertiary">{recipe.is_archived ? 'Unarchive' : 'Archive'}</Button>
          <Button type="button" disabled={recipesPending} onClick={onDelete} variant="destructive">Delete</Button>
        </div>
      </header>

      <dl className="my-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Prep" value={recipe.prep_minutes === null ? '—' : `${recipe.prep_minutes} min`} />
        <Stat label="Cook" value={recipe.cook_minutes === null ? '—' : `${recipe.cook_minutes} min`} />
        <Stat label="Total" value={(recipe.prep_minutes ?? 0) + (recipe.cook_minutes ?? 0) ? `${(recipe.prep_minutes ?? 0) + (recipe.cook_minutes ?? 0)} min` : '—'} />
        <Stat label="Servings" value={recipe.servings?.toString() ?? '—'} />
      </dl>

      <div className="grid gap-8 xl:grid-cols-2">
        <ChildList title="Ingredients" empty="No ingredients yet." items={ingredientsState.ingredients} state={ingredientsState} onAdd={() => setIngredientEditor('new')} onEdit={item => setIngredientEditor(item)} render={(item: RecipeIngredient) => <span>{[item.quantity_text, item.quantity_value, item.unit, item.name, item.preparation_note].filter(value => value !== '' && value !== null).join(' ')}</span>} />
        <ChildList title="Steps" empty="No steps yet." items={stepsState.steps} state={stepsState} onAdd={() => setStepEditor('new')} onEdit={item => setStepEditor(item)} numbered render={(item: RecipeStep) => <span>{item.instruction}{item.duration_minutes !== null ? ` · ${item.duration_minutes} min` : ''}{item.temperature_value !== null ? ` · ${item.temperature_value}°${item.temperature_unit ?? ''}` : ''}</span>} />
      </div>

      {recipe.notes && <section className="mt-7"><h4 className="text-lg font-semibold">Notes</h4><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-stone-600 dark:text-stone-300">{recipe.notes}</p></section>}
      {recipe.source && <p className="mt-4 break-all text-sm text-stone-500"><strong>Source:</strong> {recipe.source}</p>}
      {ingredientEditor && <IngredientDialog ingredient={ingredientEditor === 'new' ? null : ingredientEditor} pending={ingredientsState.pending} error={ingredientsState.error} onClose={() => setIngredientEditor(null)} onSave={saveIngredient} />}
      {stepEditor && <StepDialog step={stepEditor === 'new' ? null : stepEditor} pending={stepsState.pending} error={stepsState.error} onClose={() => setStepEditor(null)} onSave={saveStep} />}
    </article>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-stone-100 p-3 dark:bg-stone-800"><dt className="text-xs uppercase tracking-wide text-stone-500">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>
}

function ChildList<T extends { id: string }>({
  title,
  empty,
  items,
  state,
  onAdd,
  onEdit,
  render,
  numbered = false,
}: {
  title: string
  empty: string
  items: T[]
  state: ChildState<T>
  onAdd: () => void
  onEdit: (item: T) => void
  render: (item: T) => ReactNode
  numbered?: boolean
}) {
  const move = async (index: number, offset: number) => {
    const destination = index + offset
    if (destination < 0 || destination >= items.length) return
    const reordered = [...items]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(destination, 0, moved)
    await state.reorder(reordered)
  }
  const remove = async (item: T) => {
    if (window.confirm(`Delete this ${title === 'Steps' ? 'step' : 'ingredient'}?`)) await state.remove(item.id)
  }
  const label = title === 'Steps' ? 'Step' : 'Ingredient'

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3"><h4 className="text-xl font-semibold">{title}</h4><Button type="button" disabled={state.pending} onClick={onAdd} tone="orange" variant="primary" className="min-h-9 px-3 py-1 text-xs">Add</Button></div>
      {state.loading && !items.length ? <p role="status" className="text-sm text-stone-500">Loading {title.toLowerCase()}…</p> : items.length ? (
        <ol className="space-y-2">
          {items.map((item, index) => (
            <li key={item.id} className="flex flex-col items-stretch gap-3 rounded-xl border border-stone-200 p-3 dark:border-stone-800 sm:flex-row sm:items-start">
              {numbered && <span className="grid size-7 shrink-0 place-items-center rounded-full bg-orange-700 text-xs font-bold text-white">{index + 1}</span>}
              <div className="min-w-0 flex-1 text-sm leading-6">{render(item)}</div>
              <div className="flex flex-wrap justify-end gap-1 sm:shrink-0">
                <IconButton ariaLabel={`Move ${label} up`} disabled={state.pending || index === 0} onClick={() => void move(index, -1)} tone="orange">↑</IconButton>
                <IconButton ariaLabel={`Move ${label} down`} disabled={state.pending || index === items.length - 1} onClick={() => void move(index, 1)} tone="orange">↓</IconButton>
                <Button type="button" aria-label={`Edit ${label}`} disabled={state.pending} onClick={() => onEdit(item)} tone="orange" variant="secondary" className="min-h-10 px-3 py-2 text-xs">Edit</Button>
                <Button type="button" aria-label={`Delete ${label}`} disabled={state.pending} onClick={() => void remove(item)} variant="destructive" className="min-h-10 px-3 py-2 text-xs">Delete</Button>
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="rounded-xl border border-dashed border-stone-300 p-5 text-sm text-stone-500 dark:border-stone-700">{empty}</p>}
      <p className="mt-2 text-xs text-stone-500">Ordering uses contiguous positions; failed multirow saves are refreshed from Supabase.</p>
    </section>
  )
}
