/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, useState } from "react"
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

export function AppStateProvider({ children }: PropsWithChildren) {
  const [latestRun, setLatestRun] = useState<RoutingRunEnvelope | null>(null)
  const [pinnedCharts, setPinnedCharts] = useState<AssistantQueryResponse[]>([])

  const value = useMemo<AppStateValue>(
    () => ({
      latestRun,
      setLatestRun,
      pinnedCharts,
      pinChart: (chart) => {
        setPinnedCharts((prev) => [chart, ...prev].slice(0, 6))
      },
      clearPinnedCharts: () => setPinnedCharts([]),
    }),
    [latestRun, pinnedCharts],
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
