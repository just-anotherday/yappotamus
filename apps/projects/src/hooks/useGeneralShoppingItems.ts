import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { GeneralShoppingItem } from '../lib/types/database.types'

export interface GeneralShoppingItemInput {
  title: string
  quantity: string
  unit: string
  category: string
}

export interface UpdateGeneralShoppingItemInput extends Partial<GeneralShoppingItemInput> {
  completed?: boolean
  sort_order?: number
}

export function useGeneralShoppingItems() {
  const [items, setItems] = useState<GeneralShoppingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchItems = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      setItems([])
      setLoading(false)
      return
    }

    const { data, error: fetchError } = await supabase
      .from('general_shopping_items')
      .select('*')
      .eq('user_id', user.id)
      .order('sort_order', { ascending: true })
      .order('created_at', { ascending: true })
      .order('id', { ascending: true })

    if (fetchError) setError(fetchError.message)
    else {
      setItems(data ?? [])
      setError(null)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void fetchItems()
    const channel = supabase
      .channel('general-shopping-items')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'general_shopping_items' }, fetchItems)
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [fetchItems])

  const addItem = useCallback(async (input: GeneralShoppingItemInput) => {
    const title = input.title.trim()
    if (!title) {
      setError('Enter a shopping item.')
      return false
    }
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return false

    const nextSortOrder = items.length === 0 ? 0 : Math.max(...items.map(item => item.sort_order)) + 1
    const { error: insertError } = await supabase
      .from('general_shopping_items')
      .insert({
        user_id: user.id,
        title,
        quantity: input.quantity.trim(),
        unit: input.unit,
        category: input.category,
        sort_order: nextSortOrder,
      })
    if (insertError) {
      setError(insertError.message)
      return false
    }
    await fetchItems()
    return true
  }, [fetchItems, items])

  const updateItem = useCallback(async (id: string, input: UpdateGeneralShoppingItemInput) => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return false
    const updates: Record<string, unknown> = {}
    if (input.title !== undefined) {
      const title = input.title.trim()
      if (!title) {
        setError('Enter a shopping item.')
        return false
      }
      updates.title = title
    }
    if (input.quantity !== undefined) updates.quantity = input.quantity.trim()
    if (input.unit !== undefined) updates.unit = input.unit
    if (input.category !== undefined) updates.category = input.category
    if (input.completed !== undefined) updates.completed = input.completed
    if (input.sort_order !== undefined) updates.sort_order = input.sort_order
    if (Object.keys(updates).length === 0) return true

    setItems(previous => previous.map(item => item.id === id ? { ...item, ...updates } as GeneralShoppingItem : item))
    const { error: updateError } = await supabase
      .from('general_shopping_items')
      .update(updates)
      .eq('id', id)
      .eq('user_id', user.id)
    if (updateError) {
      setError(updateError.message)
      await fetchItems()
      return false
    }
    await fetchItems()
    return true
  }, [fetchItems])

  const toggleItem = useCallback((id: string, completed: boolean) => (
    updateItem(id, { completed })
  ), [updateItem])

  const deleteItem = useCallback(async (id: string) => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return false
    setItems(previous => previous.filter(item => item.id !== id))
    const { error: deleteError } = await supabase
      .from('general_shopping_items')
      .delete()
      .eq('id', id)
      .eq('user_id', user.id)
    if (deleteError) {
      setError(deleteError.message)
      await fetchItems()
      return false
    }
    await fetchItems()
    return true
  }, [fetchItems])

  const clearChecked = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return false
    setItems(previous => previous.filter(item => !item.completed))
    const { error: deleteError } = await supabase
      .from('general_shopping_items')
      .delete()
      .eq('user_id', user.id)
      .eq('completed', true)
    if (deleteError) {
      setError(deleteError.message)
      await fetchItems()
      return false
    }
    await fetchItems()
    return true
  }, [fetchItems])

  return { items, loading, error, addItem, updateItem, toggleItem, deleteItem, clearChecked }
}
