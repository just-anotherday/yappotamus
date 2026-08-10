import { useState } from 'react'
import type { ShoppingStore } from '../../lib/types/database.types'

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
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-stone-950/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="store-manager-title">
      <div className="my-6 w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl dark:border-stone-700 dark:bg-stone-900 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-300">Shopping setup</p>
            <h3 id="store-manager-title" className="mt-1 text-xl font-semibold text-stone-950 dark:text-white">Manage stores</h3>
            <p className="mt-1 text-sm text-stone-500">Stores are available across all of your shopping lists.</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm font-semibold text-stone-500 hover:text-stone-900 dark:hover:text-white">Close</button>
        </div>

        <div className="mt-5 flex gap-2">
          <input
            value={newStoreName}
            onChange={event => setNewStoreName(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && void createStore()}
            placeholder="Add a store"
            className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-950 dark:text-white"
          />
          <button type="button" onClick={() => void createStore()} disabled={!newStoreName.trim()} className="rounded-lg bg-amber-700 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">Add</button>
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
                  <button type="button" onClick={() => void saveRename()} className="text-xs font-semibold text-emerald-700">Save</button>
                  <button type="button" onClick={() => setEditingId(null)} className="text-xs font-semibold text-stone-500">Cancel</button>
                </>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate font-medium text-stone-900 dark:text-stone-100">{store.name}</span>
                  <button type="button" onClick={() => void onMoveStore(store.id, 'up')} disabled={index === 0} className="rounded px-1 text-sm text-stone-500 disabled:opacity-30" aria-label={`Move ${store.name} up`}>↑</button>
                  <button type="button" onClick={() => void onMoveStore(store.id, 'down')} disabled={index === stores.length - 1} className="rounded px-1 text-sm text-stone-500 disabled:opacity-30" aria-label={`Move ${store.name} down`}>↓</button>
                  <button type="button" onClick={() => { setEditingId(store.id); setEditingName(store.name) }} className="text-xs font-semibold text-stone-500 hover:text-amber-700">Rename</button>
                  <button type="button" onClick={() => setDeleteId(store.id)} className="text-xs font-semibold text-stone-400 hover:text-red-700">Delete</button>
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
                <button type="button" onClick={() => setDeleteId(null)} className="text-sm font-semibold text-stone-600 dark:text-stone-300">Cancel</button>
                <button type="button" onClick={() => void onDeleteStore(store.id).then(deleted => { if (deleted) setDeleteId(null) })} className="rounded bg-red-700 px-3 py-2 text-sm font-semibold text-white">Delete store</button>
              </div>
            </div>
          ) : null
        })()}
      </div>
    </div>
  )
}
