import type { NewsItem } from '../types'
import { NewsCard } from './NewsCard'
import { LoadingSpinner } from './LoadingSpinner'

interface NewsListProps {
  items: NewsItem[]
  loading: boolean
  error: string | null
}

export function NewsList({ items, loading, error }: NewsListProps) {
  if (loading) {
    return <LoadingSpinner />
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 mb-2">Failed to load news</p>
        <p className="text-gray-500 text-sm">{error}</p>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">No articles found</p>
      </div>
    )
  }

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <NewsCard key={item.id} item={item} />
      ))}
    </div>
  )
}
