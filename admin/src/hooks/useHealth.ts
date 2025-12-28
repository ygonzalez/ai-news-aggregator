import { useState, useEffect, useCallback } from 'react'
import type { HealthResponse } from '../types'
import { fetchHealth } from '../api/client'

interface UseHealthResult {
  health: HealthResponse | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useHealth(): UseHealthResult {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadHealth = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchHealth()
      setHealth(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch health')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHealth()
  }, [loadHealth])

  return { health, loading, error, refetch: loadHealth }
}
