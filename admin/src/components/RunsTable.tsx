import type { PipelineRun } from '../types'
import { StatusBadge } from './StatusBadge'
import { LoadingSpinner } from './LoadingSpinner'

interface RunsTableProps {
  runs: PipelineRun[]
  loading: boolean
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '-'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString()
}

export function RunsTable({ runs, loading }: RunsTableProps) {
  if (loading) return <LoadingSpinner />

  if (runs.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        No pipeline runs found
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-gray-700">Run ID</th>
            <th className="text-left px-4 py-3 font-medium text-gray-700">Status</th>
            <th className="text-left px-4 py-3 font-medium text-gray-700">Started</th>
            <th className="text-left px-4 py-3 font-medium text-gray-700">Duration</th>
            <th className="text-right px-4 py-3 font-medium text-gray-700">Collected</th>
            <th className="text-right px-4 py-3 font-medium text-gray-700">Processed</th>
            <th className="text-right px-4 py-3 font-medium text-gray-700">Persisted</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {runs.map((run) => (
            <tr key={run.run_id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-mono text-xs text-gray-600">
                {run.run_id}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-4 py-3 text-gray-600">
                {run.started_at ? formatDate(run.started_at) : '-'}
              </td>
              <td className="px-4 py-3 text-gray-600">
                {formatDuration(run.duration_seconds)}
              </td>
              <td className="px-4 py-3 text-right text-gray-900">
                {run.items_collected}
              </td>
              <td className="px-4 py-3 text-right text-gray-900">
                {run.items_processed}
              </td>
              <td className="px-4 py-3 text-right text-gray-900 font-medium">
                {run.items_persisted}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
