import { usePipelineRuns } from '../hooks/usePipelineRuns'
import { useHealth } from '../hooks/useHealth'
import { TriggerButton } from '../components/TriggerButton'
import { StatusBadge } from '../components/StatusBadge'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function Dashboard() {
  const { runs, loading: runsLoading, refetch } = usePipelineRuns(5)
  const { health, loading: healthLoading } = useHealth()

  const lastRun = runs[0]

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500 mt-1">Monitor and manage the AI News Aggregator pipeline</p>
        </div>
        <TriggerButton onComplete={refetch} />
      </div>

      {/* Health Status */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">System Health</h2>
        {healthLoading ? (
          <LoadingSpinner />
        ) : health ? (
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-sm text-gray-500">Overall Status</p>
              <StatusBadge status={health.status} />
            </div>
            <div>
              <p className="text-sm text-gray-500">Database</p>
              <StatusBadge status={health.database ? 'connected' : 'disconnected'} />
            </div>
            <div>
              <p className="text-sm text-gray-500">pgvector</p>
              <StatusBadge status={health.pgvector ? 'enabled' : 'disabled'} />
            </div>
          </div>
        ) : (
          <p className="text-red-600">Failed to fetch health status</p>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-6">
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <p className="text-sm text-gray-500">Last Run Status</p>
          {runsLoading ? (
            <div className="mt-2"><LoadingSpinner /></div>
          ) : lastRun ? (
            <div className="mt-2">
              <StatusBadge status={lastRun.status} />
            </div>
          ) : (
            <p className="mt-2 text-gray-400">No runs yet</p>
          )}
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <p className="text-sm text-gray-500">Items Persisted</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">
            {runsLoading ? '-' : (lastRun?.items_persisted ?? 0)}
          </p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <p className="text-sm text-gray-500">Items Collected</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">
            {runsLoading ? '-' : (lastRun?.items_collected ?? 0)}
          </p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <p className="text-sm text-gray-500">Total Runs</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">
            {runsLoading ? '-' : runs.length}
          </p>
        </div>
      </div>

      {/* Recent Runs Preview */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Runs</h2>
          <a href="/runs" className="text-sm text-blue-600 hover:text-blue-800">
            View all
          </a>
        </div>
        {runsLoading ? (
          <LoadingSpinner />
        ) : runs.length === 0 ? (
          <p className="text-gray-500 text-center py-4">No runs yet. Trigger a pipeline run to get started.</p>
        ) : (
          <div className="space-y-3">
            {runs.slice(0, 3).map((run) => (
              <div
                key={run.run_id}
                className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
              >
                <div className="flex items-center gap-4">
                  <StatusBadge status={run.status} />
                  <span className="text-sm font-mono text-gray-600">{run.run_id}</span>
                </div>
                <div className="text-sm text-gray-500">
                  {run.items_persisted} items persisted
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
