import { useState, useMemo } from 'react'
import { ArticleTypeFilter } from './components/ArticleTypeFilter'
import { Header } from './components/Header'
import { TopicFilter } from './components/TopicFilter'
import { NewsList } from './components/NewsList'
import { useNewsItems } from './hooks/useNewsItems'

function App() {
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null)
  const [selectedArticleType, setSelectedArticleType] = useState<string | null>(null)

  const params = useMemo(
    () => ({
      limit: 50,
      topic: selectedTopic ?? undefined,
      articleType: selectedArticleType ?? undefined,
    }),
    [selectedTopic, selectedArticleType]
  )

  const { items, topics, articleTypes, loading, error } = useNewsItems(params)

  return (
    <div className="min-h-screen bg-gray-50">
      <Header itemCount={items.length} />

      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <ArticleTypeFilter
            articleTypes={articleTypes}
            selectedType={selectedArticleType}
            onTypeChange={setSelectedArticleType}
          />
          <div className="h-6 w-px bg-gray-300 hidden sm:block" />
          <TopicFilter
            topics={topics}
            selectedTopic={selectedTopic}
            onTopicChange={setSelectedTopic}
          />
        </div>

        <NewsList items={items} loading={loading} error={error} />
      </main>
    </div>
  )
}

export default App
