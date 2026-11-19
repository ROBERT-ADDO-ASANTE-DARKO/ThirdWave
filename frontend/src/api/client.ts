import axios from "axios";

// Same-origin /api, proxied to the FastAPI backend by vite.config.ts in dev
// (which attaches X-Officer-Key server-side -- see that file's comment).
// The browser never holds the officer key.
export const api = axios.create({ baseURL: "/api", timeout: 10_000 });

// Uploaded photos are served from backend/main.py's StaticFiles mounts
// (/uploads, /evidence) directly on the backend origin, not under /api --
// those routes aren't officer-gated, so there's nothing to proxy for
// secrecy, same reasoning as the Mapbox token. CORS on the backend is
// wide open (allow_origins=["*"]), same dev-prototype assumption
// streamlit_app/features/govt_incident_map.py's BACKEND_URL fallback makes.
const BACKEND_ORIGIN = "http://localhost:8000";

export function backendAsset(path: string | null): string | null {
  return path ? `${BACKEND_ORIGIN}${path}` : null;
}
