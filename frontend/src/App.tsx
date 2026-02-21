import React from "react";
import { Dashboard } from "./components/Dashboard";
import { AppShell } from "./components/layout/AppShell";
import { DashboardProvider } from "./state/dashboardStore";

export const App: React.FC = () => (
  <DashboardProvider>
    <AppShell>
      <Dashboard />
    </AppShell>
  </DashboardProvider>
);
