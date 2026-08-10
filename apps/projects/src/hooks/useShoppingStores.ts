import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { ShoppingStore } from '../lib/types/database.types'

function normalizeStoreName(name: string) {
  return name.trim()
}

export function useShoppingStores() {
  const [stores, setStores] = useState<ShoppingStore[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStores = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      setStores([])
      setLoading(false)
      return
    }

    const { data, error: fetchError } = await supabase
      .from('shopping_stores')
      .select('*')
      .eq('user_id', user.id)
      .order('sort_order', { ascending: true })
      .order('name', { ascending: true })
      .order('id', { ascending: true })

    if (fetchError) setError(fetchError.message)
    else {
      setStores(data ?? [])
      setError(null)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void fetchStores()
    const channel = supabase
      .channel('shopping-stores')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'shopping_stores' }, fetchStores)
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [fetchStores])

  const createStore = useCallback(async (name: string) => {
    const normalizedName = normalizeStoreName(name)
    if (!normalizedName) {
      setError('Enter a store name.')
      return false
    }
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return false
    const nextSortOrder = stores.length === 0 ? 0 : Math.max(...stores.map(store => store.sort_order)) + 1
    const { error: insertError } = await supabase
      .from('shopping_stores')
      .insert({ user_id: user.id, name: normalizedName, sort_order: nextSortOrder })
    if (insertError) {
      setError(insertError.code === '23505' ? 'You already have a store with that name.' : insertError.message)
      return false
    }
    await fetchStores()
    return true
  }, [fetchStores, stores])

  const renameStore = useCallback(async (id: string, name: string) => {
    const normalizedName = normalizeStoreName(name)
    if (!normalizedName) {
      setError('Enter a store name.')
      return false
    }
    const { error: updateError } = await supabase.from('shopping_stores').update({ name: normalizedName }).eq('id', id)
    if (updateError) {
      setError(updateError.code === '23505' ? 'You already have a store with that name.' : updateError.message)
      return false
    }
    await fetchStores()
    return true
  }, [fetchStores])

  const deleteStore = useCallback(async (id: string) => {
    const { error: deleteError } = await supabase.from('shopping_stores').delete().eq('id', id)
    if (deleteError) {
      setError(deleteError.message)
      return false
    }
    await fetchStores()
    return true
  }, [fetchStores])

  const moveStore = useCallback(async (id: string, direction: 'up' | 'down') => {
    const currentIndex = stores.findIndex(store => store.id === id)
    const targetIndex = currentIndex + (direction === 'up' ? -1 : 1)
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= stores.length) return false
    const current = stores[currentIndex]
    const target = stores[targetIndex]
    const updates = await Promise.all([
      supabase.from('shopping_stores').update({ sort_order: target.sort_order }).eq('id', current.id),
      supabase.from('shopping_stores').update({ sort_order: current.sort_order }).eq('id', target.id),
    ])
    const updateError = updates.find(result => result.error)?.error
    if (updateError) {
      setError(updateError.message)
      return false
    }
    await fetchStores()
    return true
  }, [fetchStores, stores])

  return { stores, loading, error, createStore, renameStore, deleteStore, moveStore }
}
