import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/runs', label: 'Pipeline Runs' },
  { to: '/graph', label: 'Graph' },
]

export function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-gray-200 p-6">
      <h1 className="text-xl font-bold text-gray-900 mb-8">
        Admin
        <span className="block text-sm font-normal text-gray-500">
          AI News Aggregator
        </span>
      </h1>
      <nav className="space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `block px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-8 pt-8 border-t border-gray-200">
        <a
          href="http://localhost:5173"
          target="_blank"
          rel="noopener noreferrer"
          className="block px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
        >
          View Public Site
        </a>
      </div>
    </aside>
  )
}
