interface TopicFilterProps {
  topics: string[]
  selectedTopic: string | null
  onTopicChange: (topic: string | null) => void
}

export function TopicFilter({ topics, selectedTopic, onTopicChange }: TopicFilterProps) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
      <button
        onClick={() => onTopicChange(null)}
        className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
          selectedTopic === null
            ? 'bg-gray-900 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
      >
        All
      </button>
      {topics.map((topic) => (
        <button
          key={topic}
          onClick={() => onTopicChange(topic)}
          className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            selectedTopic === topic
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {topic}
        </button>
      ))}
    </div>
  )
}
