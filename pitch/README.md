# ThirdWave pitch materials

- `ThirdWave_Field_Report.pptx` — editable slide deck for the team (9 slides).
- `pitch.html` — source for the published web version (Claude Artifact:
  https://claude.ai/code/artifact/996b7598-2785-46f4-bf01-d62452a935e7). Not
  self-contained on its own -- `assets/images_snippet.js` (the base64 image
  payload) gets spliced into the `/*__IMAGES_PLACEHOLDER__*/` marker before
  publishing.
- `build_pptx.py` — regenerates the .pptx from the images in `assets/`.
  Run with `python3 build_pptx.py` from this directory (needs `python-pptx`).
- `assets/` — the real plates and screenshots both versions embed:
  - `plate_sar.png`, `plate_dem.png`, `plate_worldcover.png` — Sentinel-1 /
    Copernicus DEM / ESA WorldCover, exported by
    `risk_engine/export_raster_overlays.py`.
  - `diagram_plate.png` — architecture diagram, captured from the rendered
    HTML page's inline SVG.
  - `01_dashboard.png`, `02_dashboard_dem.png`, `03_pluvial.png`,
    `04_pluvial_circle.png`, `05_flood3d.png`, `07_ai_assistant_chat.png` —
    live screenshots of the Streamlit app.
  - `vlm_plate.png` — the crowdsourced-report VLM annotation in action.
    Demo photo used for this one is NOT a real pilot-district submission:
    a flooded street in Lagos, 2013 (Elgabarty2002, CC BY-SA 4.0, via
    Wikimedia Commons) — chosen because this project's own research-only
    photos (`risk_engine/data/Flooding_Accra_6.jpg` etc.) are explicitly
    marked not for redistribution.
  - `images_snippet.js` — all of the above, base64-encoded, as the
    `window.IMAGES = {...}` payload the HTML page loads.
