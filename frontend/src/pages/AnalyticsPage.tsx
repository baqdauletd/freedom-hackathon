import { useEffect, useMemo, useRef, useState } from "react"
import { askAssistant, getAnalyticsSummary } from "../api/analytics-api"
import type {
  AssistantClarificationResponse,
  AssistantResponse,
  AssistantResultResponse,
} from "../api/contracts"
import { useAppState } from "../state/AppStateContext"

type SimpleDatum = { label: string; value: number }

type AssistantTurn = {
  id: string
  query: string
  status: "loading" | "done" | "error"
  response?: AssistantResponse
  error?: string
}

const COLORS = ["#2f6cfb", "#ff6b4a", "#21b573", "#f8c75b", "#7b8bbd", "#151a2d"]

const toSeries = <T,>(rows: T[], labelKey: keyof T, valueKey: keyof T): SimpleDatum[] =>
  rows.map((row) => ({ label: String(row[labelKey] ?? "-"), value: Number(row[valueKey] ?? 0) }))

const buildPie = (data: SimpleDatum[]) => {
  const total = data.reduce((sum, item) => sum + item.value, 0)
  if (total <= 0) return "conic-gradient(#e0e4ef 0 100%)"

  let cursor = 0
  const segments = data.map((item, index) => {
    const slice = (item.value / total) * 100
    const start = cursor
    const end = cursor + slice
    cursor = end
    return `${COLORS[index % COLORS.length]} ${start}% ${end}%`
  })
  return `conic-gradient(${segments.join(", ")})`
}

const normalizeAssistantSeries = (response: AssistantResultResponse): SimpleDatum[] => {
  if (!response?.data?.labels?.length || !response?.data?.values?.length) return []
  return response.data.labels.map((label, index) => ({
    label,
    value: Number(response.data.values[index] ?? 0),
  }))
}

function ChartCard({
  title,
  description,
  data,
  mode,
}: {
  title: string
  description: string
  data: SimpleDatum[]
  mode: "bar" | "pie" | "line"
}) {
  const max = Math.max(1, ...data.map((item) => item.value))

  return (
    <article className="panel chart-card">
      <div className="panel-header">
        <h3>{title}</h3>
        <p className="muted">{description}</p>
      </div>
      {!data.length ? (
        <p className="muted">No data for the selected filters.</p>
      ) : mode === "pie" ? (
        <div className="pie-wrap">
          <div className="pie-chart" style={{ background: buildPie(data) }} />
          <ul className="legend-list">
            {data.map((item, index) => (
              <li key={item.label}>
                <span className="legend-dot" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                {item.label}: {item.value}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="bar-list">
          {data.map((item, index) => (
            <div className="bar-row" key={item.label}>
              <span className="bar-label">{item.label}</span>
              <div className="bar-track">
                <span
                  className="bar-fill"
                  style={{
                    width: `${(item.value / max) * 100}%`,
                    background: COLORS[index % COLORS.length],
                  }}
                />
              </div>
              <span className="bar-value">{item.value.toFixed(item.value % 1 ? 2 : 0)}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function AssistantTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p className="muted">No table rows returned.</p>
  const columns = Object.keys(rows[0])

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((col) => (
                <td key={`${index}-${col}`}>{String(row[col] ?? "-")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AppliedFilters({ result }: { result: AssistantResultResponse }) {
  const chips: string[] = []
  result.filters.office_names.forEach((officeName) => chips.push(`office: ${officeName}`))
  result.filters.cities.forEach((city) => chips.push(`city: ${city}`))
  if (result.filters.segment) chips.push(`segment: ${result.filters.segment}`)
  if (result.filters.language) chips.push(`language: ${result.filters.language}`)
  if (result.filters.ticket_type) chips.push(`type: ${result.filters.ticket_type}`)
  if (result.filters.date_from) chips.push(`from: ${result.filters.date_from}`)
  if (result.filters.date_to) chips.push(`to: ${result.filters.date_to}`)

  if (!chips.length) return <p className="muted">Applied filters: none</p>

  return (
    <div className="chips-wrap">
      {chips.map((chip) => (
        <span key={chip} className="chip">
          {chip}
        </span>
      ))}
    </div>
  )
}

function ClarificationOptions({
  response,
  onPick,
}: {
  response: AssistantClarificationResponse
  onPick: (query: string) => void
}) {
  return (
    <div className="clarification-options">
      <p className="muted">{response.explanation}</p>
      <div className="panel-actions">
        {response.options.map((option) => (
          <button key={`${option.intent}-${option.label}`} className="ghost" onClick={() => onPick(option.query_hint)}>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function AssistantResultCard({
  response,
  onApplyFilters,
  onPin,
}: {
  response: AssistantResultResponse
  onApplyFilters: (result: AssistantResultResponse) => void
  onPin: (result: AssistantResultResponse) => void
}) {
  const series = normalizeAssistantSeries(response)
  const mode =
    response.chart_type === "pie" || response.chart_type === "donut"
      ? "pie"
      : response.chart_type === "line"
        ? "line"
        : "bar"

  return (
    <div className="assistant-result">
      <div className="panel-header">
        <div>
          <p className="muted">Intent: {response.intent}</p>
          <h4>{response.title}</h4>
        </div>
        <div className="panel-actions">
          {response.used_fallback ? <span className="badge badge-offline">Using offline mode</span> : null}
          {response.cache_hit ? <span className="badge">Cached</span> : null}
        </div>
      </div>

      <p>{response.explanation}</p>

      {response.chart_type === "empty" ? (
        <p className="muted">No data in selected scope.</p>
      ) : (
        <ChartCard
          title="Assistant chart"
          description={`Suggested ${response.chart_type} visualization`}
          data={series}
          mode={mode}
        />
      )}

      <AssistantTable rows={response.table} />
      <AppliedFilters result={response} />

      {response.warnings?.length ? (
        <ul className="mini-list">
          {response.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div className="panel-actions">
        <button className="ghost" onClick={() => onApplyFilters(response)}>
          Apply filters to scope
        </button>
        <button className="ghost" onClick={() => onPin(response)}>
          Pin to dashboard
        </button>
      </div>
    </div>
  )
}

function AnalyticsPage() {
  const { latestRun, pinnedCharts, pinChart, clearPinnedCharts } = useAppState()
  const runId = latestRun?.run_id || ""
  const [office, setOffice] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [summary, setSummary] = useState<{
    ticket_types_by_city: Array<{ city: string; ticket_type: string; count: number }>
    sentiment_distribution: Array<{ tone: string; count: number }>
    avg_priority_by_office: Array<{ office: string; avg_priority: number }>
  } | null>(null)
  const [error, setError] = useState("")

  const [assistantInput, setAssistantInput] = useState("")
  const [assistantTurns, setAssistantTurns] = useState<AssistantTurn[]>([])
  const assistantTurnCounter = useRef(0)

  const hasActiveFilters = Boolean(office || dateFrom || dateTo)

  const clearFilters = () => {
    setOffice("")
    setDateFrom("")
    setDateTo("")
  }

  useEffect(() => {
    if (!runId) return

    let alive = true

    getAnalyticsSummary({
      run_id: runId,
      office: office || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    })
      .then((analyticsPayload) => {
        if (!alive) return
        const analytics = analyticsPayload as {
          ticket_types_by_city: Array<{ city: string; ticket_type: string; count: number }>
          sentiment_distribution: Array<{ tone: string; count: number }>
          avg_priority_by_office: Array<{ office: string; avg_priority: number }>
        }

        setSummary({
          ticket_types_by_city: analytics.ticket_types_by_city || [],
          sentiment_distribution: analytics.sentiment_distribution || [],
          avg_priority_by_office: analytics.avg_priority_by_office || [],
        })
        setError("")
      })
      .catch((requestError: unknown) => {
        if (!alive) return
        setSummary(null)
        setError(requestError instanceof Error ? requestError.message : "Failed to load analytics.")
      })

    return () => {
      alive = false
    }
  }, [runId, dateFrom, dateTo, office])

  const chartData = useMemo(() => {
    if (!runId || !summary) return null

    const typeByCity = summary.ticket_types_by_city.reduce<Record<string, number>>((acc, row) => {
      const key = `${row.city} · ${row.ticket_type}`
      acc[key] = (acc[key] || 0) + row.count
      return acc
    }, {})

    return {
      typeByCity: Object.entries(typeByCity)
        .map(([label, value]) => ({ label, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 12),
      sentiment: toSeries(summary.sentiment_distribution, "tone", "count"),
      avgPriority: toSeries(summary.avg_priority_by_office, "office", "avg_priority"),
    }
  }, [runId, summary])

  const suggestions = useMemo(() => {
    const officeHint = office ? ` for office ${office}` : ""
    const dateHint = dateFrom || dateTo ? ` from ${dateFrom || "start"} to ${dateTo || "today"}` : ""
    return [
      `Tickets by office${dateHint}`,
      `Sentiment distribution${officeHint}${dateHint}`,
      `Average priority by office${dateHint}`,
      `Top managers by assigned tickets${officeHint}${dateHint}`,
      `VIP vs Mass breakdown${dateHint}`,
    ]
  }, [office, dateFrom, dateTo])

  const applyFiltersFromAssistant = (result: AssistantResultResponse) => {
    setOffice(result.filters.office_names[0] || "")
    setDateFrom(result.filters.date_from || "")
    setDateTo(result.filters.date_to || "")
  }

  const submitAssistant = async (text?: string) => {
    const query = (text ?? assistantInput).trim()
    if (!query) return

    assistantTurnCounter.current += 1
    const turnId = `turn-${assistantTurnCounter.current}`
    setAssistantInput("")
    setAssistantTurns((prev) => [...prev, { id: turnId, query, status: "loading" }])

    try {
      const response = await askAssistant({
        query,
        run_id: runId || undefined,
        office: office || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })

      setAssistantTurns((prev) =>
        prev.map((turn) => (turn.id === turnId ? { ...turn, status: "done", response } : turn)),
      )
    } catch (requestError: unknown) {
      const message = requestError instanceof Error ? requestError.message : "Assistant request failed."
      setAssistantTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId
            ? {
                ...turn,
                status: "error",
                error: message,
              }
            : turn,
        ),
      )
    }
  }

  return (
    <section className="analytics-page">
      <header className="panel">
        <div className="panel-header">
          <div>
            <h3>Analytics dashboard</h3>
            <p className="muted">Clean operational metrics for the latest upload.</p>
            <p className="muted">Showing latest upload only.</p>
          </div>
          <button className="ghost" type="button" onClick={clearFilters} disabled={!hasActiveFilters}>
            Clear filters
          </button>
        </div>
        <div className="filter-grid inline-filters">
          <label>
            Office
            <input value={office} onChange={(event) => setOffice(event.target.value)} placeholder="Optional" />
          </label>
          <label>
            Date from
            <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            Date to
            <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
        </div>
      </header>

      {runId && error ? <p className="error-text">{error}</p> : null}
      {!runId ? <p className="muted">Upload files first to view analytics for the latest run.</p> : null}

      <div className="charts-grid">
        <ChartCard
          title="Types by city"
          description="Distribution of ticket categories by city."
          data={chartData?.typeByCity || []}
          mode="bar"
        />
        <ChartCard
          title="Sentiment distribution"
          description="Positive, neutral, and negative share."
          data={chartData?.sentiment || []}
          mode="pie"
        />
        <ChartCard
          title="Average priority by office"
          description="Operational urgency by office."
          data={chartData?.avgPriority || []}
          mode="bar"
        />
      </div>

      <section className="panel assistant-panel">
        <div className="panel-header">
          <div>
            <h3>AI Assistant</h3>
            <p className="muted">Ask analytics questions in plain language.</p>
          </div>
          <button className="ghost" onClick={() => setAssistantTurns([])} disabled={!assistantTurns.length}>
            Clear chat
          </button>
        </div>

        <div className="assistant-suggestions">
          {suggestions.map((suggestion) => (
            <button key={suggestion} className="ghost" onClick={() => submitAssistant(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>

        <div className="assistant-controls">
          <input
            value={assistantInput}
            onChange={(event) => setAssistantInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                void submitAssistant()
              }
            }}
            placeholder="Ask: Show unassigned rate and reasons in Astana"
          />
          <button className="primary" onClick={() => void submitAssistant()}>
            Ask assistant
          </button>
        </div>

        {!assistantTurns.length ? <p className="muted">Start with a suggestion or type your own question.</p> : null}

        <div className="assistant-chat">
          {assistantTurns.map((turn) => (
            <div key={turn.id} className="assistant-turn">
              <div className="assistant-user-bubble">{turn.query}</div>
              <div className="assistant-ai-bubble">
                {turn.status === "loading" ? (
                  <p className="muted">Thinking<span className="loading-dots">...</span></p>
                ) : null}

                {turn.status === "error" ? <p className="error-text">{turn.error}</p> : null}

                {turn.status === "done" && turn.response?.kind === "clarification" ? (
                  <ClarificationOptions
                    response={turn.response}
                    onPick={(queryHint) => {
                      void submitAssistant(queryHint)
                    }}
                  />
                ) : null}

                {turn.status === "done" && turn.response?.kind === "result" ? (
                  <AssistantResultCard
                    response={turn.response}
                    onApplyFilters={applyFiltersFromAssistant}
                    onPin={pinChart}
                  />
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="panel">
        <div className="panel-header">
          <h3>Pinned assistant charts</h3>
          <button className="ghost" onClick={clearPinnedCharts} disabled={!pinnedCharts.length}>
            Clear
          </button>
        </div>
        {!pinnedCharts.length ? <p className="muted">No pinned charts yet.</p> : null}
        <div className="charts-grid">
          {pinnedCharts.map((chart, index) => (
            <ChartCard
              key={`${chart.intent}-${index}`}
              title={chart.title}
              description={chart.explanation}
              data={normalizeAssistantSeries(chart)}
              mode={chart.chart_type === "pie" || chart.chart_type === "donut" ? "pie" : chart.chart_type === "line" ? "line" : "bar"}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

export default AnalyticsPage
