import { useGraph } from '../hooks/useGraph'
import { GraphViewer } from '../components/GraphViewer'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function Graph() {
  const { mermaid, nodes, loading, error } = useGraph()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pipeline Graph</h1>
        <p className="text-gray-500 mt-1">Visualization of the LangGraph pipeline structure</p>
      </div>

      {loading ? (
        <LoadingSpinner />
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800 text-sm">
          {error}
        </div>
      ) : (
        <>
          {/* Node List */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Pipeline Nodes</h2>
            <div className="flex flex-wrap gap-2">
              {nodes.map((node) => (
                <span
                  key={node}
                  className="px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-sm font-medium"
                >
                  {node}
                </span>
              ))}
            </div>
          </div>

          {/* Graph Diagram */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Flow Diagram</h2>
            {mermaid ? (
              <GraphViewer diagram={mermaid} />
            ) : (
              <div className="bg-gray-50 rounded-lg border border-gray-200 p-8 text-center text-gray-500">
                No graph data available
              </div>
            )}
          </div>

          {/* Raw Mermaid */}
          <details className="bg-gray-50 rounded-lg border border-gray-200">
            <summary className="px-4 py-3 cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900">
              View Raw Mermaid Code
            </summary>
            <pre className="px-4 pb-4 text-xs text-gray-600 overflow-auto">
              {mermaid}
            </pre>
          </details>
        </>
      )}
    </div>
  )
}
