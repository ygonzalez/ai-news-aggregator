import { useState, useEffect, useCallback } from 'react'
import type { LangSmithRun } from '../types'
import { fetchLangSmithRuns } from '../api/client'

interface UseLangSmithRunsResult {
  runs: LangSmithRun[]
  projectName: string | null
  loading: boolean
  error: string | null
  notConfigured: boolean
  refetch: () => void
}

export function useLangSmithRuns(limit = 10): UseLangSmithRunsResult {
  const [runs, setRuns] = useState<LangSmithRun[]>([])
  const [projectName, setProjectName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notConfigured, setNotConfigured] = useState(false)

  const loadRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConfigured(false)
    try {
      const response = await fetchLangSmithRuns(limit)
      setRuns(response.runs)
      setProjectName(response.project_name)
    } catch (err) {
      if (err instanceof Error && err.message.includes('503')) {
        setNotConfigured(true)
      } else {
        setError(err instanceof Error ? err.message : 'Failed to fetch LangSmith runs')
      }
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  return { runs, projectName, loading, error, notConfigured, refetch: loadRuns }
}
