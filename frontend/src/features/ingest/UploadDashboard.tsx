import type { DragEvent } from "react"
import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { ApiError } from "../../api/client"
import type { RouteResult, RoutingRunEnvelope, RunSummary } from "../../api/contracts"
import { uploadAndRoute } from "../../api/routing"
import { useAppState } from "../../state/AppStateContext"

const uploadCards = [
  {
    key: "tickets",
    title: "Tickets CSV",
    description: "Client GUID, demographics, segment, description, attachments, address.",
    example: "tickets.csv",
  },
  {
    key: "managers",
    title: "Managers CSV",
    description: "Manager name, role, skills, business unit, active workload.",
    example: "managers.csv",
  },
  {
    key: "business_units",
    title: "Business Units CSV",
    description: "Office name and address to calculate proximity.",
    example: "business_units.csv",
  },
] as const

type UploadKey = (typeof uploadCards)[number]["key"]

type UploadFiles = Record<UploadKey, File | null>

const summarizeResults = (results: RouteResult[], elapsedMs: number): RunSummary => {
  const total = results.length
  const success = results.filter((row) => Boolean(row.assigned_manager)).length
  const failed = total - success
  const timedRows = results.filter((row) => typeof row.processing_ms === "number")
  const avgProcessingMs =
    timedRows.length > 0
      ? Math.round(
          timedRows.reduce((sum, row) => sum + Number(row.processing_ms || 0), 0) / timedRows.length,
        )
      : 0

  return {
    total,
    success,
    failed,
    avg_processing_ms: avgProcessingMs,
    elapsed_ms: Math.round(elapsedMs),
  }
}

const toValidationErrors = (error: unknown): string[] => {
  if (!(error instanceof ApiError)) {
    if (error instanceof Error) return [error.message]
    return ["Unknown error"]
  }

  const details = error.body?.details
  if (Array.isArray(error.body?.messages)) {
    const messages = error.body?.messages?.filter((item): item is string => typeof item === "string")
    if (messages?.length) return messages
  }
  if (details && typeof details === "object" && "detail" in (details as Record<string, unknown>)) {
    const detail = (details as Record<string, unknown>).detail
    if (typeof detail === "string") return [detail]
    if (Array.isArray(detail)) {
      const messages: string[] = []
      detail.forEach((item) => {
        if (typeof item === "string") messages.push(item)
        if (item && typeof item === "object") {
          const msg = (item as Record<string, unknown>).msg
          if (typeof msg === "string") messages.push(msg)
        }
      })
      if (messages.length) return messages
    }
  }

  if (typeof error.body?.message === "string") return [error.body.message]
  return [error.message]
}

function UploadDashboard() {
  const navigate = useNavigate()
  const { latestRun, setLatestRun } = useAppState()

  const [files, setFiles] = useState<UploadFiles>({
    tickets: null,
    managers: null,
    business_units: null,
  })
  const [dragging, setDragging] = useState<Record<UploadKey, boolean>>({
    tickets: false,
    managers: false,
    business_units: false,
  })
  const [loading, setLoading] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const inputRefs = useRef<Array<HTMLInputElement | null>>([])

  const canSubmit = useMemo(
    () => Boolean(files.tickets && files.managers && files.business_units && !loading),
    [files, loading],
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
    if (!files.tickets || !files.managers || !files.business_units) {
      setValidationErrors(["Please upload all three CSV files."])
      return
    }

    setValidationErrors([])
    setLoading(true)
    const started = performance.now()

    try {
      const envelope = await uploadAndRoute({
        tickets: files.tickets,
        managers: files.managers,
        business_units: files.business_units,
      })

      const fallbackSummary = summarizeResults(envelope.results, performance.now() - started)
      const normalized: RoutingRunEnvelope = {
        run_id: envelope.run_id,
        results: envelope.results,
        summary:
          envelope.summary && envelope.summary.elapsed_ms > 0
            ? envelope.summary
            : { ...fallbackSummary, ...(envelope.summary || {}) },
      }

      setLatestRun(normalized)
      navigate("/results")
    } catch (error: unknown) {
      setValidationErrors(toValidationErrors(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ingest">
      <header className="ingest-hero">
        <div>
          <p className="eyebrow">After-hours routing</p>
          <h1>Upload CSVs and distribute tickets intelligently</h1>
          <p className="hero-sub">
            Upload all three datasets. We validate the files, run AI enrichment, apply routing
            rules, and prepare a review-ready dashboard.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary" onClick={runRouting} disabled={!canSubmit}>
            {loading ? "Processing..." : "Process files"}
          </button>
          <button
            className="ghost"
            type="button"
            onClick={() => navigate("/results")}
            disabled={!latestRun?.results.length}
          >
            Open last results
          </button>
        </div>
      </header>

      {loading ? (
        <section className="status-card upload-progress">
          <div className="panel-header">
            <h3>Processing in progress</h3>
            <span className="muted">AI + routing pipeline</span>
          </div>
          <div className="progress-track">
            <span className="progress-indeterminate" />
          </div>
          <p className="muted">
            We are validating CSVs and processing tickets. You will be redirected to the results
            page automatically.
          </p>
        </section>
      ) : null}

      {validationErrors.length ? (
        <section className="status-card error-card" role="alert">
          <p className="status-title">Please fix these issues</p>
          <ul className="error-list">
            {validationErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="upload-grid">
        {uploadCards.map((card, index) => (
          <div className="upload-card" key={card.key}>
            <div>
              <p className="upload-title">{card.title}</p>
              <p className="muted">{card.description}</p>
            </div>
            <input
              ref={(element) => {
                inputRefs.current[index] = element
              }}
              className="file-input"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => handleFileSelect(card.key, event.target.files?.[0] ?? null)}
            />
            <button
              className={`dropzone${dragging[card.key] ? " is-dragging" : ""}`}
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
                  <p>Drag and drop CSV</p>
                  <span>or click to browse</span>
                </>
              )}
            </button>
            <p className="upload-example">Example: {card.example}</p>
          </div>
        ))}
      </section>

      <section className="status">
        <div className="status-card highlight">
          <p className="highlight-title">Ready for review</p>
          <p className="highlight-text">
            After processing you can drill into each ticket, see routing evidence, and open the AI
            command center for ad-hoc analytics.
          </p>
          <button
            className="ghost"
            onClick={() => navigate("/analytics")}
          >
            Open analytics
          </button>
        </div>
      </section>
    </div>
  )
}

export default UploadDashboard
