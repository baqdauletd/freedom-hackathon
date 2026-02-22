import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { AssistantResponse, AssistantResultResponse } from "../../api/contracts"
import * as analyticsApi from "../../api/analytics-api"
import AnalyticsPage from "../AnalyticsPage"
import { AppStateProvider } from "../../state/AppStateContext"

vi.mock("../../api/analytics-api", () => ({
  getAnalyticsSummary: vi.fn(),
  askAssistant: vi.fn(),
}))

const mockedGetAnalyticsSummary = vi.mocked(analyticsApi.getAnalyticsSummary)
const mockedAskAssistant = vi.mocked(analyticsApi.askAssistant)

const defaultSummary = {
  ticket_types_by_city: [{ city: "Астана", ticket_type: "Жалоба", count: 2 }],
  tickets_by_office: [{ office: "Астана", count: 2 }],
  sentiment_distribution: [{ tone: "Нейтральный", count: 2 }],
  avg_priority_by_office: [{ office: "Астана", avg_priority: 5 }],
  avg_priority_by_city: [{ city: "Астана", avg_priority: 5 }],
  workload_by_manager: [],
}

const baseFilters = {
  office_names: [],
  office_ids: [],
  cities: [],
  date_from: null,
  date_to: null,
  segment: null,
  ticket_type: null,
  language: null,
  run_id: "11111111-1111-4111-8111-111111111111",
}

const renderPage = () =>
  render(
    <AppStateProvider>
      <AnalyticsPage />
    </AppStateProvider>,
  )

const submitAssistantQuery = async (query: string) => {
  const input = screen.getByPlaceholderText("Ask: Show unassigned rate and reasons in Astana")
  fireEvent.change(input, { target: { value: query } })
  fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }))
  await waitFor(() => expect(mockedAskAssistant).toHaveBeenCalled())
}

describe("AnalyticsPage assistant", () => {
  beforeEach(() => {
    mockedGetAnalyticsSummary.mockResolvedValue(defaultSummary)
    mockedAskAssistant.mockReset()
    window.localStorage.setItem(
      "fire_latest_run_meta_v1",
      JSON.stringify({
        run_id: "11111111-1111-4111-8111-111111111111",
        summary: {
          total: 3,
          success: 3,
          failed: 0,
          avg_processing_ms: 1000,
          elapsed_ms: 3000,
        },
        results: [],
      }),
    )
  })

  it("renders clarification options", async () => {
    const response: AssistantResponse = {
      kind: "clarification",
      title: "Please clarify your analytics request",
      explanation: "Choose a specific metric.",
      options: [
        {
          intent: "ticket_type_distribution",
          label: "Ticket type distribution",
          query_hint: "Show ticket type distribution",
        },
      ],
      filters: baseFilters,
      scope_applied: {
        run_id: "11111111-1111-4111-8111-111111111111",
      },
      warnings: [],
    }
    mockedAskAssistant.mockResolvedValue(response)

    renderPage()
    await submitAssistantQuery("покажи статистику")

    expect(await screen.findByText("Choose a specific metric.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Ticket type distribution" })).toBeInTheDocument()
  })

  it("renders assistant chart, table, explanation, and offline badge", async () => {
    const response: AssistantResultResponse = {
      kind: "result",
      intent: "unassigned_rate_and_reasons",
      title: "Unassigned rate and reasons",
      chart_type: "bar",
      data: {
        labels: ["Assigned", "Unassigned"],
        values: [2, 1],
      },
      table: [
        { bucket: "Assigned", count: 2 },
        { bucket: "Unassigned", count: 1 },
      ],
      explanation: "Assigned vs unassigned share and reason breakdown.",
      filters: {
        ...baseFilters,
        office_names: ["Астана"],
      },
      used_fallback: true,
      cache_hit: false,
      warnings: [],
      computed_from: "assignments join tickets join ai_analysis join business_units",
      scope_applied: {
        run_id: "11111111-1111-4111-8111-111111111111",
        office: "Астана",
      },
    }
    mockedAskAssistant.mockResolvedValue(response)

    renderPage()
    await submitAssistantQuery("show unassigned rate")

    expect(await screen.findByText("Assigned vs unassigned share and reason breakdown.")).toBeInTheDocument()
    expect(screen.getByText("Using offline mode")).toBeInTheDocument()
    expect(screen.getByText("Assigned")).toBeInTheDocument()
    expect(screen.getByText("Unassigned")).toBeInTheDocument()
  })

  it("supports apply filters and pin to dashboard actions", async () => {
    const response: AssistantResultResponse = {
      kind: "result",
      intent: "ticket_type_distribution",
      title: "Ticket type distribution",
      chart_type: "donut",
      data: {
        labels: ["Жалоба"],
        values: [2],
      },
      table: [{ ticket_type: "Жалоба", count: 2 }],
      explanation: "Type split for selected scope.",
      filters: {
        ...baseFilters,
        office_names: ["Астана"],
      },
      used_fallback: false,
      cache_hit: false,
      warnings: [],
      computed_from: "ai_analysis join tickets join assignments join business_units",
      scope_applied: {
        run_id: "11111111-1111-4111-8111-111111111111",
      },
    }
    mockedAskAssistant.mockResolvedValue(response)

    renderPage()
    await submitAssistantQuery("type distribution")

    fireEvent.click(await screen.findByRole("button", { name: "Apply filters to scope" }))
    expect(screen.getByLabelText("Office")).toHaveValue("Астана")

    fireEvent.click(screen.getByRole("button", { name: "Pin to dashboard" }))
    await waitFor(() => expect(screen.getAllByText("Ticket type distribution").length).toBeGreaterThan(1))
  })
})
