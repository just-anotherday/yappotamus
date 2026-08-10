import { useRef, useState } from 'react'
import type { ShoppingStore } from '../../lib/types/database.types'
import { Button } from '../shared/Button'
import { DialogFrame } from '../shared/DialogFrame'
import { IconButton } from '../shared/IconButton'

interface ShoppingStoreManagerProps {
  stores: ShoppingStore[]
  error: string | null
  onCreateStore: (name: string) => Promise<boolean>
  onRenameStore: (id: string, name: string) => Promise<boolean>
  onDeleteStore: (id: string) => Promise<boolean>
  onMoveStore: (id: string, direction: 'up' | 'down') => Promise<boolean>
  onClose: () => void
}

export function ShoppingStoreManager({
  stores,
  error,
  onCreateStore,
  onRenameStore,
  onDeleteStore,
  onMoveStore,
  onClose,
}: ShoppingStoreManagerProps) {
  const [newStoreName, setNewStoreName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const newStoreInputRef = useRef<HTMLInputElement>(null)

  const createStore = async () => {
    if (await onCreateStore(newStoreName)) setNewStoreName('')
  }

  const saveRename = async () => {
    if (!editingId) return
    if (await onRenameStore(editingId, editingName)) {
      setEditingId(null)
      setEditingName('')
    }
  }

  return (
    <DialogFrame labelledBy="store-manager-title" onClose={onClose} initialFocusRef={newStoreInputRef} className="my-6 w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-300">Shopping setup</p>
            <h3 id="store-manager-title" className="mt-1 text-xl font-semibold text-stone-950 dark:text-white">Manage stores</h3>
            <p className="mt-1 text-sm text-stone-500">Stores are available across all of your shopping lists.</p>
          </div>
          <Button onClick={onClose} variant="tertiary" className="px-3">Close</Button>
        </div>

        <div className="mt-5 flex gap-2">
          <input
            ref={newStoreInputRef}
            aria-label="New store name"
            value={newStoreName}
            onChange={event => setNewStoreName(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && void createStore()}
            placeholder="Add a store"
            className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
          />
          <Button onClick={() => void createStore()} disabled={!newStoreName.trim()} tone="amber" variant="primary">Add</Button>
        </div>
        {error && <p className="mt-2 text-sm text-red-700 dark:text-red-300">{error}</p>}

        <div className="mt-5 overflow-hidden rounded-xl border border-stone-200 dark:border-stone-800">
          {stores.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-stone-500">Add stores when you are ready. Unassigned items will still work.</p>
          ) : stores.map((store, index) => (
            <div key={store.id} className={`flex items-center gap-2 px-3 py-3 ${index > 0 ? 'border-t border-stone-100 dark:border-stone-800' : ''}`}>
              {editingId === store.id ? (
                <>
                  <input value={editingName} onChange={event => setEditingName(event.target.value)} className="min-w-0 flex-1 rounded border border-stone-300 px-2 py-1.5 dark:border-stone-700 dark:bg-stone-950 dark:text-white" autoFocus />
                  <Button onClick={() => void saveRename()} variant="tertiary" className="min-h-8 px-2 py-1 text-xs">Save</Button>
                  <Button onClick={() => setEditingId(null)} variant="tertiary" className="min-h-8 px-2 py-1 text-xs">Cancel</Button>
                </>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate font-medium text-stone-900 dark:text-stone-100">{store.name}</span>
                  <IconButton ariaLabel={`Move ${store.name} up`} onClick={() => void onMoveStore(store.id, 'up')} disabled={index === 0} tone="amber" className="size-9 min-h-9 text-base">↑</IconButton>
                  <IconButton ariaLabel={`Move ${store.name} down`} onClick={() => void onMoveStore(store.id, 'down')} disabled={index === stores.length - 1} tone="amber" className="size-9 min-h-9 text-base">↓</IconButton>
                  <Button aria-label={`Rename ${store.name}`} onClick={() => { setEditingId(store.id); setEditingName(store.name) }} tone="amber" variant="tertiary" className="min-h-9 px-2 py-1 text-xs">Rename</Button>
                  <Button aria-label={`Delete ${store.name}`} onClick={() => setDeleteId(store.id)} variant="destructive" className="min-h-9 px-2 py-1 text-xs">Delete</Button>
                </>
              )}
            </div>
          ))}
        </div>

        {deleteId && (() => {
          const store = stores.find(item => item.id === deleteId)
          return store ? (
            <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-900/70 dark:bg-red-950/20">
              <p className="font-semibold text-red-900 dark:text-red-100">Delete {store.name}?</p>
              <p className="mt-1 text-sm text-red-800 dark:text-red-200">Items assigned to this store will become Unassigned. No grocery items will be deleted.</p>
              <div className="mt-3 flex justify-end gap-2">
                <Button onClick={() => setDeleteId(null)} variant="secondary">Cancel</Button>
                <Button onClick={() => void onDeleteStore(store.id).then(deleted => { if (deleted) setDeleteId(null) })} variant="destructive" className="bg-red-700 text-white hover:bg-red-800 hover:text-white dark:bg-red-800 dark:text-white dark:hover:bg-red-700">Delete store</Button>
              </div>
            </div>
          ) : null
        })()}
    </DialogFrame>
  )
}
