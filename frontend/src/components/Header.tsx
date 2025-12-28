interface HeaderProps {
  itemCount: number
}

export function Header({ itemCount }: HeaderProps) {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-gray-900">AI News Aggregator</h1>
        <p className="text-sm text-gray-500 mt-1">
          {itemCount} {itemCount === 1 ? 'article' : 'articles'} from AI/ML blogs and newsletters
        </p>
      </div>
    </header>
  )
}
