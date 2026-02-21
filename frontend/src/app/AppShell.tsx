import { NavLink, Outlet, useLocation } from 'react-router-dom'

const titles: Record<string, string> = {
  '/upload': 'Upload & Process',
  '/results': 'Routing Results',
  '/analytics': 'Analytics Studio',
}

function AppShell() {
  const location = useLocation()
  const title = titles[location.pathname] ?? 'FIRE Dashboard'
  const dayLabel = new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  }).format(new Date())

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
            to="/results"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Results
          </NavLink>
          <NavLink
            to="/analytics"
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
            <div className="search">
              <span className="search-icon" />
              <input placeholder="Search tickets and managers" />
            </div>
            <button className="primary">Export report</button>
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
