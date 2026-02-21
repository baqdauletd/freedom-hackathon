/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useState } from "react"
import type { PropsWithChildren } from "react"
import type { AssistantQueryResponse, RoutingRunEnvelope } from "../api/contracts"

type AppStateValue = {
  latestRun: RoutingRunEnvelope | null
  setLatestRun: (value: RoutingRunEnvelope | null) => void
  pinnedCharts: AssistantQueryResponse[]
  pinChart: (value: AssistantQueryResponse) => void
  clearPinnedCharts: () => void
}

const AppStateContext = createContext<AppStateValue | undefined>(undefined)

const LATEST_RUN_STORAGE_KEY = "fire_latest_run_meta_v1"
const EMPTY_SUMMARY: RoutingRunEnvelope["summary"] = {
  total: 0,
  success: 0,
  failed: 0,
  avg_processing_ms: 0,
  elapsed_ms: 0,
}

const normalizeLatestRun = (value: unknown): RoutingRunEnvelope | null => {
  if (!value || typeof value !== "object") return null
  const parsed = value as Partial<RoutingRunEnvelope>
  const runId = typeof parsed.run_id === "string" && parsed.run_id.trim() ? parsed.run_id.trim() : null
  if (!runId) return null
  return {
    run_id: runId,
    summary: parsed.summary || EMPTY_SUMMARY,
    results: Array.isArray(parsed.results) ? parsed.results : [],
  }
}

const readLatestRun = (): RoutingRunEnvelope | null => {
  if (typeof window === "undefined") return null

  const raw = window.localStorage.getItem(LATEST_RUN_STORAGE_KEY)
  if (!raw) return null

  try {
    return normalizeLatestRun(JSON.parse(raw))
  } catch {
    return null
  }
}

const persistLatestRun = (value: RoutingRunEnvelope | null) => {
  if (typeof window === "undefined") return
  try {
    if (!value?.run_id) {
      window.localStorage.removeItem(LATEST_RUN_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(
      LATEST_RUN_STORAGE_KEY,
      JSON.stringify({
        run_id: value.run_id,
        summary: value.summary || EMPTY_SUMMARY,
        results: Array.isArray(value.results) ? value.results : [],
      }),
    )
  } catch {
    // Ignore storage failures (quota/private mode) and keep in-memory state.
  }
}

export function AppStateProvider({ children }: PropsWithChildren) {
  const [latestRunState, setLatestRunState] = useState<RoutingRunEnvelope | null>(() => readLatestRun())
  const [pinnedCharts, setPinnedCharts] = useState<AssistantQueryResponse[]>([])

  const setLatestRun = useCallback((value: RoutingRunEnvelope | null) => {
    setLatestRunState(value)
    persistLatestRun(value)
  }, [])

  const pinChart = useCallback((chart: AssistantQueryResponse) => {
    setPinnedCharts((prev) => [chart, ...prev].slice(0, 6))
  }, [])

  const clearPinnedCharts = useCallback(() => {
    setPinnedCharts([])
  }, [])

  const value = useMemo<AppStateValue>(
    () => ({
      latestRun: latestRunState,
      setLatestRun,
      pinnedCharts,
      pinChart,
      clearPinnedCharts,
    }),
    [clearPinnedCharts, latestRunState, pinChart, pinnedCharts, setLatestRun],
  )

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState() {
  const context = useContext(AppStateContext)
  if (!context) {
    throw new Error("useAppState must be used within AppStateProvider")
  }
  return context
}
