// Mirrors streamlit_app/app.py's FEATURES["Government"] dict -- same section
// split (Operations vs Planning, by institutional mandate, see that file's
// comment), same feature labels and order. "Overview" per section is a
// React-only landing page (no Streamlit equivalent); everything else maps
// 1:1 to an existing govt_*.py feature module and backend route.

export type NavIconKey =
  | "overview"
  | "map"
  | "queue"
  | "verification"
  | "allocation"
  | "closures"
  | "timeline"
  | "analytics"
  | "briefing"
  | "vulnerability"
  | "trend"
  | "drain"
  | "exposure"
  | "scenario"
  | "pluvial"
  | "flood3d"
  | "assistant";

export interface NavItem {
  label: string;
  path: string;
  icon: NavIconKey;
}

export type SectionKey = "operations" | "planning";

export const SECTIONS: Record<SectionKey, { label: string; items: NavItem[] }> = {
  operations: {
    label: "Operations",
    items: [
      { label: "Overview", path: "/operations", icon: "overview" },
      { label: "Live Incident Map", path: "/operations/live-map", icon: "map" },
      { label: "Incoming Reports Queue", path: "/operations/reports-queue", icon: "queue" },
      { label: "Incident Verification", path: "/operations/verification", icon: "verification" },
      { label: "Emergency Resource Allocation", path: "/operations/resource-allocation", icon: "allocation" },
      { label: "Road Closure Recommendations", path: "/operations/road-closures", icon: "closures" },
      { label: "Flood/Incident Timeline", path: "/operations/timeline", icon: "timeline" },
      { label: "Analytics Dashboard", path: "/operations/analytics", icon: "analytics" },
      { label: "District Briefing Review", path: "/operations/briefing-review", icon: "briefing" },
    ],
  },
  planning: {
    label: "Planning",
    items: [
      { label: "Overview", path: "/planning", icon: "overview" },
      { label: "District Vulnerability Dashboard", path: "/planning/vulnerability", icon: "vulnerability" },
      { label: "Multi-Year Encroachment Trend", path: "/planning/encroachment-trend", icon: "trend" },
      { label: "Drain Maintenance Prioritization", path: "/planning/drain-priority", icon: "drain" },
      { label: "Population / Infrastructure Exposure", path: "/planning/exposure", icon: "exposure" },
      { label: "Before/After Scenario Simulator", path: "/planning/scenario-simulator", icon: "scenario" },
      { label: "Pluvial Flood Simulator", path: "/planning/pluvial-simulator", icon: "pluvial" },
      { label: "3D Flood View", path: "/planning/flood-3d", icon: "flood3d" },
    ],
  },
};

export const AI_ASSISTANT: NavItem = { label: "AI Assistant", path: "/ai-assistant", icon: "assistant" };
