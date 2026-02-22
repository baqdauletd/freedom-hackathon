import { useEffect, useMemo, useState } from "react"
import type { RouteResult, TicketDetailResponse } from "../api/contracts"
import { getResults, getTicketDetail } from "../api/routing"
import { useAppState } from "../state/AppStateContext"

type FilterState = {
  segment: string
  type: string
  tone: string
  language: string
  city: string
  office: string
  managerId: string
  search: string
}

const PAGE_SIZE = 25
const MANAGER_ID_PREFIX = "id:"
const MANAGER_NAME_PREFIX = "name:"

const initialFilters: FilterState = {
  segment: "",
  type: "",
  tone: "",
  language: "",
  city: "",
  office: "",
  managerId: "",
  search: "",
}

const toSortableString = (value: unknown) => {
  if (Array.isArray(value)) return value.join(",").toLowerCase()
  return String(value || "").toLowerCase()
}

const parseManagerFilter = (value: string): { managerId?: number; managerName?: string } => {
  if (!value) return {}

  if (value.startsWith(MANAGER_ID_PREFIX)) {
    const parsed = Number(value.slice(MANAGER_ID_PREFIX.length))
    return Number.isFinite(parsed) ? { managerId: parsed } : {}
  }

  if (value.startsWith(MANAGER_NAME_PREFIX)) {
    const managerName = value.slice(MANAGER_NAME_PREFIX.length).trim()
    return managerName ? { managerName } : {}
  }

  const parsed = Number(value)
  if (Number.isFinite(parsed)) return { managerId: parsed }

  return { managerName: value.trim() || undefined }
}

function ResultsPage() {
  const { latestRun } = useAppState()
  const runId = latestRun?.run_id || undefined

  const [filters, setFilters] = useState<FilterState>(initialFilters)
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [items, setItems] = useState<RouteResult[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [sortBy, setSortBy] = useState("created_at")
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [selected, setSelected] = useState<RouteResult | null>(null)
  const [detail, setDetail] = useState<TicketDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const usesLocalData = Boolean(latestRun?.results.length)

  const localFiltered = useMemo(() => {
    if (!usesLocalData || !latestRun) return []

    const matches = latestRun.results.filter((row) => {
      if (filters.segment && row.segment !== filters.segment) return false
      if (filters.type && row.ticket_type !== filters.type) return false
      if (filters.tone && row.sentiment !== filters.tone) return false
      if (filters.language && row.language !== filters.language) return false
      if (filters.city && (row.city || "") !== filters.city) return false
      if (filters.office && row.office !== filters.office) return false
      if (filters.managerId) {
        const { managerId, managerName } = parseManagerFilter(filters.managerId)
        if (managerId !== undefined && row.manager_id !== managerId) return false
        if (managerName && (row.assigned_manager || "") !== managerName) return false
      }
      if (dateFrom || dateTo) {
        const createdAt = row.created_at ? new Date(row.created_at) : null
        if (!createdAt || Number.isNaN(createdAt.getTime())) return false
        if (dateFrom && createdAt < new Date(`${dateFrom}T00:00:00`)) return false
        if (dateTo && createdAt > new Date(`${dateTo}T23:59:59`)) return false
      }
      if (filters.search) {
        const needle = filters.search.toLowerCase()
        const source = `${row.ticket_id} ${row.summary} ${row.description || ""}`.toLowerCase()
        if (!source.includes(needle)) return false
      }
      return true
    })

    const sorted = [...matches].sort((a, b) => {
      const left = a[sortBy as keyof RouteResult]
      const right = b[sortBy as keyof RouteResult]
      const comparison = toSortableString(left).localeCompare(toSortableString(right), undefined, {
        numeric: true,
      })
      return sortOrder === "asc" ? comparison : -comparison
    })

    return sorted
  }, [dateFrom, dateTo, filters, latestRun, sortBy, sortOrder, usesLocalData])

  useEffect(() => {
    if (usesLocalData) {
      setTotal(localFiltered.length)
      setItems(localFiltered.slice(offset, offset + PAGE_SIZE))
      return
    }

    if (!runId) {
      setItems([])
      setTotal(0)
      setLoading(false)
      setError("")
      return
    }

    let alive = true
    setLoading(true)
    setError("")

    const managerFilter = parseManagerFilter(filters.managerId)

    getResults({
      run_id: runId,
      office: filters.office || undefined,
      city: filters.city || undefined,
      type: filters.type || undefined,
      tone: filters.tone || undefined,
      language: filters.language || undefined,
      manager_id: managerFilter.managerId,
      manager: managerFilter.managerName,
      segment: filters.segment || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: filters.search || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      limit: PAGE_SIZE,
      offset,
    })
      .then((response) => {
        if (!alive) return
        const payload = response as { items?: RouteResult[]; total?: number }
        setItems(Array.isArray(payload.items) ? payload.items : [])
        setTotal(Number(payload.total || 0))
      })
      .catch((requestError: unknown) => {
        if (!alive) return
        setError(requestError instanceof Error ? requestError.message : "Failed to load results.")
      })
      .finally(() => {
        if (!alive) return
        setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [dateFrom, dateTo, filters, localFiltered, offset, runId, sortBy, sortOrder, usesLocalData])

  useEffect(() => {
    setOffset(0)
  }, [dateFrom, dateTo, filters, sortBy, sortOrder, runId])

  const options = useMemo(() => {
    const source = usesLocalData ? localFiltered : items
    const distinct = (values: string[]) =>
      Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b))
    const managerMap = new Map<string, { id: string; label: string }>()

    source.forEach((row) => {
      const managerName = (row.assigned_manager || "").trim()
      if (!managerName) return

      if (typeof row.manager_id === "number") {
        const key = `${MANAGER_ID_PREFIX}${row.manager_id}`
        if (!managerMap.has(key)) {
          managerMap.set(key, { id: key, label: `${managerName} (#${row.manager_id})` })
        }
        return
      }

      const key = `${MANAGER_NAME_PREFIX}${managerName}`
      if (!managerMap.has(key)) {
        managerMap.set(key, { id: key, label: managerName })
      }
    })

    return {
      segments: distinct(source.map((row) => row.segment || "")),
      types: distinct(source.map((row) => row.ticket_type)),
      tones: distinct(source.map((row) => row.sentiment)),
      languages: distinct(source.map((row) => row.language)),
      cities: distinct(source.map((row) => row.city || "")),
      offices: distinct(source.map((row) => row.office)),
      managers: Array.from(managerMap.values()).sort((a, b) => a.label.localeCompare(b.label)),
    }
  }, [items, localFiltered, usesLocalData])

  const hasActiveFilters = Boolean(
    filters.search ||
      filters.segment ||
      filters.type ||
      filters.tone ||
      filters.language ||
      filters.city ||
      filters.office ||
      filters.managerId ||
      dateFrom ||
      dateTo,
  )

  const clearFilters = () => {
    setFilters({ ...initialFilters })
    setDateFrom("")
    setDateTo("")
    setOffset(0)
  }

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const toggleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"))
      return
    }
    setSortBy(column)
    setSortOrder("asc")
  }

  const openTicket = async (row: RouteResult) => {
    setSelected(row)
    setDetail(null)
    if (typeof row.id !== "number") return

    setDetailLoading(true)
    try {
      const ticketDetail = await getTicketDetail(row.id)
      setDetail(ticketDetail as TicketDetailResponse)
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const summary = latestRun?.summary
  const assignmentStatus = detail?.assignment?.assignment_status || selected?.assignment_status || "assigned"
  const unassignedReason = detail?.assignment?.unassigned_reason || selected?.unassigned_reason || ""

  return (
    <section className="results-page">
      <header className="panel">
        <div className="panel-header">
          <div>
            <h3>Routing results</h3>
            <p className="muted">
              Review distribution outcomes, inspect assignment quality, and drill into each ticket.
            </p>
          </div>
          <div className="summary-grid">
            <div className="summary-stat">
              <span>Total</span>
              <strong>{summary?.total ?? total}</strong>
            </div>
            <div className="summary-stat">
              <span>Failures</span>
              <strong>{summary?.failed ?? Math.max(0, total - items.filter((row) => row.assigned_manager).length)}</strong>
            </div>
            <div className="summary-stat">
              <span>Avg ms/ticket</span>
              <strong>{summary?.avg_processing_ms ?? "-"}</strong>
            </div>
          </div>
        </div>
      </header>

      <section className="panel filters-panel">
        <div className="panel-header">
          <h3>Filters</h3>
          <button className="ghost" type="button" onClick={clearFilters} disabled={!hasActiveFilters}>
            Clear filters
          </button>
        </div>
        <div className="filter-grid">
          <label>
            Search
            <input
              value={filters.search}
              onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
              placeholder="GUID or description"
            />
          </label>
          <label>
            Segment
            <select
              value={filters.segment}
              onChange={(event) => setFilters((prev) => ({ ...prev, segment: event.target.value }))}
            >
              <option value="">All</option>
              {options.segments.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <select value={filters.type} onChange={(event) => setFilters((prev) => ({ ...prev, type: event.target.value }))}>
              <option value="">All</option>
              {options.types.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tone
            <select value={filters.tone} onChange={(event) => setFilters((prev) => ({ ...prev, tone: event.target.value }))}>
              <option value="">All</option>
              {options.tones.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Language
            <select
              value={filters.language}
              onChange={(event) => setFilters((prev) => ({ ...prev, language: event.target.value }))}
            >
              <option value="">All</option>
              {options.languages.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            City
            <select value={filters.city} onChange={(event) => setFilters((prev) => ({ ...prev, city: event.target.value }))}>
              <option value="">All</option>
              {options.cities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Office
            <select
              value={filters.office}
              onChange={(event) => setFilters((prev) => ({ ...prev, office: event.target.value }))}
            >
              <option value="">All</option>
              {options.offices.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Assigned manager
            <select
              value={filters.managerId}
              onChange={(event) => setFilters((prev) => ({ ...prev, managerId: event.target.value }))}
            >
              <option value="">All</option>
              {options.managers.map((manager) => (
                <option key={manager.id} value={manager.id}>
                  {manager.label}
                </option>
              ))}
            </select>
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
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>Tickets</h3>
          <p className="muted">
            Page {currentPage} of {totalPages}
          </p>
        </div>
        {loading ? <p className="muted">Loading results...</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        {!loading && !runId ? <p className="muted">Upload files first to view results for the latest run.</p> : null}
        {!loading && !!runId && !items.length ? <p className="muted">No results match your filters.</p> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <button className="sort-btn" onClick={() => toggleSort("ticket_id")}>
                    Ticket
                  </button>
                </th>
                <th>
                  <button className="sort-btn" onClick={() => toggleSort("ticket_type")}>
                    Type
                  </button>
                </th>
                <th>Tone</th>
                <th>
                  <button className="sort-btn" onClick={() => toggleSort("priority")}>
                    Priority
                  </button>
                </th>
                <th>Language</th>
                <th>Office</th>
                <th>Manager</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={`${row.id ?? row.ticket_index}-${row.ticket_id}`} onClick={() => openTicket(row)}>
                  <td>{row.ticket_id}</td>
                  <td>{row.ticket_type}</td>
                  <td>{row.sentiment}</td>
                  <td>{row.priority}</td>
                  <td>{row.language}</td>
                  <td>{row.office}</td>
                  <td>
                    {row.assigned_manager ||
                      (row.assignment_status === "unassigned"
                        ? `Unassigned (${row.unassigned_reason || "no_eligible_manager"})`
                        : "-")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <button className="ghost" onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))} disabled={offset === 0}>
            Previous
          </button>
          <button
            className="ghost"
            onClick={() => setOffset((prev) => (prev + PAGE_SIZE < total ? prev + PAGE_SIZE : prev))}
            disabled={offset + PAGE_SIZE >= total}
          >
            Next
          </button>
        </div>
      </section>

      {selected ? (
        <aside className="drawer-backdrop" role="dialog" aria-modal="true">
          <div className="drawer">
            <div className="panel-header">
              <h3>Ticket {selected.ticket_id}</h3>
              <button className="ghost" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
            {detailLoading ? <p className="muted">Loading details...</p> : null}
            <div className="detail-section">
              <h4>Original ticket</h4>
              <p className="muted">Segment: {detail?.ticket.segment || selected.segment || "-"}</p>
              <p className="muted">City: {detail?.ticket.city || selected.city || "-"}</p>
              <p>{detail?.ticket.description || selected.description || selected.summary}</p>
            </div>
            <div className="detail-section">
              <h4>AI analysis</h4>
              <p className="muted">Type: {detail?.ai_analysis?.ticket_type || selected.ticket_type}</p>
              <p className="muted">Tone: {detail?.ai_analysis?.tone || selected.sentiment}</p>
              <p className="muted">Priority: {detail?.ai_analysis?.priority || selected.priority}</p>
              <p className="muted">Language: {detail?.ai_analysis?.language || selected.language}</p>
              <p>{detail?.ai_analysis?.summary || selected.summary}</p>
              <p className="muted">{detail?.ai_analysis?.recommendation || selected.recommendation}</p>
            </div>
            <div className="detail-section">
              <h4>Geo</h4>
              <p className="muted">
                Ticket coords: {detail?.ai_analysis?.ticket_lat ?? selected.ticket_lat ?? "-"},{" "}
                {detail?.ai_analysis?.ticket_lon ?? selected.ticket_lon ?? "-"}
              </p>
              <p className="muted">
                Office coords: {detail?.assignment?.office_lat ?? selected.office_lat ?? "-"},{" "}
                {detail?.assignment?.office_lon ?? selected.office_lon ?? "-"}
              </p>
            </div>
            <div className="detail-section">
              <h4>Explain routing</h4>
              <p className="muted">Office: {detail?.assignment?.office || selected.office}</p>
              <p className="muted">
                Assigned manager: {detail?.assignment?.assigned_manager || selected.assigned_manager || "-"}
              </p>
              <p className="muted">
                Assignment status:{" "}
                {assignmentStatus}
              </p>
              {unassignedReason ? (
                <p className="muted">
                  Unassigned reason: {unassignedReason}
                </p>
              ) : null}
            </div>
          </div>
        </aside>
      ) : null}
    </section>
  )
}

export default ResultsPage
