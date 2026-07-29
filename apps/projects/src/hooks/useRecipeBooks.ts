import { useCallback, useEffect, useRef, useState } from 'react'
import * as recipeBookService from '../services/recipeBooks'
import type { RecipeBook, RecipeBookUpdate } from '../types/recipeBooks'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected Recipe Book error occurred.'
}

export function useRecipeBooks(userId: string, includeArchived: boolean) {
  const [data, setData] = useState<RecipeBook[]>([])
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const current = ++request.current
    setLoading(true)
    try {
      const books = await recipeBookService.listRecipeBooks(includeArchived)
      if (current === request.current) {
        setData(books)
        setError(null)
      }
    } catch (caught) {
      if (current === request.current) setError(message(caught))
    } finally {
      if (current === request.current) setLoading(false)
    }
  }, [includeArchived])

  useEffect(() => {
    void refresh()
    return () => { request.current += 1 }
  }, [refresh])

  const mutate = useCallback(async <T,>(operation: () => Promise<T>): Promise<T | null> => {
    if (pending) return null
    setPending(true)
    setError(null)
    try {
      const result = await operation()
      await refresh()
      return result
    } catch (caught) {
      setError(message(caught))
      return null
    } finally {
      setPending(false)
    }
  }, [pending, refresh])

  return {
    books: data,
    loading,
    pending,
    error,
    clearError: () => setError(null),
    refresh,
    create: (name: string, description: string, coverLabel: string | null) => mutate(
      () => recipeBookService.createRecipeBook({
        user_id: userId,
        name,
        description,
        cover_label: coverLabel,
      }),
    ),
    update: (id: string, updates: RecipeBookUpdate) => mutate(
      () => recipeBookService.updateRecipeBook(id, updates),
    ),
    setArchived: (id: string, value: boolean) => mutate(
      () => recipeBookService.setRecipeBookArchived(id, value),
    ),
    remove: (id: string) => mutate(async () => {
      await recipeBookService.deleteRecipeBook(id)
      return true
    }),
  }
}
