import type { ArticleTypesResponse, ItemsResponse, TopicsResponse } from '../types'

const API_BASE = '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new ApiError(
      `API request failed: ${response.statusText}`,
      response.status
    )
  }
  return response.json()
}

export interface FetchItemsParams {
  limit?: number
  topic?: string
  articleType?: string
}

export async function fetchItems(params: FetchItemsParams = {}): Promise<ItemsResponse> {
  const searchParams = new URLSearchParams()

  if (params.limit) {
    searchParams.set('limit', String(params.limit))
  }
  if (params.topic) {
    searchParams.set('topic', params.topic)
  }
  if (params.articleType) {
    searchParams.set('article_type', params.articleType)
  }

  const queryString = searchParams.toString()
  const url = `${API_BASE}/items${queryString ? `?${queryString}` : ''}`

  return fetchJson<ItemsResponse>(url)
}

export async function fetchTopics(): Promise<TopicsResponse> {
  return fetchJson<TopicsResponse>(`${API_BASE}/topics`)
}

export async function fetchArticleTypes(): Promise<ArticleTypesResponse> {
  return fetchJson<ArticleTypesResponse>(`${API_BASE}/article-types`)
}
