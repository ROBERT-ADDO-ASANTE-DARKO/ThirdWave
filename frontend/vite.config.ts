import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import dotenv from "dotenv";
import { defineConfig } from "vite";

// The officer API key (backend/.env's OFFICER_API_KEY) must never reach the
// browser bundle -- it's a single shared secret, not a per-user token (see
// backend/auth.py's docstring). Streamlit could read it directly because it
// runs as a trusted server process; this dev proxy gives the React app the
// same trust boundary: Vite's Node process reads the key and attaches it to
// proxied /api/* requests, so the browser only ever talks to same-origin
// /api and never sees the secret. A real deployment would need an
// equivalent small server-side proxy in front of the backend -- this is
// that proxy's dev-time stand-in, not a shortcut to remove later.
const backendEnv = dotenv.config({ path: fileURLToPath(new URL("../backend/.env", import.meta.url)) }).parsed ?? {};
const rootEnv = dotenv.config({ path: fileURLToPath(new URL("../.env", import.meta.url)) }).parsed ?? {};

const officerKey = backendEnv.OFFICER_API_KEY;
// Mapbox tokens ARE meant for client-side use (unlike the officer key) --
// same token streamlit_app/map_tiles.py and citizen_app's style picker use,
// just exposed to the browser bundle here instead of read server-side.
const mapboxToken = rootEnv.MAPBOX_API_KEY;

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_MAPBOX_TOKEN": JSON.stringify(mapboxToken ?? ""),
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            if (officerKey) proxyReq.setHeader("X-Officer-Key", officerKey);
          });
        },
      },
    },
  },
});
