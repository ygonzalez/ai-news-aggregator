import type { NewsItem } from '../types'

interface NewsCardProps {
  item: NewsItem
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 60) {
    return `${diffMins}m ago`
  } else if (diffHours < 24) {
    return `${diffHours}h ago`
  } else if (diffDays < 7) {
    return `${diffDays}d ago`
  } else {
    return date.toLocaleDateString()
  }
}

const topicColors: Record<string, string> = {
  'LLMs': 'bg-purple-100 text-purple-800',
  'AI Agents': 'bg-blue-100 text-blue-800',
  'AI Safety': 'bg-red-100 text-red-800',
  'MLOps': 'bg-green-100 text-green-800',
  'Computer Vision': 'bg-yellow-100 text-yellow-800',
  'NLP': 'bg-indigo-100 text-indigo-800',
  'Open Source': 'bg-orange-100 text-orange-800',
  'Products': 'bg-pink-100 text-pink-800',
  'Research': 'bg-cyan-100 text-cyan-800',
  'Industry': 'bg-gray-100 text-gray-800',
}

const sourceConfig: Record<string, { label: string; color: string }> = {
  'rss': { label: 'RSS', color: 'bg-orange-50 text-orange-600 border-orange-200' },
  'gmail': { label: 'Email', color: 'bg-blue-50 text-blue-600 border-blue-200' },
  'newsletter': { label: 'Newsletter', color: 'bg-violet-50 text-violet-600 border-violet-200' },
  'twitter': { label: 'Twitter', color: 'bg-sky-50 text-sky-600 border-sky-200' },
}

const articleTypeConfig: Record<string, { label: string; color: string }> = {
  'news': { label: 'News', color: 'bg-slate-100 text-slate-700' },
  'tutorial': { label: 'Tutorial', color: 'bg-teal-100 text-teal-700' },
}

export function NewsCard({ item }: NewsCardProps) {
  const primaryUrl = item.urls[0]

  return (
    <article className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4 mb-3">
        <a
          href={primaryUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-lg font-semibold text-gray-900 hover:text-blue-600 transition-colors line-clamp-2"
        >
          {item.title}
        </a>
        <div className="flex items-center gap-2 shrink-0">
          {item.sources.map((source) => {
            const config = sourceConfig[source] || { label: source, color: 'bg-gray-50 text-gray-600 border-gray-200' }
            return (
              <span
                key={source}
                className={`px-1.5 py-0.5 rounded text-xs font-medium border ${config.color}`}
              >
                {config.label}
              </span>
            )
          })}
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {formatRelativeTime(item.published_at)}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {item.article_type && (
          <span
            className={`px-2 py-1 rounded text-xs font-medium ${
              articleTypeConfig[item.article_type]?.color || 'bg-gray-100 text-gray-700'
            }`}
          >
            {articleTypeConfig[item.article_type]?.label || item.article_type}
          </span>
        )}
        {item.topics.map((topic) => (
          <span
            key={topic}
            className={`px-2 py-1 rounded text-xs font-medium ${
              topicColors[topic] || 'bg-gray-100 text-gray-800'
            }`}
          >
            {topic}
          </span>
        ))}
        <span className="px-2 py-1 rounded text-xs font-medium bg-emerald-100 text-emerald-800">
          {Math.round(item.relevance_score * 100)}% relevant
        </span>
      </div>

      <p className="text-gray-600 text-sm mb-4 line-clamp-3">{item.summary}</p>

      {item.key_points.length > 0 && (
        <ul className="text-sm text-gray-700 space-y-1">
          {item.key_points.slice(0, 3).map((point, index) => (
            <li key={index} className="flex items-start gap-2">
              <span className="text-gray-400 mt-1">-</span>
              <span className="line-clamp-1">{point}</span>
            </li>
          ))}
        </ul>
      )}

      {item.urls.length > 1 && (
        <p className="text-xs text-gray-400 mt-4">
          +{item.urls.length - 1} more {item.urls.length === 2 ? 'source' : 'sources'}
        </p>
      )}
    </article>
  )
}
