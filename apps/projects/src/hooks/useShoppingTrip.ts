import { useCallback, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'

export function useShoppingTrip() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submittingRef = useRef(false)

  const finishTrip = useCallback(async (projectId: string, storeId: string) => {
    if (submittingRef.current) return null

    submittingRef.current = true
    setPending(true)
    setError(null)
    try {
      const { data, error: rpcError } = await supabase.rpc('finish_shopping_trip', {
        p_project_id: projectId,
        p_store_id: storeId,
      })
      if (rpcError) {
        setError(`Unable to finish this shopping trip. ${rpcError.message}`)
        return null
      }
      if (typeof data !== 'number') {
        setError('Unable to finish this shopping trip. The server returned an invalid result.')
        return null
      }
      return data
    } catch {
      setError('Unable to finish this shopping trip. Please check your connection and try again.')
      return null
    } finally {
      submittingRef.current = false
      setPending(false)
    }
  }, [])

  const clearError = useCallback(() => setError(null), [])

  return { finishTrip, pending, error, clearError }
}
