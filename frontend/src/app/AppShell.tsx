import { NavLink, Outlet, useLocation } from 'react-router-dom'

const titles: Record<string, string> = {
  '/': 'Operations dashboard',
  '/tickets': 'Tickets overview',
  '/managers': 'Managers roster',
  '/business-units': 'Business units',
  '/analytics': 'Analytics studio',
}

function AppShell() {
  const location = useLocation()
  const title = titles[location.pathname] ?? 'Operations dashboard'

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" />
          <div>
            <p className="brand-name">FreedomOps</p>
            <p className="brand-sub">After-hours routing</p>
          </div>
        </div>
        <nav className="nav">
          <NavLink
            end
            to="/"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/tickets"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Tickets
          </NavLink>
          <NavLink
            to="/managers"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Managers
          </NavLink>
          <NavLink
            to="/business-units"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Business units
          </NavLink>
          <NavLink
            to="/analytics"
            className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
          >
            Analytics
          </NavLink>
        </nav>
        <div className="sidebar-card">
          <p className="sidebar-title">AI status</p>
          <p className="sidebar-value">96% confidence</p>
          <p className="sidebar-note">NLP + geocoding healthy</p>
          <div className="progress">
            <span style={{ width: '96%' }} />
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Saturday, Feb 21</p>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <div className="search">
              <span className="search-icon" />
              <input placeholder="Search tickets, clients, managers" />
            </div>
            <button className="primary">Create ticket</button>
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
