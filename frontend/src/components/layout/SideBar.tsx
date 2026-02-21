import React from "react";
import "./Layout.css";

export const SideBar: React.FC = () => (
  <aside className="sidebar">
    <div>
      <h2>Freedom Support</h2>
      <p>Night Ops Dashboard</p>
    </div>
    <nav className="sidebar__nav">
      <span className="sidebar__item">Tickets</span>
      <span className="sidebar__item">Managers</span>
      <span className="sidebar__item">Offices</span>
      <span className="sidebar__item">AI Explain</span>
    </nav>
  </aside>
);
