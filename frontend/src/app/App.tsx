import { BrowserRouter, Route, Routes } from 'react-router-dom'
import AppShell from './AppShell'
import Dashboard from '../features/dashboard/Dashboard'
import TicketsPage from '../pages/TicketsPage'
import ManagersPage from '../pages/ManagersPage'
import BusinessUnitsPage from '../pages/BusinessUnitsPage'
import AnalyticsPage from '../pages/AnalyticsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/managers" element={<ManagersPage />} />
          <Route path="/business-units" element={<BusinessUnitsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
