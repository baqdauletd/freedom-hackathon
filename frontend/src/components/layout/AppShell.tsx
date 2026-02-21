import React from "react";
import { SideBar } from "./SideBar";
import { Topbar } from "./Topbar";
import { Page } from "./Page";
import "./Layout.css";

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="shell">
    <SideBar />
    <Page>
      <Topbar />
      {children}
    </Page>
  </div>
);
