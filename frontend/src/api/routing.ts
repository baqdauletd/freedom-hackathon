import { ApiError, apiClient } from "./client"
import type { RouteResult, RoutingRunEnvelope } from "./contracts"
import { toApiUrl } from "./config"

const buildFallbackSummary = (results: RouteResult[]): RoutingRunEnvelope["summary"] => {
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
    elapsed_ms: 0,
  }
}

export const normalizeRoutingEnvelope = (payload: unknown): RoutingRunEnvelope => {
  if (Array.isArray(payload)) {
    const results = payload as RouteResult[]
    return {
      run_id: null,
      summary: buildFallbackSummary(results),
      results,
    }
  }

  if (payload && typeof payload === "object") {
    const envelope = payload as Partial<RoutingRunEnvelope>
    const results = Array.isArray(envelope.results) ? envelope.results : []
    return {
      run_id: envelope.run_id ?? null,
      summary: envelope.summary ?? buildFallbackSummary(results),
      results,
    }
  }

  throw new ApiError("Unexpected response format", 500)
}

export const uploadAndRoute = async (files: {
  tickets: File
  managers: File
  business_units: File
}): Promise<RoutingRunEnvelope> => {
  const form = new FormData()
  form.append("tickets", files.tickets)
  form.append("managers", files.managers)
  form.append("business_units", files.business_units)

  const response = await fetch(toApiUrl("/route/upload"), {
    method: "POST",
    body: form,
  })

  if (!response.ok) {
    const contentType = response.headers.get("Content-Type") || ""
    if (contentType.includes("application/json")) {
      const body = await response.json().catch(() => ({}))
      const message = typeof body?.detail === "string" ? body.detail : response.statusText
      throw new ApiError(message || "Upload failed", response.status, { details: body })
    }
    const text = await response.text()
    throw new ApiError(text || "Upload failed", response.status)
  }

  const data = await response.json()
  return normalizeRoutingEnvelope(data)
}

type ResultsQuery = {
  run_id?: string
  office?: string
  office_id?: number
  city?: string
  type?: string
  tone?: string
  language?: string
  manager_id?: number
  manager?: string
  segment?: string
  date_from?: string
  date_to?: string
  search?: string
  sort_by?: string
  sort_order?: "asc" | "desc"
  limit?: number
  offset?: number
}

export const getResults = async (query: ResultsQuery) =>
  apiClient.request({
    method: "GET",
    path: "/results",
    query,
  })

export const getTicketDetail = async (ticketId: string | number) =>
  apiClient.request({
    method: "GET",
    path: `/tickets/${ticketId}`,
  })

export const getManagers = async (query?: {
  run_id?: string
  office?: string
  office_id?: number
  date_from?: string
  date_to?: string
}) =>
  apiClient.request({
    method: "GET",
    path: "/managers",
    query,
  })

export const getRuns = async (query?: {
  limit?: number
  offset?: number
  status?: string
}) =>
  apiClient.request({
    method: "GET",
    path: "/runs",
    query,
  })
