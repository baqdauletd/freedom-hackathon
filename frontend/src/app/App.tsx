import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import UploadDashboard from "../features/ingest/UploadDashboard"
import AnalyticsPage from "../pages/AnalyticsPage"
import ResultsPage from "../pages/ResultsPage"
import { AppStateProvider } from "../state/AppStateContext"
import "./App.css"
import AppShell from "./AppShell"

function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to="/upload" replace />} />
            <Route path="/upload" element={<UploadDashboard />} />
            <Route path="/results" element={<ResultsPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="*" element={<Navigate to="/upload" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppStateProvider>
  )
}

export default App
