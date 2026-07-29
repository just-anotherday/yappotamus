import { useCallback, useEffect, useRef, useState } from 'react'
import * as service from '../services/recipeSteps'
import type { RecipeStep, RecipeStepInsert, RecipeStepUpdate } from '../types/recipeBooks'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected recipe-step error occurred.'
}

export function useRecipeSteps(recipeId: string | null) {
  const [steps, setSteps] = useState<RecipeStep[]>([])
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const current = ++request.current
    if (!recipeId) {
      setSteps([])
      return
    }
    setLoading(true)
    try {
      const result = await service.listRecipeSteps(recipeId)
      if (current === request.current) {
        setSteps(result)
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
    steps,
    loading,
    pending,
    error,
    refresh,
    create: (input: RecipeStepInsert) => mutate(() => service.createRecipeStep(input)),
    update: (id: string, input: RecipeStepUpdate) => mutate(
      () => service.updateRecipeStep(id, input),
    ),
    remove: (id: string) => mutate(async () => {
      await service.deleteRecipeStep(id)
      return true
    }),
    reorder: (items: RecipeStep[]) => mutate(async () => {
      await service.reorderRecipeSteps(items)
      return true
    }),
  }
}
