import React from "react";
import "./Layout.css";

export const Topbar: React.FC = () => (
  <header className="topbar">
    <div>
      <strong>AI Ticket Routing</strong>
    </div>
    <div>Processing SLA: 10s</div>
  </header>
);
