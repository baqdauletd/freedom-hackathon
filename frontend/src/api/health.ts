import { apiClient } from "./client"

export type HealthResponse = {
  status: string
  app_instance_id?: string
  started_at?: string
}

export const getHealth = async () =>
  apiClient.request<HealthResponse>({
    method: "GET",
    path: "/health",
  })

