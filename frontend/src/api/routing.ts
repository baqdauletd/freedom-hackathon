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
    let body: unknown = null
    let text = ""
    const messages: string[] = []

    if (contentType.includes("application/json")) {
      body = await response.json().catch(() => null)
      if (body && typeof body === "object") {
        const detail = (body as { detail?: unknown }).detail
        if (typeof detail === "string") {
          messages.push(detail)
        } else if (Array.isArray(detail)) {
          detail.forEach((item) => {
            if (typeof item === "string") {
              messages.push(item)
            } else if (item && typeof item === "object") {
              const msg = (item as { msg?: unknown }).msg
              if (typeof msg === "string") messages.push(msg)
            }
          })
        }
        const fallbackMessage = (body as { message?: unknown }).message
        if (typeof fallbackMessage === "string") messages.push(fallbackMessage)
      }
    } else {
      text = await response.text()
      if (text.trim()) messages.push(text.trim())
    }

    if (!messages.length) {
      const statusLabel = `${response.status} ${response.statusText}`.trim()
      messages.push(statusLabel || "Upload failed")
    }

    throw new ApiError(messages.join("\n"), response.status, { details: body ?? text, messages })
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
