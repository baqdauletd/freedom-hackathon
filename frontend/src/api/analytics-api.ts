import { apiClient } from "./client"
import type {
  AnalyticsSummaryResponse,
  AssistantQueryRequest,
  AssistantQueryResponse,
} from "./contracts"

export const getAnalyticsSummary = async (query?: {
  run_id?: string
  office?: string
  office_id?: number
  date_from?: string
  date_to?: string
}) =>
  apiClient.request<AnalyticsSummaryResponse>({
    method: "GET",
    path: "/analytics/summary",
    query,
  })

export const askAssistant = async (payload: AssistantQueryRequest) =>
  apiClient.request<AssistantQueryResponse, AssistantQueryRequest>({
    method: "POST",
    path: "/assistant/query",
    body: payload,
  })
