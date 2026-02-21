export type RouteResult = {
  id?: number
  run_id?: string
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
  manager_id?: number | null
  assigned_manager: string | null
  ticket_lat?: number | null
  ticket_lon?: number | null
  office_lat?: number | null
  office_lon?: number | null
  processing_ms?: number | null
  segment?: string | null
  city?: string | null
  description?: string | null
  created_at?: string | null
}

export type RunSummary = {
  total: number
  success: number
  failed: number
  avg_processing_ms: number
  elapsed_ms: number
}

export type RoutingRunEnvelope = {
  run_id: string | null
  summary: RunSummary
  results: RouteResult[]
}

export type ResultsListResponse = {
  items: RouteResult[]
  total: number
  limit: number
  offset: number
}

export type TicketDetailResponse = {
  id: number
  run_id?: string | null
  ticket: {
    external_id: string
    segment: string
    description: string
    country: string | null
    region: string | null
    city: string | null
    street: string | null
    house: string | null
    created_at: string | null
  }
  ai_analysis: {
    ticket_type: string
    tone: string
    priority: number
    language: string
    summary: string
    recommendation: string
    ticket_lat: number | null
    ticket_lon: number | null
    processing_ms: number | null
  } | null
  assignment: {
    office: string
    office_lat: number | null
    office_lon: number | null
    manager_id?: number | null
    assigned_manager: string | null
    selected_managers: string[]
    rr_turn: number
    decision_trace?: Record<string, unknown> | null
  } | null
}

export type ManagerListItem = {
  id: number
  full_name: string
  position: string
  skills: string[]
  office: string
  current_load: number
  assigned_count: number
}

export type ManagerListResponse = {
  items: ManagerListItem[]
}

export type AnalyticsSummaryResponse = {
  ticket_types_by_city: Array<{ city: string; ticket_type: string; count: number }>
  tickets_by_office: Array<{ office: string; count: number }>
  sentiment_distribution: Array<{ tone: string; count: number }>
  avg_priority_by_office: Array<{ office: string; avg_priority: number }>
  avg_priority_by_city: Array<{ city: string; avg_priority: number }>
  workload_by_manager: Array<{
    manager_id: number
    manager: string
    manager_name: string
    office: string
    current_load: number
    assigned_ticket_count: number
    assigned_count: number
  }>
}

export type AssistantQueryRequest = {
  query: string
}

export type AssistantFilters = {
  office_names: string[]
  office_ids?: number[]
  cities: string[]
  date_from?: string | null
  date_to?: string | null
  segment?: "Mass" | "VIP" | "Priority" | null
  ticket_type?: string | null
  language?: "KZ" | "ENG" | "RU" | null
  run_id?: string | null
}

export type AssistantQueryResponse = {
  intent: string
  title: string
  chart_type: "bar" | "line" | "pie" | "table"
  data: {
    labels: string[]
    values: number[]
  }
  table: Array<Record<string, unknown>>
  explanation: string
  filters: AssistantFilters
}
