import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAppState } from '../state/AppStateContext'

const titles: Record<string, string> = {
  '/upload': 'Upload & Process',
  '/results': 'Routing Results',
  '/analytics': 'Analytics Studio',
}

function AppShell() {
  const location = useLocation()
  const { latestRun } = useAppState()
  const title = titles[location.pathname] ?? 'FIRE Dashboard'
  const dayLabel = new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  }).format(new Date())

  const canExport = Boolean(latestRun?.results.length)
  const scopeParams = new URLSearchParams(location.search)
  const sharedScope = new URLSearchParams()
  const scopeKeys = ["run_id", "office", "office_id", "date_from", "date_to"]
  for (const key of scopeKeys) {
    const value = scopeParams.get(key)
    if (value) sharedScope.set(key, value)
  }
  if (!sharedScope.get("run_id") && latestRun?.run_id) {
    sharedScope.set("run_id", latestRun.run_id)
  }
  const sharedQuery = sharedScope.toString()
  const withScope = (path: string) => (sharedQuery ? `${path}?${sharedQuery}` : path)

  const stringifyCsvValue = (value: unknown) => {
    if (Array.isArray(value)) return JSON.stringify(value.join(' | '))
    if (value && typeof value === 'object') return JSON.stringify(JSON.stringify(value))
    return JSON.stringify(value ?? '')
  }

  function exportLatestRun() {
    if (!latestRun?.results.length) return

    const headers = Object.keys(latestRun.results[0])
    const rows = latestRun.results.map((row) =>
      headers.map((key) => stringifyCsvValue((row as Record<string, unknown>)[key])).join(',')
    )
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = latestRun.run_id ? `fire-results-${latestRun.run_id}.csv` : 'fire-results.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img
            className="brand-logo"
            src="https://yt3.googleusercontent.com/ytc/AIdro_n5YlppjJyhRbNi1vOal0MzfDmVXaVyfO4LlT03uPQjTsc=s900-c-k-c0x00ffffff-no-rj"
            alt="Freedom Bank logo"
          />
          <div>
            <p className="brand-name">FreedomOps</p>
            <p className="brand-sub">After-hours routing</p>
          </div>
        </div>
        <nav className="nav">
          <NavLink
            end
            to="/upload"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Upload
          </NavLink>
          <NavLink
            to={withScope("/results")}
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Results
          </NavLink>
          <NavLink
            to={withScope("/analytics")}
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Analytics
          </NavLink>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">{dayLabel}</p>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <button className="primary" onClick={exportLatestRun} disabled={!canExport}>
              Export report
            </button>
            <div className="avatar">AI</div>
          </div>
        </header>
        <div className="page">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default AppShell
