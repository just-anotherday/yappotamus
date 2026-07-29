import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchRecipe } from '../services/recipes'
import type { Recipe } from '../types/recipeBooks'

export function useRecipe(recipeId: string | null) {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const current = ++request.current
    if (!recipeId) {
      setRecipe(null)
      return
    }
    setLoading(true)
    try {
      const result = await fetchRecipe(recipeId)
      if (current === request.current) {
        setRecipe(result)
        setError(null)
      }
    } catch (caught) {
      if (current === request.current) {
        setError(caught instanceof Error ? caught.message : 'Could not load the recipe.')
      }
    } finally {
      if (current === request.current) setLoading(false)
    }
  }, [recipeId])

  useEffect(() => {
    void refresh()
    return () => { request.current += 1 }
  }, [refresh])

  return { recipe, loading, error, refresh }
}
