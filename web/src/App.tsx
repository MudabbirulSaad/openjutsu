import { useQueryClient } from "@tanstack/react-query";
import { Folder, Layers, Settings2, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";

import { Projects } from "./Projects";
import { Settings } from "./Settings";
import { Studio } from "./Studio";
function Theme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "system",
  );
  useEffect(() => {
    const q = matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      (document.documentElement.dataset.theme =
        theme === "system" ? (q.matches ? "dark" : "light") : theme);
    apply();
    q.addEventListener("change", apply);
    localStorage.setItem("theme", theme);
    return () => q.removeEventListener("change", apply);
  }, [theme]);
  return (
    <select
      aria-label="Color theme"
      className="theme-select"
      value={theme}
      onChange={(e) => setTheme(e.target.value)}
    >
      <option value="system">System theme</option>
      <option value="light">Light theme</option>
      <option value="dark">Dark theme</option>
    </select>
  );
}
export function App() {
  const client = useQueryClient();
  const [connected, setConnected] = useState(true);
  useEffect(() => {
    const events = new EventSource("/api/events");
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.onmessage = () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["job"] });
    };
    return () => events.close();
  }, [client]);
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand" aria-label="OpenJutsu projects">
          <Layers size={23} />
          <span>OpenJutsu</span>
          <span className="alpha">alpha</span>
        </Link>
        <nav aria-label="Main navigation">
          <NavLink to="/" end>
            <Folder size={16} />
            Projects
          </NavLink>
          <NavLink to="/recipes">
            <Layers size={16} />
            Recipes
          </NavLink>
          <NavLink to="/settings">
            <Settings2 size={16} />
            Settings
          </NavLink>
        </nav>
        <div className="header-right">
          {!connected && (
            <span className="connection" role="status">
              <WifiOff size={15} />
              Reconnecting
            </span>
          )}
          <Theme />
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/recipes" element={<Projects recipes />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="/studio/:id/:stage"
          element={<Studio connected={connected} />}
        />
        <Route
          path="*"
          element={
            <p className="page">
              <Link to="/">Return to projects</Link>
            </p>
          }
        />
      </Routes>
    </div>
  );
}
