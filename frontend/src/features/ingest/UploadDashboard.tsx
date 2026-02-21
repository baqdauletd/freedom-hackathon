const uploadCards = [
  {
    title: 'Tickets CSV',
    description: 'Client GUID, demographics, segment, description, attachments, address.',
    example: 'tickets.csv',
  },
  {
    title: 'Managers CSV',
    description: 'Manager name, role, skills, business unit, active workload.',
    example: 'managers.csv',
  },
  {
    title: 'Business Units CSV',
    description: 'Office name and address to calculate proximity.',
    example: 'business_units.csv',
  },
]

const outputManagers = [
  {
    name: 'E. Karimova',
    title: 'Lead Specialist',
    office: 'Astana',
    skills: ['VIP', 'KZ', 'ENG'],
    assigned: 18,
    load: '72%',
  },
  {
    name: 'I. Ospan',
    title: 'Chief Specialist',
    office: 'Almaty',
    skills: ['VIP', 'ENG'],
    assigned: 15,
    load: '58%',
  },
  {
    name: 'S. Kassenov',
    title: 'Specialist',
    office: 'Shymkent',
    skills: ['KZ', 'RU'],
    assigned: 12,
    load: '51%',
  },
]

function UploadDashboard() {
  return (
    <div className="ingest">
      <header className="ingest-hero">
        <div>
          <p className="eyebrow">After-hours routing</p>
          <h1>Upload CSVs → Get routed results</h1>
          <p className="hero-sub">
            Drop the three datasets, run AI enrichment + rules engine, then review the final
            assignments by manager.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary">Run routing</button>
          <button className="ghost">View sample format</button>
        </div>
      </header>

      <section className="upload-grid">
        {uploadCards.map((card) => (
          <div className="upload-card" key={card.title}>
            <div>
              <p className="upload-title">{card.title}</p>
              <p className="muted">{card.description}</p>
            </div>
            <div className="dropzone">
              <p>Drag & drop CSV</p>
              <span>or click to browse</span>
            </div>
            <p className="upload-example">Example: {card.example}</p>
          </div>
        ))}
      </section>

      <section className="status">
        <div className="status-card">
          <p className="status-title">Pipeline status</p>
          <div className="status-row">
            <span className="status-dot" />
            <div>
              <p className="status-label">AI enrichment</p>
              <p className="muted">Classification, tone, language, summary, geocoding</p>
            </div>
            <span className="status-time">~6s per ticket</span>
          </div>
          <div className="status-row">
            <span className="status-dot amber" />
            <div>
              <p className="status-label">Business rules</p>
              <p className="muted">Office proximity, skills filters, round-robin balancing</p>
            </div>
            <span className="status-time">~2s per ticket</span>
          </div>
          <div className="status-row">
            <span className="status-dot green" />
            <div>
              <p className="status-label">Assignments ready</p>
              <p className="muted">Preview managers and routed tickets</p>
            </div>
            <span className="status-time">Realtime</span>
          </div>
        </div>

        <div className="status-card highlight">
          <p className="highlight-title">AI command center</p>
          <p className="highlight-text">
            Ask: “Show distribution of complaint types by city” — we generate a chart instantly.
          </p>
          <button className="ghost">Launch assistant</button>
        </div>
      </section>

      <section className="result">
        <div className="panel-header">
          <h3>Routed managers</h3>
          <button className="ghost">Export results</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Manager</th>
              <th>Office</th>
              <th>Skills</th>
              <th>Assigned tickets</th>
              <th>Load</th>
            </tr>
          </thead>
          <tbody>
            {outputManagers.map((manager) => (
              <tr key={manager.name}>
                <td>
                  <div className="ticket-id">{manager.name}</div>
                  <div className="muted">{manager.title}</div>
                </td>
                <td>{manager.office}</td>
                <td>
                  <div className="badge-row">
                    {manager.skills.map((skill) => (
                      <span key={skill} className="badge">
                        {skill}
                      </span>
                    ))}
                  </div>
                </td>
                <td>{manager.assigned}</td>
                <td>
                  <span className="chip">{manager.load}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default UploadDashboard
