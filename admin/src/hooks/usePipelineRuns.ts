import { useState, useEffect, useCallback } from 'react'
import type { PipelineRun } from '../types'
import { fetchPipelineRuns } from '../api/client'

interface UsePipelineRunsResult {
  runs: PipelineRun[]
  loading: boolean
  error: string | null
  refetch: () => void
}

export function usePipelineRuns(limit = 20): UsePipelineRunsResult {
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchPipelineRuns(limit)
      setRuns(response.runs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pipeline runs')
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  return { runs, loading, error, refetch: loadRuns }
}
