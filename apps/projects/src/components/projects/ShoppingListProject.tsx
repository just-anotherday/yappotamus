import { useEffect, useMemo, useRef, useState } from 'react'
import type { GeneralShoppingItemInput, UpdateGeneralShoppingItemInput } from '../../hooks/useGeneralShoppingItems'
import type { AddTaskOptions, UpdateTaskOptions } from '../../hooks/useTasks'
import type { GeneralShoppingItem, ShoppingStore, Task, TaskMetadata } from '../../lib/types/database.types'
import { Button } from '../shared/Button'
import { DialogFrame } from '../shared/DialogFrame'
import { ShoppingStoreManager } from '../shopping/ShoppingStoreManager'

const categories = ['Produce', 'Dairy', 'Pantry', 'Meat & Seafood', 'Frozen', 'Household', 'Other']
const units = ['', 'pcs', 'lb', 'oz', 'kg', 'g', 'bag', 'box', 'can', 'bottle']

interface ShoppingListProjectProps {
  projectId: string
  projectName: string
  tasks: Task[]
  onAddTask: (options: AddTaskOptions | string, description?: string) => Promise<void>
  onToggleTask: (id: string, completed: boolean) => Promise<void>
  onUpdateTask: (id: string, options: UpdateTaskOptions | string, description?: string) => Promise<void>
  onDeleteTask: (id: string) => Promise<void>
  onDeleteTasks: (ids: string[]) => Promise<void>
  generalItems: GeneralShoppingItem[]
  generalLoading: boolean
  generalError: string | null
  onAddGeneralItem: (input: GeneralShoppingItemInput) => Promise<boolean>
  onUpdateGeneralItem: (id: string, input: UpdateGeneralShoppingItemInput) => Promise<boolean>
  onToggleGeneralItem: (id: string, completed: boolean) => Promise<boolean>
  onDeleteGeneralItem: (id: string) => Promise<boolean>
  onClearCheckedGeneral: () => Promise<boolean>
  stores: ShoppingStore[]
  storesError: string | null
  onCreateStore: (name: string) => Promise<boolean>
  onRenameStore: (id: string, name: string) => Promise<boolean>
  onDeleteStore: (id: string) => Promise<boolean>
  onMoveStore: (id: string, direction: 'up' | 'down') => Promise<boolean>
  onFinishTrip: (projectId: string, storeId: string) => Promise<number | null>
  tripPending: boolean
  tripError: string | null
  onClearTripError: () => void
  hiddenShoppingCategories: string[] | null
  onHiddenShoppingCategoriesChange: (categories: string[]) => void
}

interface ShoppingDraft {
  title: string
  quantity: string
  unit: string
  category: string
  destination: 'general' | 'unassigned' | `store:${string}`
}

interface GeneralShoppingDraft {
  title: string
  quantity: string
  unit: string
  category: string
}

const emptyDraft: ShoppingDraft = {
  title: '',
  quantity: '',
  unit: '',
  category: 'Produce',
  destination: 'unassigned',
}

function shoppingMetadata(draft: ShoppingDraft): TaskMetadata {
  return {
    content_type: 'shopping',
    quantity: draft.quantity.trim(),
    unit: draft.unit,
    category: draft.category,
  }
}

export function ShoppingListProject({
  projectId,
  projectName,
  tasks,
  onAddTask,
  onToggleTask,
  onUpdateTask,
  onDeleteTask,
  onDeleteTasks,
  generalItems,
  generalLoading,
  generalError,
  onAddGeneralItem,
  onUpdateGeneralItem,
  onToggleGeneralItem,
  onDeleteGeneralItem,
  onClearCheckedGeneral,
  stores,
  storesError,
  onCreateStore,
  onRenameStore,
  onDeleteStore,
  onMoveStore,
  onFinishTrip,
  tripPending,
  tripError,
  onClearTripError,
  hiddenShoppingCategories,
  onHiddenShoppingCategoriesChange,
}: ShoppingListProjectProps) {
  const [draft, setDraft] = useState<ShoppingDraft>(emptyDraft)
  const [query, setQuery] = useState('')
  const [hideChecked, setHideChecked] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<ShoppingDraft>(emptyDraft)
  const [confirmClear, setConfirmClear] = useState(false)
  const [editingGeneralId, setEditingGeneralId] = useState<string | null>(null)
  const [generalEditDraft, setGeneralEditDraft] = useState<GeneralShoppingDraft>({ title: '', quantity: '', unit: '', category: 'Other' })
  const [confirmClearGeneral, setConfirmClearGeneral] = useState(false)
  const [storeManagerOpen, setStoreManagerOpen] = useState(false)
  const [tripStoreId, setTripStoreId] = useState<string | null>(null)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [tripNotice, setTripNotice] = useState<string | null>(null)
  const finishCancelRef = useRef<HTMLButtonElement>(null)

  const tripStore = useMemo(
    () => tripStoreId ? stores.find(store => store.id === tripStoreId) ?? null : null,
    [stores, tripStoreId],
  )
  const tripTasks = useMemo(
    () => tripStoreId ? tasks.filter(task => task.shopping_store_id === tripStoreId) : [],
    [tasks, tripStoreId],
  )
  const tripCheckedCount = tripTasks.filter(task => task.completed).length
  const tripRemainingCount = tripTasks.length - tripCheckedCount
  const generalCheckedCount = generalItems.filter(item => item.completed).length
  const hiddenCategorySet = useMemo(
    () => new Set(hiddenShoppingCategories ?? []),
    [hiddenShoppingCategories],
  )

  const setCategoryVisible = (category: string, visible: boolean) => {
    const nextHiddenCategories = new Set(hiddenShoppingCategories ?? [])
    if (visible) nextHiddenCategories.delete(category)
    else nextHiddenCategories.add(category)
    onHiddenShoppingCategoriesChange([...nextHiddenCategories])
  }

  useEffect(() => {
    setTripStoreId(null)
    setConfirmFinish(false)
    setTripNotice(null)
    onClearTripError()
  }, [onClearTripError, projectId])

  useEffect(() => {
    if (!tripStoreId || tripStore) return
    setTripStoreId(null)
    setConfirmFinish(false)
    setTripNotice('Store is no longer available. Its items are now Unassigned.')
    onClearTripError()
  }, [onClearTripError, tripStore, tripStoreId])

  const visibleTasks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return tasks.filter(task => {
      if (hiddenCategorySet.has(task.metadata.category ?? '')) return false
      if (hideChecked && task.completed) return false
      if (!normalizedQuery) return true
      const category = task.metadata.category ?? ''
      return `${task.title} ${category}`.toLowerCase().includes(normalizedQuery)
    })
  }, [hiddenCategorySet, hideChecked, query, tasks])

  const visibleGeneralItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return generalItems.filter(item => {
      if (hiddenCategorySet.has(item.category)) return false
      if (hideChecked && item.completed) return false
      if (!normalizedQuery) return true
      return `${item.title} ${item.category}`.toLowerCase().includes(normalizedQuery)
    })
  }, [generalItems, hiddenCategorySet, hideChecked, query])

  const groupedTasks = useMemo(() => {
    const groups = new Map<string, Task[]>()
    for (const store of stores) groups.set(store.id, [])
    const unassigned: Task[] = []
    for (const task of visibleTasks) {
      const group = task.shopping_store_id ? groups.get(task.shopping_store_id) : undefined
      if (group) group.push(task)
      else unassigned.push(task)
    }
    return [
      ...stores.map(store => ({ id: store.id, name: store.name, items: groups.get(store.id) ?? [] })).filter(group => group.items.length > 0),
      ...(unassigned.length > 0 ? [{ id: 'unassigned', name: 'Unassigned', items: unassigned }] : []),
    ]
  }, [stores, visibleTasks])

  const checkedIds = tasks.filter(task => task.completed).map(task => task.id)

  const addItem = async () => {
    if (!draft.title.trim()) return
    if (draft.destination === 'general') {
      const added = await onAddGeneralItem({
        title: draft.title,
        quantity: draft.quantity,
        unit: draft.unit,
        category: draft.category,
      })
      if (added) setDraft(previous => ({ ...emptyDraft, category: previous.category, destination: previous.destination }))
      return
    }
    await onAddTask({
      title: draft.title.trim(),
      status: 'TODO',
      priority: 'MEDIUM',
      metadata: shoppingMetadata(draft),
      shopping_store_id: draft.destination === 'unassigned' ? null : draft.destination.slice('store:'.length),
    })
    setDraft(previous => ({ ...emptyDraft, category: previous.category, destination: previous.destination }))
  }

  const startEditing = (task: Task) => {
    setEditingId(task.id)
    setEditDraft({
      title: task.title,
      quantity: task.metadata.quantity ?? '',
      unit: task.metadata.unit ?? '',
      category: task.metadata.category ?? 'Other',
      destination: task.shopping_store_id ? `store:${task.shopping_store_id}` : 'unassigned',
    })
  }

  const saveEdit = async () => {
    if (!editingId || !editDraft.title.trim()) return
    await onUpdateTask(editingId, {
      title: editDraft.title.trim(),
      metadata: shoppingMetadata(editDraft),
      shopping_store_id: editDraft.destination === 'unassigned' ? null : editDraft.destination.slice('store:'.length),
    })
    setEditingId(null)
  }

  const clearChecked = async () => {
    if (checkedIds.length === 0) return
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    await onDeleteTasks(checkedIds)
    setConfirmClear(false)
  }

  const startEditingGeneral = (item: GeneralShoppingItem) => {
    setEditingGeneralId(item.id)
    setGeneralEditDraft({ title: item.title, quantity: item.quantity, unit: item.unit, category: item.category })
  }

  const saveGeneralEdit = async () => {
    if (!editingGeneralId || !generalEditDraft.title.trim()) return
    const updated = await onUpdateGeneralItem(editingGeneralId, generalEditDraft)
    if (updated) setEditingGeneralId(null)
  }

  const clearCheckedGeneral = async () => {
    if (generalCheckedCount === 0) return
    if (!confirmClearGeneral) {
      setConfirmClearGeneral(true)
      return
    }
    if (await onClearCheckedGeneral()) setConfirmClearGeneral(false)
  }

  const startTrip = (storeId: string) => {
    onClearTripError()
    setTripNotice(null)
    setConfirmFinish(false)
    setTripStoreId(storeId)
  }

  const exitTrip = () => {
    setTripStoreId(null)
    setConfirmFinish(false)
    onClearTripError()
  }

  const finishTrip = async () => {
    if (!tripStoreId || !tripStore || tripCheckedCount === 0 || tripPending) return
    const deletedCount = await onFinishTrip(projectId, tripStoreId)
    if (deletedCount === null) return
    setConfirmFinish(false)
    setTripStoreId(null)
  }

  if (tripStoreId && tripStore) {
    return (
      <section className="mx-auto max-w-3xl">
        <Button onClick={exitTrip} disabled={tripPending} tone="amber" variant="tertiary" className="px-3">
          ← Back to {projectName}
        </Button>
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/70 p-5 dark:border-amber-900/60 dark:bg-amber-950/20">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-800 dark:text-amber-300">Shopping trip</p>
          <h3 className="mt-1 text-2xl font-semibold text-stone-950 dark:text-white">{tripStore.name}</h3>
          <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">{tripRemainingCount} remaining · {tripCheckedCount} checked</p>
        </div>

        {tripError && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/70 dark:bg-red-950/20 dark:text-red-200">{tripError}</p>}

        <div className="mt-5 overflow-hidden rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
          {tripTasks.map((task, index) => (
            <div key={task.id} className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? 'border-t border-stone-100 dark:border-stone-800' : ''}`}>
              <input type="checkbox" checked={task.completed} onChange={() => onToggleTask(task.id, !task.completed)} className="size-5 accent-amber-700" aria-label={`Mark ${task.title} ${task.completed ? 'needed' : 'complete'}`} />
              <div className="min-w-0 flex-1"><p className={`font-medium ${task.completed ? 'text-stone-400 line-through' : 'text-stone-900 dark:text-stone-100'}`}>{task.title}</p></div>
              {(task.metadata.quantity || task.metadata.unit) && <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">{[task.metadata.quantity, task.metadata.unit].filter(Boolean).join(' ')}</span>}
            </div>
          ))}
          {tripTasks.length === 0 && <p className="px-4 py-10 text-center text-sm text-stone-500">No items are currently assigned to this store.</p>}
        </div>

        {generalItems.length > 0 && <section className="mt-6">
          <div className="mb-2 flex items-center gap-3">
            <div>
              <h4 className="text-sm font-bold uppercase tracking-[0.13em] text-stone-500 dark:text-stone-400">General</h4>
              <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">Shared across shopping lists</p>
            </div>
            <div className="h-px flex-1 bg-stone-200 dark:bg-stone-800" />
            <span className="text-xs text-stone-400">{generalItems.length}</span>
          </div>
          <div className="overflow-hidden rounded-xl border border-stone-200 bg-stone-50/70 dark:border-stone-800 dark:bg-stone-900/60">
            {generalItems.map((item, index) => (
              <div key={item.id} className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? 'border-t border-stone-200/80 dark:border-stone-800' : ''}`}>
                <input type="checkbox" checked={item.completed} onChange={() => void onToggleGeneralItem(item.id, !item.completed)} className="size-5 accent-amber-700" aria-label={`Mark shared item ${item.title} ${item.completed ? 'needed' : 'complete'}`} />
                <div className="min-w-0 flex-1"><p className={`font-medium ${item.completed ? 'text-stone-400 line-through' : 'text-stone-900 dark:text-stone-100'}`}>{item.title}</p></div>
                {(item.quantity || item.unit) && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">{[item.quantity, item.unit].filter(Boolean).join(' ')}</span>}
              </div>
            ))}
          </div>
        </section>}

        <Button onClick={() => setConfirmFinish(true)} disabled={tripCheckedCount === 0 || tripPending} tone="amber" variant="primary" className="mt-5 w-full py-3">
          {tripPending ? 'Finishing trip…' : `Finish ${tripStore.name} Trip`}
        </Button>

        {confirmFinish && <DialogFrame labelledBy="finish-trip-title" pending={tripPending} onClose={() => setConfirmFinish(false)} initialFocusRef={finishCancelRef} className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900">
            <h3 id="finish-trip-title" className="text-xl font-semibold text-stone-950 dark:text-white">Finish {tripStore.name} trip?</h3>
            <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">{tripCheckedCount} checked {tripCheckedCount === 1 ? 'item' : 'items'} will be removed from this shopping list. {tripRemainingCount} unchecked {tripRemainingCount === 1 ? 'item' : 'items'} will remain for next time.</p>
            <div className="mt-5 flex justify-end gap-3">
              <Button ref={finishCancelRef} onClick={() => setConfirmFinish(false)} disabled={tripPending} variant="secondary">Cancel</Button>
              <Button onClick={() => void finishTrip()} disabled={tripPending} tone="amber" variant="primary">{tripPending ? 'Finishing…' : 'Finish Trip'}</Button>
            </div>
        </DialogFrame>}
      </section>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[21rem_minmax(0,1fr)]">
      <aside className="h-fit rounded-2xl border border-amber-200 bg-amber-50/70 p-5 dark:border-amber-900/60 dark:bg-amber-950/20">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-800 dark:text-amber-300">Quick add</p>
        <h3 className="mt-1 text-xl font-semibold text-stone-950 dark:text-white">What do you need?</h3>

        <div className="mt-4 space-y-3">
          <input
            aria-label="Shopping item"
            value={draft.title}
            onChange={event => setDraft({ ...draft, title: event.target.value })}
            onKeyDown={event => event.key === 'Enter' && addItem()}
            placeholder="Milk, tomatoes, olive oil…"
            className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-600/15 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              aria-label="Quantity"
              value={draft.quantity}
              onChange={event => setDraft({ ...draft, quantity: event.target.value })}
              placeholder="Quantity"
              className="min-w-0 rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
            />
            <select
              aria-label="Unit"
              value={draft.unit}
              onChange={event => setDraft({ ...draft, unit: event.target.value })}
              className="min-w-0 rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
            >
              {units.map(unit => <option key={unit || 'none'} value={unit}>{unit || 'No unit'}</option>)}
            </select>
          </div>
          <select
            aria-label="Category"
            value={draft.category}
            onChange={event => setDraft({ ...draft, category: event.target.value })}
            className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
          >
            {categories.map(category => <option key={category}>{category}</option>)}
          </select>
          <select
            aria-label="Destination"
            value={draft.destination}
            onChange={event => setDraft({ ...draft, destination: event.target.value as ShoppingDraft['destination'] })}
            className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
          >
            <option value="general">General · shared across shopping lists</option>
            <option value="unassigned">Unassigned</option>
            {stores.map(store => <option key={store.id} value={`store:${store.id}`}>{store.name}</option>)}
          </select>
          <Button onClick={() => setStoreManagerOpen(true)} tone="amber" variant="tertiary" className="w-full">Manage stores</Button>
          <Button
            onClick={addItem}
            disabled={!draft.title.trim()}
            tone="amber"
            variant="primary"
            className="w-full py-2.5"
          >
            {draft.destination === 'general' ? 'Add to General' : 'Add to list'}
          </Button>
        </div>

        <div className="mt-5 border-t border-amber-200 pt-4 text-sm text-stone-700 dark:border-amber-900 dark:text-stone-300">
          <div className="flex items-center justify-between">
            <span>Still needed</span>
            <strong>{tasks.length - checkedIds.length}</strong>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>Checked off</span>
            <strong>{checkedIds.length}</strong>
          </div>
        </div>
      </aside>

      <section className="min-w-0">
        {tripNotice && <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-100">{tripNotice}</p>}
        <div className="mb-4 flex flex-col gap-3">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search this list…"
            className="h-10 min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 text-sm outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-600/15 dark:border-stone-700 dark:bg-stone-900 dark:text-white"
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setHideChecked(value => !value)} tone="amber" variant="secondary" className={`flex-1 sm:flex-none ${hideChecked ? 'border-amber-700 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200' : ''}`}>
              {hideChecked ? 'Show checked' : 'Hide checked'}
            </Button>
            <Button onClick={clearChecked} disabled={checkedIds.length === 0} variant="destructive" className="flex-1 sm:flex-none">
              {confirmClear ? 'Confirm clear' : `Clear checked (${checkedIds.length})`}
            </Button>
          </div>
          <fieldset className="rounded-xl border border-stone-200 bg-stone-50/70 p-3 dark:border-stone-800 dark:bg-stone-900/60">
            <div className="flex items-center justify-between gap-3">
              <legend className="text-sm font-semibold text-stone-800 dark:text-stone-100">Categories</legend>
              <Button
                onClick={() => onHiddenShoppingCategoriesChange([])}
                disabled={hiddenCategorySet.size === 0}
                tone="amber"
                variant="tertiary"
                className="min-h-8 px-2 py-1 text-xs"
              >
                Select All
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
              {categories.map(category => (
                <label key={category} className="flex cursor-pointer items-center gap-2 text-sm text-stone-700 dark:text-stone-300">
                  <input
                    type="checkbox"
                    checked={!hiddenCategorySet.has(category)}
                    onChange={event => setCategoryVisible(category, event.target.checked)}
                    className="size-4 accent-amber-700"
                  />
                  {category}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="space-y-6">
          {groupedTasks.map(group => (
            <div key={group.id}>
              <div className="mb-2 flex items-center gap-3">
                <h3 className="text-sm font-bold uppercase tracking-[0.13em] text-stone-500 dark:text-stone-400">{group.name}</h3>
                <div className="h-px flex-1 bg-stone-200 dark:bg-stone-800" />
                <span className="text-xs text-stone-400">{group.items.length}</span>
                {group.id !== 'unassigned' && <Button onClick={() => startTrip(group.id)} tone="amber" variant="tertiary" className="min-h-9 px-2 py-1 text-xs">Start Trip</Button>}
              </div>

              <div className="overflow-hidden rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
                {group.items.map((task, index) => (
                  <div
                    key={task.id}
                    className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? 'border-t border-stone-100 dark:border-stone-800' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={task.completed}
                      onChange={() => onToggleTask(task.id, !task.completed)}
                      className="size-5 accent-amber-700"
                      aria-label={`Mark ${task.title} ${task.completed ? 'needed' : 'complete'}`}
                    />

                    {editingId === task.id ? (
                      <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(8rem,1fr)_6rem_6rem_9rem_9rem_auto]">
                        <input
                          value={editDraft.title}
                          onChange={event => setEditDraft({ ...editDraft, title: event.target.value })}
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white sm:col-span-2 lg:col-span-1"
                        />
                        <input
                          value={editDraft.quantity}
                          onChange={event => setEditDraft({ ...editDraft, quantity: event.target.value })}
                          placeholder="Qty"
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                        />
                        <select
                          value={editDraft.unit}
                          onChange={event => setEditDraft({ ...editDraft, unit: event.target.value })}
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                        >
                          {units.map(unit => <option key={unit || 'none'} value={unit}>{unit || '—'}</option>)}
                        </select>
                        <select
                          value={editDraft.category}
                          onChange={event => setEditDraft({ ...editDraft, category: event.target.value })}
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                        >
                          {categories.map(item => <option key={item}>{item}</option>)}
                        </select>
                        <select
                          value={editDraft.destination}
                          onChange={event => setEditDraft({ ...editDraft, destination: event.target.value as ShoppingDraft['destination'] })}
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                        >
                          <option value="unassigned">Unassigned</option>
                          {stores.map(store => <option key={store.id} value={`store:${store.id}`}>{store.name}</option>)}
                        </select>
                        <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-1">
                          <Button onClick={saveEdit} tone="amber" variant="primary">Save</Button>
                          <Button onClick={() => setEditingId(null)} tone="amber" variant="secondary">Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="min-w-0 flex-1">
                          <p className={`font-medium ${task.completed ? 'text-stone-400 line-through' : 'text-stone-900 dark:text-stone-100'}`}>
                            {task.title}
                          </p>
                        </div>
                        {(task.metadata.quantity || task.metadata.unit) && (
                          <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                            {[task.metadata.quantity, task.metadata.unit].filter(Boolean).join(' ')}
                          </span>
                        )}
                        <Button onClick={() => startEditing(task)} tone="amber" variant="tertiary" className="px-3">Edit</Button>
                        <Button onClick={() => onDeleteTask(task.id)} variant="destructive" className="px-3">Remove</Button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          <section>
            <div className="mb-2 flex items-center gap-3">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-[0.13em] text-stone-500 dark:text-stone-400">General</h3>
                <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">Shared across shopping lists</p>
              </div>
              <div className="h-px flex-1 bg-stone-200 dark:bg-stone-800" />
              <span className="text-xs text-stone-400">{visibleGeneralItems.length}</span>
              <Button onClick={clearCheckedGeneral} disabled={generalCheckedCount === 0} variant="destructive" className="min-h-9 px-2 py-1 text-xs">
                {confirmClearGeneral ? 'Confirm clear General' : `Clear checked General (${generalCheckedCount})`}
              </Button>
            </div>
            {generalError && <p className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/70 dark:bg-red-950/20 dark:text-red-200">{generalError}</p>}
            <div className="overflow-hidden rounded-xl border border-stone-200 bg-stone-50/70 dark:border-stone-800 dark:bg-stone-900/60">
              {generalLoading ? <p className="px-4 py-5 text-sm text-stone-500">Loading shared items…</p> : visibleGeneralItems.map((item, index) => (
                <div key={item.id} className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? 'border-t border-stone-200/80 dark:border-stone-800' : ''}`}>
                  <input
                    type="checkbox"
                    checked={item.completed}
                    onChange={() => void onToggleGeneralItem(item.id, !item.completed)}
                    className="size-5 shrink-0 accent-amber-700"
                    aria-label={`Mark shared item ${item.title} ${item.completed ? 'needed' : 'complete'}`}
                  />
                  {editingGeneralId === item.id ? (
                    <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(8rem,1fr)_6rem_6rem_9rem_auto]">
                      <input value={generalEditDraft.title} onChange={event => setGeneralEditDraft({ ...generalEditDraft, title: event.target.value })} className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white sm:col-span-2 lg:col-span-1" />
                      <input value={generalEditDraft.quantity} onChange={event => setGeneralEditDraft({ ...generalEditDraft, quantity: event.target.value })} placeholder="Qty" className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white" />
                      <select value={generalEditDraft.unit} onChange={event => setGeneralEditDraft({ ...generalEditDraft, unit: event.target.value })} className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white">
                        {units.map(unit => <option key={unit || 'none'} value={unit}>{unit || '—'}</option>)}
                      </select>
                      <select value={generalEditDraft.category} onChange={event => setGeneralEditDraft({ ...generalEditDraft, category: event.target.value })} className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white">
                        {categories.map(category => <option key={category}>{category}</option>)}
                      </select>
                      <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-1">
                        <Button onClick={() => void saveGeneralEdit()} tone="amber" variant="primary">Save</Button>
                        <Button onClick={() => setEditingGeneralId(null)} tone="amber" variant="secondary">Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="min-w-0 flex-1"><p className={`font-medium ${item.completed ? 'text-stone-400 line-through' : 'text-stone-900 dark:text-stone-100'}`}>{item.title}</p></div>
                      {(item.quantity || item.unit) && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">{[item.quantity, item.unit].filter(Boolean).join(' ')}</span>}
                      <Button onClick={() => startEditingGeneral(item)} tone="amber" variant="tertiary" className="px-3">Edit</Button>
                      <Button onClick={() => void onDeleteGeneralItem(item.id)} variant="destructive" className="px-3">Remove</Button>
                    </>
                  )}
                </div>
              ))}
              {!generalLoading && visibleGeneralItems.length === 0 && <p className="px-4 py-5 text-sm text-stone-500">{generalItems.length === 0 ? 'No shared items yet. Choose General in Quick add to create one.' : 'No shared items match this view.'}</p>}
            </div>
          </section>
        </div>

        {visibleTasks.length === 0 && visibleGeneralItems.length === 0 && (
          <div className="rounded-2xl border border-dashed border-stone-300 px-6 py-16 text-center dark:border-stone-700">
            <p className="font-semibold text-stone-800 dark:text-stone-100">
              {tasks.length === 0 ? 'Your shopping list is empty.' : 'Nothing matches this view.'}
            </p>
            <p className="mt-1 text-sm text-stone-500">Add an item and assign a store whenever you are ready.</p>
          </div>
        )}
      </section>
      {storeManagerOpen && <ShoppingStoreManager
        stores={stores}
        error={storesError}
        onCreateStore={onCreateStore}
        onRenameStore={onRenameStore}
        onDeleteStore={onDeleteStore}
        onMoveStore={onMoveStore}
        onClose={() => setStoreManagerOpen(false)}
      />}
    </div>
  )
}
