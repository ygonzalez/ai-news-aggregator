import { useState, useEffect } from 'react'
import { fetchGraph } from '../api/client'

interface UseGraphResult {
  mermaid: string | null
  nodes: string[]
  loading: boolean
  error: string | null
}

export function useGraph(): UseGraphResult {
  const [mermaid, setMermaid] = useState<string | null>(null)
  const [nodes, setNodes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadGraph() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchGraph()
        setMermaid(response.mermaid)
        setNodes(response.nodes)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch graph')
      } finally {
        setLoading(false)
      }
    }

    loadGraph()
  }, [])

  return { mermaid, nodes, loading, error }
}
