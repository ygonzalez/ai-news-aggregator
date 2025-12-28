import { useState, useEffect, useCallback } from 'react'
import type { NewsItem } from '../types'
import { fetchArticleTypes, fetchItems, fetchTopics, type FetchItemsParams } from '../api/client'

interface UseNewsItemsResult {
  items: NewsItem[]
  topics: string[]
  articleTypes: string[]
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useNewsItems(params: FetchItemsParams = {}): UseNewsItemsResult {
  const [items, setItems] = useState<NewsItem[]>([])
  const [topics, setTopics] = useState<string[]>([])
  const [articleTypes, setArticleTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchItems(params)
      setItems(response.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch news items')
    } finally {
      setLoading(false)
    }
  }, [params.limit, params.topic, params.articleType, params.minRelevance])

  const loadTopics = useCallback(async () => {
    try {
      const response = await fetchTopics()
      setTopics(response.topics)
    } catch (err) {
      console.error('Failed to fetch topics:', err)
    }
  }, [])

  const loadArticleTypes = useCallback(async () => {
    try {
      const response = await fetchArticleTypes()
      setArticleTypes(response.article_types)
    } catch (err) {
      console.error('Failed to fetch article types:', err)
    }
  }, [])

  useEffect(() => {
    loadTopics()
    loadArticleTypes()
  }, [loadTopics, loadArticleTypes])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  return { items, topics, articleTypes, loading, error, refetch: loadItems }
}
