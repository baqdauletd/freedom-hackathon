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
  assignment_status?: string | null
  unassigned_reason?: string | null
  warnings?: string[]
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

export type RunListItem = {
  run_id: string
  status: string
  created_at: string | null
  summary: RunSummary
  source_files: {
    tickets?: string | null
    managers?: string | null
    business_units?: string | null
  }
}

export type RunsListResponse = {
  items: RunListItem[]
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
    assignment_status?: string | null
    unassigned_reason?: string | null
    selected_managers: string[]
    rr_turn: number
    decision_trace?: Record<string, unknown> | null
    warnings?: string[]
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
  run_id?: string
  office?: string
  date_from?: string
  date_to?: string
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

export type AssistantScopeApplied = {
  run_id?: string | null
  office?: string | null
  date_from?: string | null
  date_to?: string | null
}

export type AssistantClarificationOption = {
  intent: string
  label: string
  query_hint: string
}

export type AssistantResultResponse = {
  kind: "result"
  intent: string
  title: string
  chart_type: "bar" | "line" | "pie" | "donut" | "table" | "empty"
  data: {
    labels: string[]
    values: number[]
    [key: string]: unknown
  }
  table: Array<Record<string, unknown>>
  explanation: string
  filters: AssistantFilters
  computed_from?: string | null
  scope_applied?: AssistantScopeApplied
  warnings?: string[]
  used_fallback?: boolean
  cache_hit?: boolean
}

export type AssistantClarificationResponse = {
  kind: "clarification"
  title: string
  explanation: string
  options: AssistantClarificationOption[]
  filters: AssistantFilters
  scope_applied?: AssistantScopeApplied
  warnings?: string[]
}

export type AssistantResponse = AssistantResultResponse | AssistantClarificationResponse
