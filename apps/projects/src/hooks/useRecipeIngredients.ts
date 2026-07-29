import { useCallback, useEffect, useRef, useState } from 'react'
import * as service from '../services/recipeIngredients'
import type {
  RecipeIngredient,
  RecipeIngredientInsert,
  RecipeIngredientUpdate,
} from '../types/recipeBooks'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected ingredient error occurred.'
}

export function useRecipeIngredients(recipeId: string | null) {
  const [ingredients, setIngredients] = useState<RecipeIngredient[]>([])
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const current = ++request.current
    if (!recipeId) {
      setIngredients([])
      return
    }
    setLoading(true)
    try {
      const result = await service.listRecipeIngredients(recipeId)
      if (current === request.current) {
        setIngredients(result)
        setError(null)
      }
    } catch (caught) {
      if (current === request.current) setError(message(caught))
    } finally {
      if (current === request.current) setLoading(false)
    }
  }, [recipeId])

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
      await refresh()
      setError(message(caught))
      return null
    } finally {
      setPending(false)
    }
  }, [pending, refresh])

  return {
    ingredients,
    loading,
    pending,
    error,
    refresh,
    create: (input: RecipeIngredientInsert) => mutate(
      () => service.createRecipeIngredient(input),
    ),
    update: (id: string, input: RecipeIngredientUpdate) => mutate(
      () => service.updateRecipeIngredient(id, input),
    ),
    remove: (id: string) => mutate(async () => {
      await service.deleteRecipeIngredient(id)
      return true
    }),
    reorder: (items: RecipeIngredient[]) => mutate(async () => {
      await service.reorderRecipeIngredients(items)
      return true
    }),
  }
}
