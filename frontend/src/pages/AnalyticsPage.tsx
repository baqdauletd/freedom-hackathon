import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { askAssistant, getAnalyticsSummary } from "../api/analytics-api"
import type { AssistantQueryResponse, ManagerListItem } from "../api/contracts"
import { getManagers } from "../api/routing"
import { useAppState } from "../state/AppStateContext"

type SimpleDatum = { label: string; value: number }

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

const normalizeAssistantSeries = (response: AssistantQueryResponse): SimpleDatum[] => {
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

function AnalyticsPage() {
  const [params] = useSearchParams()
  const initialRunId = params.get("run_id") || ""

  const { pinnedCharts, pinChart, clearPinnedCharts } = useAppState()
  const [runId, setRunId] = useState(initialRunId)
  const [office, setOffice] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [summary, setSummary] = useState<{
    ticket_types_by_city: Array<{ city: string; ticket_type: string; count: number }>
    sentiment_distribution: Array<{ tone: string; count: number }>
    avg_priority_by_office: Array<{ office: string; avg_priority: number }>
    workload_by_manager: Array<{ manager: string; current_load: number }>
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const [assistantQuery, setAssistantQuery] = useState("")
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantError, setAssistantError] = useState("")
  const [assistantResult, setAssistantResult] = useState<AssistantQueryResponse | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")

    Promise.all([
      getAnalyticsSummary({
        run_id: runId || undefined,
        office: office || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
      getManagers({ run_id: runId || undefined, office: office || undefined }),
    ])
      .then(([analyticsPayload, managersPayload]) => {
        if (!alive) return
        const managerItems = ((managersPayload as { items?: ManagerListItem[] }).items || []).map((manager) => ({
          manager: manager.full_name,
          current_load: manager.current_load,
          assigned_count: manager.assigned_count,
          office: manager.office,
        }))

        const analytics = analyticsPayload as {
          ticket_types_by_city: Array<{ city: string; ticket_type: string; count: number }>
          sentiment_distribution: Array<{ tone: string; count: number }>
          avg_priority_by_office: Array<{ office: string; avg_priority: number }>
          workload_by_manager?: Array<{ manager: string; current_load: number }>
        }

        setSummary({
          ticket_types_by_city: analytics.ticket_types_by_city || [],
          sentiment_distribution: analytics.sentiment_distribution || [],
          avg_priority_by_office: analytics.avg_priority_by_office || [],
          workload_by_manager: analytics.workload_by_manager || managerItems,
        })
      })
      .catch((requestError: unknown) => {
        if (!alive) return
        setError(requestError instanceof Error ? requestError.message : "Failed to load analytics.")
      })
      .finally(() => {
        if (!alive) return
        setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [dateFrom, dateTo, office, runId])

  const chartData = useMemo(() => {
    if (!summary) return null
    const typeByCity = summary.ticket_types_by_city.reduce<Record<string, number>>((acc, row) => {
      const key = `${row.city} · ${row.ticket_type}`
      acc[key] = (acc[key] || 0) + row.count
      return acc
    }, {})

    return {
      typeByCity: Object.entries(typeByCity).map(([label, value]) => ({ label, value })),
      sentiment: toSeries(summary.sentiment_distribution, "tone", "count"),
      avgPriority: toSeries(summary.avg_priority_by_office, "office", "avg_priority"),
      workload: toSeries(summary.workload_by_manager, "manager", "current_load"),
    }
  }, [summary])

  const submitAssistant = async () => {
    if (!assistantQuery.trim()) return
    setAssistantLoading(true)
    setAssistantError("")
    try {
      const response = await askAssistant({ query: assistantQuery.trim() })
      setAssistantResult(response)
    } catch (requestError: unknown) {
      setAssistantError(requestError instanceof Error ? requestError.message : "Assistant request failed.")
    } finally {
      setAssistantLoading(false)
    }
  }

  const applyAssistantFilters = () => {
    if (!assistantResult) return
    const filters = assistantResult.filters

    setOffice(filters.office_names[0] || "")
    setDateFrom(filters.date_from || "")
    setDateTo(filters.date_to || "")
    setRunId(filters.run_id || "")
  }

  return (
    <section className="analytics-page">
      <header className="panel">
        <div className="panel-header">
          <div>
            <h3>Analytics dashboard</h3>
            <p className="muted">Track workload, sentiment, and assignment quality across offices.</p>
          </div>
          <div className="filter-grid inline-filters">
            <label>
              Run ID
              <input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="Optional" />
            </label>
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
        </div>
      </header>

      {loading ? <p className="muted">Loading analytics...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      <div className="charts-grid">
        <ChartCard
          title="Types by city"
          description="Distribution of ticket categories by city."
          data={chartData?.typeByCity || []}
          mode="bar"
        />
        <ChartCard
          title="Sentiment distribution"
          description="How incoming ticket tone is distributed."
          data={chartData?.sentiment || []}
          mode="pie"
        />
        <ChartCard
          title="Average priority by office"
          description="Operational urgency by office."
          data={chartData?.avgPriority || []}
          mode="bar"
        />
        <ChartCard
          title="Workload by manager"
          description="Current load across managers."
          data={chartData?.workload || []}
          mode="bar"
        />
      </div>

      <section className="panel assistant-panel">
        <div className="panel-header">
          <h3>AI Command Center</h3>
          <p className="muted">Ask natural-language analytics questions and turn answers into visuals.</p>
        </div>

        <div className="assistant-controls">
          <input
            value={assistantQuery}
            onChange={(event) => setAssistantQuery(event.target.value)}
            placeholder="Показать средний возраст клиентов по офисам Астана и Алматы"
          />
          <button className="primary" onClick={submitAssistant} disabled={assistantLoading}>
            {assistantLoading ? "Running..." : "Ask assistant"}
          </button>
        </div>

        {assistantError ? <p className="error-text">{assistantError}</p> : null}

        {assistantResult ? (
          <div className="assistant-result">
            <div className="panel-header">
              <div>
                <p className="muted">Intent: {assistantResult.intent}</p>
                <h4>{assistantResult.title}</h4>
              </div>
              <div className="panel-actions">
                <button className="ghost" onClick={() => setAssistantQuery(`${assistantQuery} по офису Астана`)}>
                  Refine query
                </button>
                <button className="ghost" onClick={applyAssistantFilters}>
                  Apply filters
                </button>
                <button className="ghost" onClick={() => pinChart(assistantResult)}>
                  Pin to dashboard
                </button>
              </div>
            </div>

            <p>{assistantResult.explanation}</p>

            <ChartCard
              title="Assistant chart"
              description={`Suggested ${assistantResult.chart_type} visualization`}
              data={normalizeAssistantSeries(assistantResult)}
              mode={assistantResult.chart_type === "pie" ? "pie" : assistantResult.chart_type === "line" ? "line" : "bar"}
            />

            <AssistantTable rows={assistantResult.table} />

            <div className="chips-wrap">
              {assistantResult.filters.office_names.map((name) => (
                <span key={`office-${name}`} className="chip">
                  office: {name}
                </span>
              ))}
              {assistantResult.filters.cities.map((name) => (
                <span key={`city-${name}`} className="chip">
                  city: {name}
                </span>
              ))}
              {assistantResult.filters.segment ? <span className="chip">segment: {assistantResult.filters.segment}</span> : null}
              {assistantResult.filters.language ? <span className="chip">lang: {assistantResult.filters.language}</span> : null}
              {assistantResult.filters.ticket_type ? (
                <span className="chip">type: {assistantResult.filters.ticket_type}</span>
              ) : null}
              {assistantResult.filters.date_from ? <span className="chip">from: {assistantResult.filters.date_from}</span> : null}
              {assistantResult.filters.date_to ? <span className="chip">to: {assistantResult.filters.date_to}</span> : null}
            </div>
          </div>
        ) : (
          <p className="muted">Ask a query to generate chart + table + explanation.</p>
        )}
      </section>

      <section className="panel">
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
              mode={chart.chart_type === "pie" ? "pie" : chart.chart_type === "line" ? "line" : "bar"}
            />
          ))}
        </div>
      </section>
    </section>
  )
}

export default AnalyticsPage
