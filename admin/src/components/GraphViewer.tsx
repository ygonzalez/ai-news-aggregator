import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

interface GraphViewerProps {
  diagram: string
}

export function GraphViewer({ diagram }: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis',
      },
    })
  }, [])

  useEffect(() => {
    if (!containerRef.current || !diagram) return

    const renderDiagram = async () => {
      try {
        // Clear previous content
        containerRef.current!.innerHTML = ''

        // Generate unique ID for this render
        const id = `mermaid-${Date.now()}`

        const { svg } = await mermaid.render(id, diagram)
        if (containerRef.current) {
          containerRef.current.innerHTML = svg
        }
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to render diagram')
      }
    }

    renderDiagram()
  }, [diagram])

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800 text-sm">Failed to render diagram: {error}</p>
        <pre className="mt-2 text-xs text-gray-600 overflow-auto bg-gray-100 p-2 rounded">
          {diagram}
        </pre>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="bg-white rounded-lg border border-gray-200 p-6 overflow-auto"
    />
  )
}
