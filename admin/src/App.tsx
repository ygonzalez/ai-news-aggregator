import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Runs } from './pages/Runs'
import { Graph } from './pages/Graph'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="runs" element={<Runs />} />
          <Route path="graph" element={<Graph />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
