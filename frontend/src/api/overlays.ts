import { backendAsset } from "./client";
import type { OverlayManifest } from "./types";

// Returns null if the manifest is missing or unreachable -- mirrors
// streamlit_app/features/govt_district_dashboard.py's load_overlay_manifest(),
// where "no overlays yet" is a normal, silently-handled state, not an error.
export async function fetchOverlayManifest(): Promise<OverlayManifest | null> {
  try {
    const res = await fetch(backendAsset("/overlays/manifest.json")!);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
