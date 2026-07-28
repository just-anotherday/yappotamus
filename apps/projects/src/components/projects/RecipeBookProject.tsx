import { useEffect, useMemo, useState } from 'react'
import type { AddTaskOptions, UpdateTaskOptions } from '../../hooks/useTasks'
import type { Task, TaskMetadata } from '../../lib/types/database.types'

interface RecipeBookProjectProps {
  tasks: Task[]
  onAddTask: (options: AddTaskOptions | string, description?: string) => Promise<void>
  onUpdateTask: (id: string, options: UpdateTaskOptions | string, description?: string) => Promise<void>
  onDeleteTask: (id: string) => Promise<void>
}

interface RecipeDraft {
  title: string
  description: string
  prepMinutes: string
  cookMinutes: string
  servings: string
  ingredients: string
  steps: string
}

const emptyRecipe: RecipeDraft = {
  title: '',
  description: '',
  prepMinutes: '',
  cookMinutes: '',
  servings: '',
  ingredients: '',
  steps: '',
}

function lines(value: string) {
  return value.split('\n').map(line => line.trim()).filter(Boolean)
}

function optionalNumber(value: string) {
  const parsed = Number(value)
  return value.trim() && Number.isFinite(parsed) ? parsed : undefined
}

function metadataFromDraft(draft: RecipeDraft): TaskMetadata {
  return {
    content_type: 'recipe',
    prep_minutes: optionalNumber(draft.prepMinutes),
    cook_minutes: optionalNumber(draft.cookMinutes),
    servings: optionalNumber(draft.servings),
    ingredients: lines(draft.ingredients),
    steps: lines(draft.steps),
  }
}

function draftFromTask(task: Task): RecipeDraft {
  return {
    title: task.title,
    description: task.description ?? '',
    prepMinutes: task.metadata.prep_minutes?.toString() ?? '',
    cookMinutes: task.metadata.cook_minutes?.toString() ?? '',
    servings: task.metadata.servings?.toString() ?? '',
    ingredients: (task.metadata.ingredients ?? []).join('\n'),
    steps: (task.metadata.steps ?? []).join('\n'),
  }
}

export function RecipeBookProject({
  tasks,
  onAddTask,
  onUpdateTask,
  onDeleteTask,
}: RecipeBookProjectProps) {
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [editor, setEditor] = useState<{ mode: 'create' | 'edit'; draft: RecipeDraft } | null>(null)
  const [checkedIngredients, setCheckedIngredients] = useState<Set<number>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)

  const filteredRecipes = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return tasks
    return tasks.filter(task => `${task.title} ${task.description ?? ''}`.toLowerCase().includes(normalizedQuery))
  }, [query, tasks])

  useEffect(() => {
    if (tasks.length === 0) {
      setSelectedRecipeId(null)
      return
    }
    if (!selectedRecipeId || !tasks.some(task => task.id === selectedRecipeId)) {
      setSelectedRecipeId(tasks[0].id)
    }
  }, [selectedRecipeId, tasks])

  useEffect(() => {
    setCheckedIngredients(new Set())
  }, [selectedRecipeId])

  const selectedRecipe = tasks.find(task => task.id === selectedRecipeId)
  const ingredients = selectedRecipe?.metadata.ingredients ?? []
  const steps = selectedRecipe?.metadata.steps ?? []
  const totalMinutes = (selectedRecipe?.metadata.prep_minutes ?? 0) + (selectedRecipe?.metadata.cook_minutes ?? 0)

  useEffect(() => {
    setConfirmDelete(false)
  }, [editor?.mode, selectedRecipeId])

  const saveRecipe = async () => {
    if (!editor?.draft.title.trim()) return
    const payload = {
      title: editor.draft.title.trim(),
      description: editor.draft.description.trim(),
      metadata: metadataFromDraft(editor.draft),
    }

    if (editor.mode === 'create') {
      await onAddTask({ ...payload, status: 'TODO', priority: 'MEDIUM' })
    } else if (selectedRecipe) {
      await onUpdateTask(selectedRecipe.id, payload)
    }
    setEditor(null)
  }

  const deleteRecipe = async () => {
    if (!selectedRecipe) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    await onDeleteTask(selectedRecipe.id)
    setEditor(null)
  }

  return (
    <div className="grid min-h-[34rem] gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <aside className="rounded-2xl border border-orange-200 bg-orange-50/60 p-4 dark:border-orange-900/60 dark:bg-orange-950/20">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-800 dark:text-orange-300">Recipe book</p>
            <p className="mt-1 text-sm text-stone-500">{tasks.length} {tasks.length === 1 ? 'recipe' : 'recipes'}</p>
          </div>
          <button
            type="button"
            onClick={() => setEditor({ mode: 'create', draft: emptyRecipe })}
            className="rounded-lg bg-orange-700 px-3 py-2 text-xs font-semibold text-white hover:bg-orange-800"
          >
            Add
          </button>
        </div>

        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Find a recipe…"
          className="mt-4 w-full rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm outline-none focus:border-orange-600 dark:border-orange-900 dark:bg-stone-950 dark:text-white"
        />

        <nav className="mt-3 space-y-1" aria-label="Recipes">
          {filteredRecipes.map(recipe => (
            <button
              key={recipe.id}
              type="button"
              onClick={() => setSelectedRecipeId(recipe.id)}
              className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                recipe.id === selectedRecipeId
                  ? 'bg-white text-orange-900 shadow-sm ring-1 ring-orange-200 dark:bg-stone-900 dark:text-orange-200 dark:ring-orange-900'
                  : 'text-stone-700 hover:bg-white/70 dark:text-stone-200 dark:hover:bg-stone-900/70'
              }`}
            >
              <span className="block truncate text-sm font-semibold">{recipe.title}</span>
              {recipe.metadata.cook_minutes !== undefined && (
                <span className="mt-0.5 block text-xs text-stone-500">{recipe.metadata.cook_minutes} min cook</span>
              )}
            </button>
          ))}
        </nav>
      </aside>

      <section className="min-w-0">
        {selectedRecipe ? (
          <article>
            <div className="flex flex-col gap-4 border-b border-stone-200 pb-5 dark:border-stone-800 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-700 dark:text-orange-300">Cooking instructions</p>
                <h3 className="mt-2 text-3xl font-semibold tracking-tight text-stone-950 dark:text-white">{selectedRecipe.title}</h3>
                {selectedRecipe.description && (
                  <p className="mt-2 max-w-2xl leading-7 text-stone-600 dark:text-stone-300">{selectedRecipe.description}</p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditor({ mode: 'edit', draft: draftFromTask(selectedRecipe) })}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-100 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
                >
                  Edit recipe
                </button>
              </div>
            </div>

            <dl className="my-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {selectedRecipe.metadata.prep_minutes !== undefined && (
                <div className="rounded-xl bg-stone-100 p-3 dark:bg-stone-800">
                  <dt className="text-xs uppercase tracking-wide text-stone-500">Prep</dt>
                  <dd className="mt-1 font-semibold text-stone-900 dark:text-white">{selectedRecipe.metadata.prep_minutes} min</dd>
                </div>
              )}
              {selectedRecipe.metadata.cook_minutes !== undefined && (
                <div className="rounded-xl bg-stone-100 p-3 dark:bg-stone-800">
                  <dt className="text-xs uppercase tracking-wide text-stone-500">Cook</dt>
                  <dd className="mt-1 font-semibold text-stone-900 dark:text-white">{selectedRecipe.metadata.cook_minutes} min</dd>
                </div>
              )}
              {totalMinutes > 0 && (
                <div className="rounded-xl bg-stone-100 p-3 dark:bg-stone-800">
                  <dt className="text-xs uppercase tracking-wide text-stone-500">Total</dt>
                  <dd className="mt-1 font-semibold text-stone-900 dark:text-white">{totalMinutes} min</dd>
                </div>
              )}
              {selectedRecipe.metadata.servings !== undefined && (
                <div className="rounded-xl bg-stone-100 p-3 dark:bg-stone-800">
                  <dt className="text-xs uppercase tracking-wide text-stone-500">Serves</dt>
                  <dd className="mt-1 font-semibold text-stone-900 dark:text-white">{selectedRecipe.metadata.servings}</dd>
                </div>
              )}
            </dl>

            <div className="grid gap-8 xl:grid-cols-[minmax(15rem,0.8fr)_minmax(20rem,1.2fr)]">
              <section>
                <div className="mb-3 flex items-baseline justify-between">
                  <h4 className="text-xl font-semibold text-stone-900 dark:text-white">Ingredients</h4>
                  {ingredients.length > 0 && <span className="text-xs text-stone-500">{checkedIngredients.size}/{ingredients.length} ready</span>}
                </div>
                {ingredients.length > 0 ? (
                  <ul className="overflow-hidden rounded-xl border border-stone-200 dark:border-stone-800">
                    {ingredients.map((ingredient, index) => (
                      <li key={`${ingredient}-${index}`} className="border-b border-stone-100 last:border-b-0 dark:border-stone-800">
                        <label className="flex cursor-pointer gap-3 px-4 py-3">
                          <input
                            type="checkbox"
                            checked={checkedIngredients.has(index)}
                            onChange={() => {
                              setCheckedIngredients(previous => {
                                const next = new Set(previous)
                                if (next.has(index)) next.delete(index)
                                else next.add(index)
                                return next
                              })
                            }}
                            className="mt-0.5 size-4 accent-orange-700"
                          />
                          <span className={checkedIngredients.has(index) ? 'text-stone-400 line-through' : 'text-stone-700 dark:text-stone-200'}>
                            {ingredient}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="rounded-xl border border-dashed border-stone-300 p-5 text-sm text-stone-500 dark:border-stone-700">
                    Add ingredients while editing this recipe.
                  </p>
                )}
              </section>

              <section>
                <h4 className="mb-3 text-xl font-semibold text-stone-900 dark:text-white">Method</h4>
                {steps.length > 0 ? (
                  <ol className="space-y-5">
                    {steps.map((step, index) => (
                      <li key={`${step}-${index}`} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-3">
                        <span className="grid size-9 place-items-center rounded-full bg-orange-700 text-sm font-bold text-white">{index + 1}</span>
                        <p className="pt-1 leading-7 text-stone-700 dark:text-stone-200">{step}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="rounded-xl border border-dashed border-stone-300 p-5 text-sm text-stone-500 dark:border-stone-700">
                    Add one instruction per line while editing this recipe.
                  </p>
                )}
              </section>
            </div>
          </article>
        ) : (
          <div className="grid min-h-[32rem] place-items-center rounded-2xl border border-dashed border-stone-300 p-8 text-center dark:border-stone-700">
            <div>
              <p className="text-xl font-semibold text-stone-800 dark:text-white">Start your recipe collection.</p>
              <p className="mt-2 text-sm text-stone-500">Save ingredients and instructions so dinner does not depend on memory.</p>
              <button
                type="button"
                onClick={() => setEditor({ mode: 'create', draft: emptyRecipe })}
                className="mt-5 rounded-lg bg-orange-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-orange-800"
              >
                Add first recipe
              </button>
            </div>
          </div>
        )}
      </section>

      {editor && (
        <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-stone-950/45 p-4 backdrop-blur-sm">
          <div className="my-6 w-full max-w-3xl rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-700 dark:text-orange-300">
                  {editor.mode === 'create' ? 'New recipe' : 'Recipe editor'}
                </p>
                <h3 className="mt-1 text-2xl font-semibold text-stone-950 dark:text-white">
                  {editor.mode === 'create' ? 'Add cooking instructions' : `Edit ${selectedRecipe?.title}`}
                </h3>
              </div>
              <button type="button" onClick={() => setEditor(null)} className="text-sm text-stone-500 hover:text-stone-900 dark:hover:text-white">Close</button>
            </div>

            <div className="mt-5 grid gap-4">
              <label>
                <span className="mb-1 block text-sm font-semibold text-stone-700 dark:text-stone-200">Recipe name</span>
                <input
                  value={editor.draft.title}
                  onChange={event => setEditor({ ...editor, draft: { ...editor.draft, title: event.target.value } })}
                  className="w-full rounded-lg border border-stone-300 px-3 py-2.5 outline-none focus:border-orange-600 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                  autoFocus
                />
              </label>
              <label>
                <span className="mb-1 block text-sm font-semibold text-stone-700 dark:text-stone-200">Short description</span>
                <textarea
                  value={editor.draft.description}
                  onChange={event => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-stone-300 px-3 py-2.5 outline-none focus:border-orange-600 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                />
              </label>
              <div className="grid grid-cols-3 gap-3">
                {[
                  ['Prep minutes', 'prepMinutes'],
                  ['Cook minutes', 'cookMinutes'],
                  ['Servings', 'servings'],
                ].map(([label, field]) => (
                  <label key={field}>
                    <span className="mb-1 block text-sm font-semibold text-stone-700 dark:text-stone-200">{label}</span>
                    <input
                      type="number"
                      min="0"
                      value={editor.draft[field as keyof RecipeDraft]}
                      onChange={event => setEditor({ ...editor, draft: { ...editor.draft, [field]: event.target.value } })}
                      className="w-full min-w-0 rounded-lg border border-stone-300 px-3 py-2.5 outline-none focus:border-orange-600 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                    />
                  </label>
                ))}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  <span className="mb-1 block text-sm font-semibold text-stone-700 dark:text-stone-200">Ingredients</span>
                  <textarea
                    value={editor.draft.ingredients}
                    onChange={event => setEditor({ ...editor, draft: { ...editor.draft, ingredients: event.target.value } })}
                    rows={9}
                    placeholder={'1 cup flour\n2 eggs\nPinch of salt'}
                    className="w-full rounded-lg border border-stone-300 px-3 py-2.5 leading-6 outline-none focus:border-orange-600 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                  />
                  <span className="text-xs text-stone-500">One ingredient per line</span>
                </label>
                <label>
                  <span className="mb-1 block text-sm font-semibold text-stone-700 dark:text-stone-200">Instructions</span>
                  <textarea
                    value={editor.draft.steps}
                    onChange={event => setEditor({ ...editor, draft: { ...editor.draft, steps: event.target.value } })}
                    rows={9}
                    placeholder={'Preheat the oven.\nMix the ingredients.\nBake until golden.'}
                    className="w-full rounded-lg border border-stone-300 px-3 py-2.5 leading-6 outline-none focus:border-orange-600 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                  />
                  <span className="text-xs text-stone-500">One step per line; numbering is automatic</span>
                </label>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <div>
                {editor.mode === 'edit' && (
                  <button type="button" onClick={deleteRecipe} className="rounded-lg px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40">
                    {confirmDelete ? 'Click again to delete' : 'Delete recipe'}
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => setEditor(null)} className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-700 dark:border-stone-700 dark:text-stone-200">
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveRecipe}
                  disabled={!editor.draft.title.trim()}
                  className="rounded-lg bg-orange-700 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-800 disabled:opacity-45"
                >
                  Save recipe
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
