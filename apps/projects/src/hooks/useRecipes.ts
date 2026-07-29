import { useCallback, useEffect, useRef, useState } from 'react'
import * as recipeService from '../services/recipes'
import type { Recipe, RecipeInsert, RecipeUpdate } from '../types/recipeBooks'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected recipe error occurred.'
}

export function useRecipes(recipeBookId: string | null, includeArchived: boolean) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const current = ++request.current
    if (!recipeBookId) {
      setRecipes([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const result = await recipeService.listRecipes(recipeBookId, includeArchived)
      if (current === request.current) {
        setRecipes(result)
        setError(null)
      }
    } catch (caught) {
      if (current === request.current) setError(message(caught))
    } finally {
      if (current === request.current) setLoading(false)
    }
  }, [includeArchived, recipeBookId])

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
    recipes,
    loading,
    pending,
    error,
    clearError: () => setError(null),
    refresh,
    create: (input: RecipeInsert) => mutate(() => recipeService.createRecipe(input)),
    update: (id: string, input: RecipeUpdate) => mutate(
      () => recipeService.updateRecipe(id, input),
    ),
    setArchived: (id: string, value: boolean) => mutate(
      () => recipeService.setRecipeArchived(id, value),
    ),
    setFavorite: (id: string, value: boolean) => mutate(
      () => recipeService.setRecipeFavorite(id, value),
    ),
    remove: (id: string) => mutate(async () => {
      await recipeService.deleteRecipe(id)
      return true
    }),
  }
}
