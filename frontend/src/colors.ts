import type { Level } from "./api/types";

// Same values as theme.css's --level-* custom properties, duplicated as
// raw hex because Leaflet writes these directly into SVG stroke/fill
// presentation attributes, where CSS var() support is unreliable --
// unlike theme.css, which plain DOM/CSS consumes directly.
export const LEVEL_HEX: Record<Level, string> = {
  Low: "#1E8A4C",
  Moderate: "#B8860B",
  High: "#C1621B",
  "Very High": "#B0241D",
};

export const INK_NAVY = "#0B2545";
export const STEEL_BLUE = "#1E4E6B";
export const SIGNAL_TEAL = "#1B7A9E";

// Confidence (report evidence strength) gets its own palette, deliberately
// NOT LEVEL_HEX -- "how much evidence backs this one report" and "how
// flood-prone this area is in general" are different axes; reusing the
// Low/Moderate/High/Very High colors would blur them. Same choice
// streamlit_app/features/govt_reports_queue.py makes (CONFIDENCE_COLOR).
export const CONFIDENCE_COLOR: Record<string, string> = {
  Weak: "#6B7280",
  "Some corroboration": STEEL_BLUE,
  "Well-corroborated": SIGNAL_TEAL,
  "Strongly corroborated": INK_NAVY,
};

export const LEVEL_RANK: Record<Level, number> = { "Very High": 3, High: 2, Moderate: 1, Low: 0 };

export function worstLevel(levels: (Level | null | undefined)[]): Level | null {
  const present = levels.filter((lv): lv is Level => !!lv);
  if (present.length === 0) return null;
  return present.reduce((worst, lv) => (LEVEL_RANK[lv] > LEVEL_RANK[worst] ? lv : worst));
}
