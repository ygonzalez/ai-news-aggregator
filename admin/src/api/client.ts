import type {
  PipelineRunsResponse,
  LangSmithRunsResponse,
  GraphResponse,
  RunResponse,
  HealthResponse,
} from '../types'

const API_BASE = '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new ApiError(
      `API request failed: ${response.statusText}`,
      response.status
    )
  }
  return response.json()
}

export async function fetchPipelineRuns(limit = 20): Promise<PipelineRunsResponse> {
  return fetchJson<PipelineRunsResponse>(`${API_BASE}/admin/runs?limit=${limit}`)
}

export async function fetchLangSmithRuns(limit = 10): Promise<LangSmithRunsResponse> {
  return fetchJson<LangSmithRunsResponse>(`${API_BASE}/admin/langsmith-runs?limit=${limit}`)
}

export async function fetchGraph(): Promise<GraphResponse> {
  return fetchJson<GraphResponse>(`${API_BASE}/admin/graph`)
}

export async function triggerRun(backfillDays = 0): Promise<RunResponse> {
  return fetchJson<RunResponse>(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ backfill_days: backfillDays }),
  })
}

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>(`${API_BASE}/health`)
}
