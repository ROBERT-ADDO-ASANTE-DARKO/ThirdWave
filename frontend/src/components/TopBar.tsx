import type { ReactNode } from "react";
import { BellIcon, SearchIcon } from "./icons";
import "./TopBar.css";

interface SearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

interface TopBarProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  // Opt-in and page-owned: search filters whatever that page already has
  // loaded (see Reports Queue), never navigates elsewhere or queries the
  // backend on its own. Omitted entirely -- not shown disabled -- on a
  // page that doesn't implement filtering yet, so there's never a search
  // box that looks live but does nothing.
  search?: SearchProps;
}

export function TopBar({ title, subtitle, actions, search }: TopBarProps) {
  return (
    <header className="topbar">
      <div>
        <h1 className="topbar-title">{title}</h1>
        {subtitle && <p className="topbar-subtitle">{subtitle}</p>}
      </div>
      <div className="topbar-actions">
        {actions}
        {search && (
          <label className="topbar-search">
            <span className="topbar-search-icon">
              <SearchIcon />
            </span>
            <input
              type="search"
              placeholder={search.placeholder ?? "Search…"}
              aria-label="Search"
              value={search.value}
              onChange={(e) => search.onChange(e.target.value)}
            />
          </label>
        )}
        <button type="button" aria-label="Notifications" className="topbar-bell">
          <BellIcon />
          <span className="topbar-bell-dot" />
        </button>
      </div>
    </header>
  );
}
