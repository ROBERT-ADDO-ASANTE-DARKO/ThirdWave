"""
map_tiles.py — shared base-tile-style picker for every Streamlit folium
map in the government dashboard, mirroring
citizen_app/lib/widgets/map_style_control.dart's Streets/Satellite/Dark/
Terrain picker: same Mapbox styles, same MAPBOX_API_KEY, read from the
repo-root .env (NOT backend/.env -- that one holds backend-only secrets
like OFFICER_API_KEY, see auth.py's docstring for the split). Folium's
own LayerControl renders the choice as an in-map radio picker, not a
Streamlit widget, so switching styles never triggers a Streamlit rerun
(no backend round-trip, no lost pan/zoom position) -- the same reason
the Flutter picker lives inside the map widget itself rather than a
separate settings screen.

override=True below is required, not a style choice: Streamlit's own
bootstrap (streamlit/web/bootstrap.py) runs
`os.environ.setdefault("MAPBOX_API_KEY", "")` on startup, before any
app code -- "prevent PyDeck from throwing when MAPBOX_API_KEY is
unset," for its own unrelated st.map()/PyDeck widgets. That pre-sets
the SAME env var name this module reuses to an empty string, so
load_dotenv()'s default (never override an already-present key) would
silently discard the real token from .env every time, with no error.
Confirmed by direct runtime inspection: mapbox_token() returned '' in
the live app despite the .env file parsing correctly in isolation.
"""

from __future__ import annotations

import os
from pathlib import Path

import folium
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Same style IDs and Mapbox Styles API URL pattern as
# citizen_app/lib/widgets/map_style_control.dart's tileLayerFor(). The
# default "Streets" layer is whatever tiles= the caller already passed
# to folium.Map(...) (OpenStreetMap, every page in this dashboard) --
# this module only adds the extra alternatives.
_MAPBOX_STYLES = [
    ("Satellite", "satellite-streets-v12"),
    ("Dark", "dark-v11"),
    ("Terrain", "outdoors-v12"),
]


def mapbox_token() -> str | None:
    return os.environ.get("MAPBOX_API_KEY")


def add_style_layers(m: folium.Map, token: str | None = None) -> None:
    """Adds Satellite/Dark/Terrain as selectable base layers alongside
    the map's existing default (Streets). Degrades to a no-op -- not an
    error -- when no Mapbox token is configured, same "the map still
    works with just Streets" rule the Flutter picker follows. Does NOT
    add a folium.LayerControl() itself: a page with its own overlay
    layers (e.g. govt_district_dashboard.py's SAR/DEM/WorldCover toggle)
    must add exactly one LayerControl after calling this, covering both
    the style layers and its own, or Leaflet renders two separate
    control widgets."""
    token = token or mapbox_token()
    if not token:
        return
    for name, style_id in _MAPBOX_STYLES:
        folium.TileLayer(
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/{style_id}/tiles/256/{{z}}/{{x}}/{{y}}@2x?access_token={token}",
            attr="Mapbox", name=name, overlay=False, control=True,
        ).add_to(m)
