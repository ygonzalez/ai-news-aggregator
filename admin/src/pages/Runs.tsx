import { usePipelineRuns } from '../hooks/usePipelineRuns'
import { useLangSmithRuns } from '../hooks/useLangSmithRuns'
import { RunsTable } from '../components/RunsTable'
import { LangSmithRunsList } from '../components/LangSmithRunsList'
import { TriggerButton } from '../components/TriggerButton'

export function Runs() {
  const { runs, loading, error, refetch } = usePipelineRuns(20)
  const {
    runs: lsRuns,
    projectName,
    loading: lsLoading,
    error: lsError,
    notConfigured,
  } = useLangSmithRuns(10)

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pipeline Runs</h1>
          <p className="text-gray-500 mt-1">View run history and trigger new runs</p>
        </div>
        <TriggerButton onComplete={refetch} />
      </div>

      {/* Database Runs */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Database Runs</h2>
        {error ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800 text-sm">
            {error}
          </div>
        ) : (
          <RunsTable runs={runs} loading={loading} />
        )}
      </section>

      {/* LangSmith Runs */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          LangSmith Runs
          {projectName && (
            <span className="text-sm font-normal text-gray-500 ml-2">
              ({projectName})
            </span>
          )}
        </h2>
        {lsError ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800 text-sm">
            {lsError}
          </div>
        ) : (
          <LangSmithRunsList
            runs={lsRuns}
            loading={lsLoading}
            notConfigured={notConfigured}
          />
        )}
      </section>
    </div>
  )
}
