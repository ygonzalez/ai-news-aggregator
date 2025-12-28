interface ArticleTypeFilterProps {
  articleTypes: string[]
  selectedType: string | null
  onTypeChange: (type: string | null) => void
}

const typeLabels: Record<string, string> = {
  news: 'News',
  tutorial: 'Tutorials',
}

export function ArticleTypeFilter({ articleTypes, selectedType, onTypeChange }: ArticleTypeFilterProps) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onTypeChange(null)}
        className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
          selectedType === null
            ? 'bg-blue-600 text-white'
            : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
        }`}
      >
        All Types
      </button>
      {articleTypes.map((type) => (
        <button
          key={type}
          onClick={() => onTypeChange(type)}
          className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            selectedType === type
              ? 'bg-blue-600 text-white'
              : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
          }`}
        >
          {typeLabels[type] || type}
        </button>
      ))}
    </div>
  )
}
