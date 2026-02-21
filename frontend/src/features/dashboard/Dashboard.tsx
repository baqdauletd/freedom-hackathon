import { metrics, tickets, topManagers } from './dashboard-data'

function Dashboard() {
  return (
    <>
      <section className="hero">
        <div className="hero-left">
          <p className="hero-tag">Auto assignment in 6 seconds</p>
          <h2>
            After-hours requests turned into <span>actionable work</span>
          </h2>
          <p className="hero-sub">
            NLP summarizes context, validates skills, and balances workload across offices with
            strict rules.
          </p>
          <div className="hero-actions">
            <button className="primary">View routing log</button>
            <button className="ghost">Simulate assignment</button>
          </div>
        </div>
        <div className="hero-right">
          <div className="glass-card">
            <p className="glass-title">AI Summary · Ticket TK-29310</p>
            <p className="glass-text">
              Client reports suspicious transfer attempts and requests immediate lock. Negative
              tone, high urgency. Recommend freeze account and call within 15 minutes.
            </p>
            <div className="badge-row">
              <span className="badge danger">Fraud</span>
              <span className="badge">Priority 9</span>
              <span className="badge">KZ</span>
              <span className="badge">VIP</span>
            </div>
          </div>
        </div>
      </section>

      <section className="metrics">
        {metrics.map((metric) => (
          <div className="metric-card" key={metric.label}>
            <p className="metric-label">{metric.label}</p>
            <p className="metric-value">{metric.value}</p>
            <p className="metric-delta">{metric.delta}</p>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panel-header">
            <h3>Live queue</h3>
            <button className="ghost">Export CSV</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Client</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Language</th>
                <th>Assigned</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr key={ticket.id}>
                  <td>
                    <div className="ticket-id">{ticket.id}</div>
                    <div className="muted">{ticket.city}</div>
                  </td>
                  <td>{ticket.client}</td>
                  <td>
                    <span className={`chip chip-${ticket.tone.toLowerCase()}`}>
                      {ticket.type}
                    </span>
                  </td>
                  <td>{ticket.priority}</td>
                  <td>{ticket.lang}</td>
                  <td>{ticket.manager}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel stack">
          <div className="panel">
            <div className="panel-header">
              <h3>Office load</h3>
              <button className="ghost">Balance mode</button>
            </div>
            <div className="office">
              <div>
                <p className="office-title">Astana</p>
                <p className="muted">22 active · 8 managers</p>
              </div>
              <div className="bar">
                <span style={{ width: '72%' }} />
              </div>
            </div>
            <div className="office">
              <div>
                <p className="office-title">Almaty</p>
                <p className="muted">18 active · 7 managers</p>
              </div>
              <div className="bar">
                <span style={{ width: '58%' }} />
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <h3>Top managers</h3>
              <button className="ghost">Reassign</button>
            </div>
            <div className="manager-list">
              {topManagers.map((manager) => (
                <div className="manager" key={manager.name}>
                  <div>
                    <p className="manager-name">{manager.name}</p>
                    <p className="muted">{manager.title}</p>
                    <div className="badge-row">
                      {manager.skills.map((skill) => (
                        <span key={skill} className="badge">
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="load">
                    <span>{manager.load} in work</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="detail">
        <div className="detail-card">
          <div className="panel-header">
            <h3>Focused ticket</h3>
            <span className="badge">Round robin #2</span>
          </div>
          <div className="detail-grid">
            <div>
              <p className="muted">Client</p>
              <p className="detail-value">A. Tleuova · VIP</p>
              <p className="muted">Address</p>
              <p className="detail-value">Astana, Yessil, Dostyk 10</p>
              <p className="muted">Detected language</p>
              <p className="detail-value">KZ</p>
            </div>
            <div>
              <p className="muted">Summary</p>
              <p className="detail-value">
                Suspicious transfer attempts, requests account lock. Immediate action required.
              </p>
              <p className="muted">Recommendation</p>
              <p className="detail-value">Freeze account, call within 15 minutes.</p>
            </div>
            <div>
              <p className="muted">Assigned manager</p>
              <p className="detail-value">E. Karimova</p>
              <p className="muted">Skills matched</p>
              <div className="badge-row">
                <span className="badge">VIP</span>
                <span className="badge">KZ</span>
                <span className="badge">Fraud</span>
              </div>
              <button className="primary full">Open ticket</button>
            </div>
          </div>
        </div>
        <div className="detail-card highlight">
          <p className="highlight-title">AI Command Center</p>
          <p className="highlight-text">
            Ask: “Show distribution of complaint types by city” — the assistant builds charts and
            dashboards instantly.
          </p>
          <button className="ghost">Launch assistant</button>
        </div>
      </section>
    </>
  )
}

export default Dashboard
