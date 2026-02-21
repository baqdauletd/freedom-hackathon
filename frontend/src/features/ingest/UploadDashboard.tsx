import type { DragEvent } from 'react'
import { useMemo, useRef, useState } from 'react'

const uploadCards = [
  {
    key: 'tickets',
    title: 'Tickets CSV',
    description: 'Client GUID, demographics, segment, description, attachments, address.',
    example: 'tickets.csv',
  },
  {
    key: 'managers',
    title: 'Managers CSV',
    description: 'Manager name, role, skills, business unit, active workload.',
    example: 'managers.csv',
  },
  {
    key: 'business_units',
    title: 'Business Units CSV',
    description: 'Office name and address to calculate proximity.',
    example: 'business_units.csv',
  },
]

type RouteResult = {
  ticket_id: string | number
  ticket_index: number
  ticket_type: string
  sentiment: string
  priority: number
  language: string
  summary: string
  recommendation: string
  office: string
  selected_managers: string[]
  assigned_manager: string | null
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

type UploadKey = (typeof uploadCards)[number]['key']

function UploadDashboard() {
  const [files, setFiles] = useState<Record<UploadKey, File | null>>({
    tickets: null,
    managers: null,
    business_units: null,
  })
  const [dragging, setDragging] = useState<Record<UploadKey, boolean>>({
    tickets: false,
    managers: false,
    business_units: false,
  })
  const [results, setResults] = useState<RouteResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const inputRefs = useRef<Array<HTMLInputElement | null>>([])

  const canSubmit = useMemo(
    () => !!files.tickets && !!files.managers && !!files.business_units && !loading,
    [files, loading]
  )

  function handleFileSelect(key: UploadKey, file: File | null) {
    setFiles((prev) => ({ ...prev, [key]: file }))
  }

  function handleBrowse(index: number) {
    inputRefs.current[index]?.click()
  }

  function handleDrop(key: UploadKey, event: DragEvent<HTMLButtonElement>) {
    event.preventDefault()
    setDragging((prev) => ({ ...prev, [key]: false }))
    const file = event.dataTransfer.files?.[0] ?? null
    handleFileSelect(key, file)
  }

  function handleDragOver(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault()
  }

  function handleDragEnter(key: UploadKey) {
    setDragging((prev) => ({ ...prev, [key]: true }))
  }

  function handleDragLeave(key: UploadKey) {
    setDragging((prev) => ({ ...prev, [key]: false }))
  }

  async function runRouting() {
    setError('')
    if (!files.tickets || !files.managers || !files.business_units) {
      setError('Please upload all three CSV files.')
      return
    }

    const form = new FormData()
    form.append('tickets', files.tickets)
    form.append('managers', files.managers)
    form.append('business_units', files.business_units)

    setLoading(true)
    try {
      const response = await fetch(`${API_BASE}/route/upload`, {
        method: 'POST',
        body: form,
      })
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || 'Request failed')
      }
      const data = (await response.json()) as RouteResult[]
      setResults(data)
    } catch (err: any) {
      setError(err?.message || 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  function downloadCSV() {
    if (!results.length) return
    const headers = Object.keys(results[0])
    const rows = results.map((row) =>
      headers
        .map((key) => {
          const value = (row as any)[key]
          return JSON.stringify(value ?? '')
        })
        .join(',')
    )
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'routing_results.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

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
          <button className="primary" onClick={runRouting} disabled={!canSubmit}>
            {loading ? 'Running...' : 'Run routing'}
          </button>
          <button className="ghost">View sample format</button>
        </div>
      </header>

      <section className="upload-grid">
        {uploadCards.map((card, index) => (
          <div className="upload-card" key={card.title}>
            <div>
              <p className="upload-title">{card.title}</p>
              <p className="muted">{card.description}</p>
            </div>
            <input
              ref={(el) => {
                inputRefs.current[index] = el
              }}
              className="file-input"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => handleFileSelect(card.key, event.target.files?.[0] ?? null)}
            />
            <button
              className={`dropzone${dragging[card.key] ? ' is-dragging' : ''}`}
              type="button"
              onClick={() => handleBrowse(index)}
              onDragOver={handleDragOver}
              onDragEnter={() => handleDragEnter(card.key)}
              onDragLeave={() => handleDragLeave(card.key)}
              onDrop={(event) => handleDrop(card.key, event)}
            >
              {files[card.key] ? (
                <>
                  <p>{files[card.key]?.name}</p>
                  <span>Click to replace</span>
                </>
              ) : (
                <>
                  <p>Drag & drop CSV</p>
                  <span>or click to browse</span>
                </>
              )}
            </button>
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
          <h3>Routed results</h3>
          <div className="panel-actions">
            {error ? <span className="error-text">{error}</span> : null}
            <button className="ghost" onClick={downloadCSV} disabled={!results.length}>
              Export results
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Ticket ID</th>
              <th>Type</th>
              <th>Sentiment</th>
              <th>Priority</th>
              <th>Language</th>
              <th>Office</th>
              <th>Assigned manager</th>
            </tr>
          </thead>
          <tbody>
            {results.map((row) => (
              <tr key={row.ticket_index}>
                <td>
                  <div className="ticket-id">{row.ticket_id}</div>
                </td>
                <td>{row.ticket_type}</td>
                <td>{row.sentiment}</td>
                <td>{row.priority}</td>
                <td>{row.language}</td>
                <td>{row.office}</td>
                <td>{row.assigned_manager || '-'}</td>
              </tr>
            ))}
            {!results.length ? (
              <tr>
                <td className="muted" colSpan={7}>
                  Upload files and run routing to see results.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default UploadDashboard
