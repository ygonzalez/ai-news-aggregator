export interface NewsItem {
  id: string
  title: string
  summary: string
  key_points: string[]
  topics: string[]
  article_type: string
  urls: string[]
  sources: string[]
  published_at: string
}

export interface ItemsResponse {
  items: NewsItem[]
  count: number
  total?: number
}

export interface TopicsResponse {
  topics: string[]
}

export interface ArticleTypesResponse {
  article_types: string[]
}

export interface HealthResponse {
  status: string
  database: boolean
  pgvector: boolean
  timestamp: string
}
