import { useEffect, useMemo, useRef, useState } from 'react'
import type { AddTaskOptions, UpdateTaskOptions } from '../../hooks/useTasks'
import type { ShoppingStore, Task, TaskMetadata } from '../../lib/types/database.types'
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
}

interface ShoppingDraft {
  title: string
  quantity: string
  unit: string
  category: string
  shopping_store_id: string | null
}

const emptyDraft: ShoppingDraft = {
  title: '',
  quantity: '',
  unit: '',
  category: 'Produce',
  shopping_store_id: null,
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
}: ShoppingListProjectProps) {
  const [draft, setDraft] = useState<ShoppingDraft>(emptyDraft)
  const [query, setQuery] = useState('')
  const [hideChecked, setHideChecked] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<ShoppingDraft>(emptyDraft)
  const [confirmClear, setConfirmClear] = useState(false)
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
      if (hideChecked && task.completed) return false
      if (!normalizedQuery) return true
      const category = task.metadata.category ?? ''
      return `${task.title} ${category}`.toLowerCase().includes(normalizedQuery)
    })
  }, [hideChecked, query, tasks])

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
    await onAddTask({
      title: draft.title.trim(),
      status: 'TODO',
      priority: 'MEDIUM',
      metadata: shoppingMetadata(draft),
      shopping_store_id: draft.shopping_store_id,
    })
    setDraft(previous => ({ ...emptyDraft, category: previous.category }))
  }

  const startEditing = (task: Task) => {
    setEditingId(task.id)
    setEditDraft({
      title: task.title,
      quantity: task.metadata.quantity ?? '',
      unit: task.metadata.unit ?? '',
      category: task.metadata.category ?? 'Other',
      shopping_store_id: task.shopping_store_id,
    })
  }

  const saveEdit = async () => {
    if (!editingId || !editDraft.title.trim()) return
    await onUpdateTask(editingId, {
      title: editDraft.title.trim(),
      metadata: shoppingMetadata(editDraft),
      shopping_store_id: editDraft.shopping_store_id,
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
            aria-label="Store"
            value={draft.shopping_store_id ?? ''}
            onChange={event => setDraft({ ...draft, shopping_store_id: event.target.value || null })}
            className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2.5 outline-none focus:border-amber-600 dark:border-amber-900 dark:bg-stone-950 dark:text-white"
          >
            <option value="">Unassigned</option>
            {stores.map(store => <option key={store.id} value={store.id}>{store.name}</option>)}
          </select>
          <Button onClick={() => setStoreManagerOpen(true)} tone="amber" variant="tertiary" className="w-full">Manage stores</Button>
          <Button
            onClick={addItem}
            disabled={!draft.title.trim()}
            tone="amber"
            variant="primary"
            className="w-full py-2.5"
          >
            Add to list
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
                          value={editDraft.shopping_store_id ?? ''}
                          onChange={event => setEditDraft({ ...editDraft, shopping_store_id: event.target.value || null })}
                          className="min-w-0 rounded border border-stone-300 px-2 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
                        >
                          <option value="">Unassigned</option>
                          {stores.map(store => <option key={store.id} value={store.id}>{store.name}</option>)}
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
        </div>

        {visibleTasks.length === 0 && (
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
