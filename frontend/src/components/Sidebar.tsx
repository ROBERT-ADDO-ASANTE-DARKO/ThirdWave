import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { AI_ASSISTANT, SECTIONS, type SectionKey } from "../nav";
import { LogoMark, NavIcon } from "./icons";
import "./Sidebar.css";

// A path belongs to "planning" if it starts with /planning, otherwise it's
// "operations" (including the AI Assistant route, which isn't part of
// either section's own list but should still keep whichever tab is active).
function sectionFromPath(pathname: string): SectionKey {
  return pathname.startsWith("/planning") ? "planning" : "operations";
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeSection = sectionFromPath(location.pathname);

  return (
    <nav aria-label="Primary" className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">
          <LogoMark />
        </div>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">ThirdWave</span>
          <span className="sidebar-brand-tag">GOVERNMENT</span>
        </div>
      </div>

      <div className="sidebar-toggle" role="tablist" aria-label="Section">
        {(Object.keys(SECTIONS) as SectionKey[]).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={activeSection === key}
            className={`sidebar-toggle-btn ${activeSection === key ? "is-active" : ""}`}
            onClick={() => navigate(SECTIONS[key].items[0].path)}
          >
            {SECTIONS[key].label}
          </button>
        ))}
      </div>

      <div className="sidebar-group">
        <span className="sidebar-group-label">{SECTIONS[activeSection].label.toUpperCase()}</span>
        {SECTIONS[activeSection].items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end
            className={({ isActive }) => `sidebar-link ${isActive ? "is-active" : ""}`}
          >
            {({ isActive }) => (
              <>
                <NavIcon icon={item.icon} color={isActive ? "#5FC9E8" : undefined} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </div>

      <div className="sidebar-group sidebar-group-tail">
        <NavLink to={AI_ASSISTANT.path} className={({ isActive }) => `sidebar-link ${isActive ? "is-active" : ""}`}>
          {({ isActive }) => (
            <>
              <NavIcon icon={AI_ASSISTANT.icon} color={isActive ? "#5FC9E8" : undefined} />
              {AI_ASSISTANT.label}
            </>
          )}
        </NavLink>
      </div>

      <div className="sidebar-identity">
        <div className="sidebar-identity-avatar">KA</div>
        <div className="sidebar-identity-text">
          <span className="sidebar-identity-name">K. Asante</span>
          <span className="sidebar-identity-role">Weija Gbawe NADMO</span>
        </div>
      </div>
    </nav>
  );
}
