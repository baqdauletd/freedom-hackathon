import React from "react";
import "./Layout.css";

export const Page: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <main className="page">{children}</main>
);
