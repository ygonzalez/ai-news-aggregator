import { useState } from 'react'
import { triggerRun } from '../api/client'

interface TriggerButtonProps {
  onComplete?: () => void
}

export function TriggerButton({ onComplete }: TriggerButtonProps) {
  const [running, setRunning] = useState(false)
  const [backfillDays, setBackfillDays] = useState(0)
  const [result, setResult] = useState<{ status: string; message: string } | null>(null)

  const handleTrigger = async () => {
    setRunning(true)
    setResult(null)
    try {
      const response = await triggerRun(backfillDays)
      setResult({ status: response.status, message: response.message })
      onComplete?.()
    } catch (err) {
      setResult({
        status: 'failed',
        message: err instanceof Error ? err.message : 'Unknown error'
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <select
          value={backfillDays}
          onChange={(e) => setBackfillDays(Number(e.target.value))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={running}
        >
          <option value={0}>Today only</option>
          <option value={1}>Last 1 day</option>
          <option value={3}>Last 3 days</option>
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
        </select>
        <button
          onClick={handleTrigger}
          disabled={running}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {running ? 'Running...' : 'Run Pipeline'}
        </button>
      </div>
      {result && (
        <p className={`text-sm ${result.status === 'completed' ? 'text-green-600' : 'text-red-600'}`}>
          {result.message}
        </p>
      )}
    </div>
  )
}
