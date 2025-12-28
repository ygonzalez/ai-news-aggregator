export interface PipelineRun {
  run_id: string
  run_date: string
  started_at: string | null
  completed_at: string | null
  items_collected: number
  items_processed: number
  items_persisted: number
  status: 'running' | 'completed' | 'failed'
  error_message: string | null
  duration_seconds: number | null
}

export interface PipelineRunsResponse {
  runs: PipelineRun[]
  count: number
}

export interface LangSmithRun {
  id: string
  name: string
  status: string
  start_time: string | null
  end_time: string | null
  duration_ms: number | null
  error: string | null
  langsmith_url: string
  // Token usage
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  // Cost
  total_cost: number | null
}

export interface LangSmithRunsResponse {
  runs: LangSmithRun[]
  count: number
  project_name: string
}

export interface GraphResponse {
  mermaid: string
  nodes: string[]
}

export interface RunRequest {
  backfill_days: number
}

export interface RunResponse {
  status: 'started' | 'completed' | 'failed'
  run_id: string | null
  message: string
  stats: {
    total_items?: number
    persisted_count?: number
    collection_errors?: number
  } | null
}

export interface HealthResponse {
  status: string
  database: boolean
  pgvector: boolean
  timestamp: string
}
