import type { LangSmithRun } from '../types'
import { StatusBadge } from './StatusBadge'
import { LoadingSpinner } from './LoadingSpinner'

interface LangSmithRunsListProps {
  runs: LangSmithRun[]
  loading: boolean
  notConfigured?: boolean
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString()
}

function formatTokens(tokens: number | null): string {
  if (tokens === null) return '-'
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return tokens.toString()
}

function formatCost(cost: number | null): string {
  if (cost === null) return '-'
  return `$${cost.toFixed(4)}`
}

export function LangSmithRunsList({ runs, loading, notConfigured }: LangSmithRunsListProps) {
  if (loading) return <LoadingSpinner />

  if (notConfigured) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-800 text-sm">
        LangSmith is not configured. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in your environment.
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        No LangSmith runs found
      </div>
    )
  }

  return (
    <div className="grid gap-4">
      {runs.map((run) => (
        <div
          key={run.id}
          className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-shadow"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h4 className="font-medium text-gray-900 truncate">{run.name}</h4>
              <p className="text-xs text-gray-500 font-mono mt-1">{run.id}</p>
            </div>
            <StatusBadge status={run.status} />
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-3 text-sm text-gray-600">
            <span>Started: {formatDate(run.start_time)}</span>
            <span>Duration: {formatDuration(run.duration_ms)}</span>
          </div>

          {/* Token and Cost Info */}
          {(run.total_tokens !== null || run.total_cost !== null) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3 text-sm">
              {run.total_tokens !== null && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">Tokens:</span>
                  <span className="font-medium text-gray-900">{formatTokens(run.total_tokens)}</span>
                  {run.prompt_tokens !== null && run.completion_tokens !== null && (
                    <span className="text-gray-400 text-xs">
                      ({formatTokens(run.prompt_tokens)} in / {formatTokens(run.completion_tokens)} out)
                    </span>
                  )}
                </div>
              )}
              {run.total_cost !== null && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">Cost:</span>
                  <span className="font-medium text-emerald-700">{formatCost(run.total_cost)}</span>
                </div>
              )}
            </div>
          )}

          {run.error && (
            <p className="mt-2 text-sm text-red-600 bg-red-50 rounded p-2">
              {run.error}
            </p>
          )}
          <div className="mt-3">
            <a
              href={run.langsmith_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
            >
              View in LangSmith
            </a>
          </div>
        </div>
      ))}
    </div>
  )
}
