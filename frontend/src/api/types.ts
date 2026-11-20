// Mirrors backend/serializers.py's serialize_report() and
// backend/clustering.py's cluster_reports() output shapes 1:1.

export type HazardType = "urban_flood" | "flash_flood" | "river_flood";
export type Level = "Low" | "Moderate" | "High" | "Very High";
export type ResponseStatus = "reported" | "responding" | "resolved" | null;

export interface Zone {
  id: string;
  score: number;
  level: Level;
  extended: boolean;
}

// backend/report_confidence.py's compute() output -- deliberately not a
// single "truth score": score (0-100) + a band label with its own
// vocabulary, plus the per-signal breakdown that produced it.
export interface Confidence {
  score: number;
  band: "Strongly corroborated" | "Well-corroborated" | "Some corroboration" | "Weak";
  signals: {
    photo_check?: { status: "no_photo" | "checked" | "check_failed"; shows_flooding?: boolean; note?: string | null; detail?: string };
    cluster_size?: number;
    news_hits?: number;
    nearby_historical_events?: number;
    sar?: {
      status: "not_applicable" | "checked" | "not_yet_checked" | "check_failed";
      new_flood_at_peak_km2?: number;
      verdict?: string;
      detail?: string;
    };
  };
}

interface ReportBase {
  id: string;
  reporter_ref: string | null;
  hazard_type: HazardType;
  description: string | null;
  has_photo: boolean;
  photo_url: string | null;
  annotated_photo_url: string | null;
  ai_assisted: boolean;
  synthetic: boolean;
  lon: number;
  lat: number;
  location_label: string | null;
  district: string | null;
  depth_lo_m: number | null;
  depth_hi_m: number | null;
  submitted_at: string;
  verified_at: string | null;
  verified_by: string | null;
  assigned_responder: string | null;
  eta_minutes: number | null;
  response_status: ResponseStatus;
  resolved_at: string | null;
  zone: Zone | null;
  confidence: Confidence;
}

export interface Incident extends ReportBase {
  status: "verified" | "resolved";
}

export interface PendingReport extends ReportBase {
  status: "pending";
}

// backend/geo_data.py's nearest_facility() -- real OSM fire stations /
// hospitals, see routers/resource_allocation.py.
export interface Facility {
  name: string;
  lat: number;
  lon: number;
  distance_km: number;
}

export interface NearestFacilities {
  fire_station: Facility | null;
  hospital: Facility | null;
}

// backend/road_closure_score.py's compute() and
// route_engine.road_closure_recommendations() output shapes.
export type Highway = string | string[] | null;

export interface RoadClosureSignals {
  water_depth: number;
  report_count: number;
  road_classification: number;
  historical_frequency: number;
  rainfall_forecast: number;
}

export interface RoadClosureScore {
  name: string;
  highway: Highway;
  n_edges: number;
  coords: [number, number][][];
  closure_score: number;
  level: Level;
  emoji: string;
  action: string;
  action_basis: "depth" | "score";
  n_verified_reports: number;
  incident_ids: string[];
  max_depth_hi_m: number | null;
  n_nearby_historical_events: number;
  near_term_rainfall_mm: number | null;
  signals: RoadClosureSignals;
}

export interface AffectedSegment {
  name: string;
  highway: Highway;
  n_edges: number;
  coords: [number, number][][];
}

export interface RoadClosureByIncident {
  id: string;
  lon: number;
  lat: number;
  hazard_type: HazardType;
  location_label: string | null;
  district: string | null;
  synthetic: boolean;
  depth_lo_m: number | null;
  depth_hi_m: number | null;
  affected_segments: AffectedSegment[];
  n_segments: number;
}

// backend/report_events.py's timeline_for_report() output.
export type EventType = "submitted" | "verified" | "rejected" | "responder_assigned" | "resolved";

export interface TimelineEvent {
  event_type: EventType;
  occurred_at: string;
  detail: string | null;
  reconstructed: boolean;
  note?: string;
}

export interface ReportTimeline {
  report_id: string;
  events: TimelineEvent[];
  untimed_notes: string[];
}

// backend/analytics.py's three views over the live Report table.
export interface LatencyStats {
  n: number;
  mean_min: number | null;
  median_min: number | null;
  min_min: number | null;
  max_min: number | null;
}

export interface ResponseTimeStats {
  verification_latency: LatencyStats;
  resolution_latency: LatencyStats;
  total_reports: number;
}

export interface DistrictCount {
  district: string;
  total: number;
  pending: number;
  verified: number;
  rejected: number;
  resolved: number;
}

export interface Hotspot {
  centroid: { lat: number; lon: number };
  district: string | null;
  n_reports: number;
  hazard_types: HazardType[];
  any_synthetic: boolean;
  static_zone: { id: string; score: number; level: Level } | null;
}

export interface HotspotsResponse {
  hotspots: Hotspot[];
  n_verified_or_resolved_reports_considered: number;
  note: string;
}

// backend/routers/briefings.py -- district assembly briefing lifecycle
// (draft stored -> human review -> approved/rejected). Mirrors
// streamlit_app/geo_tools.py's BRIEFING_SECTION_KEYS exactly.
export const BRIEFING_SECTION_KEYS = ["purpose", "context", "finding", "implications", "sources"] as const;
export type BriefingSectionKey = (typeof BRIEFING_SECTION_KEYS)[number];

export interface Briefing {
  id: string;
  district: string;
  trigger_reason: string;
  source_finding: string | null;
  status: "drafted" | "approved" | "rejected";
  sections: Partial<Record<BriefingSectionKey, string>>;
  doc_url: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

// backend/routers/districts.py -- per-assembly composite vulnerability
// score (SAR + DEM + LULC) + geometry. Three coverage scopes share this
// shape, but "extended" only ever populates a minimal subset (score,
// level, water_occ_pct, low_elev_frac_pct, in_original_pilot) -- the
// optional fields reflect that real difference, not laziness.
export type DistrictScope = "pilot" | "extended" | "lower_volta";

export interface AssemblyScore {
  assembly: string;
  score: number;
  level: Level;
  water_occ_pct: number;
  low_elev_frac_pct: number;
  median_elev_m?: number;
  impervious_pct?: number;
  wetland_water_pct?: number;
  in_original_pilot?: boolean;
  region?: string;
}

// Minimal local GeoJSON typing -- avoids pulling in @types/geojson for
// the one shape this app needs.
export interface DistrictFeature {
  type: "Feature";
  geometry:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] };
  properties: AssemblyScore;
}

export interface PilotDistrictsResponse {
  scores: AssemblyScore[];
  geojson: { type: "FeatureCollection"; features: DistrictFeature[] };
}

// risk_engine/briefing_queue.py's semi-automatic flagging queue.
export interface BriefingQueueEntry {
  district: string;
  reason: string;
  source_finding: string;
  flagged_at: string;
}

// backend/routers/encroachment_trend.py + geo_data.py's
// encroachment_trend_cells()/encroachment_trend_by_assembly() --
// risk_engine/channel_encroachment_timeseries.py's 2019-2026 NDBI-near-
// channel trend. See that module's docstring for the full honesty
// caveats (2019 dataset-wide anomaly, flood-contamination risk on
// "Improving" cells).
export type EncroachmentDirection = "Worsening" | "Stable" | "Improving";

export interface EncroachmentAssemblyRow {
  assembly: string;
  n_cells_near_channel: number;
  n_worsening: number;
  n_stable: number;
  n_improving: number;
  n_possibly_flood_contaminated: number;
  n_sensitive_to_2019: number;
  mean_slope_per_year: number;
}

export interface EncroachmentYearValue {
  status: string;
  mean_ndbi_near_channel: number | null;
  n_buffer_pixels_valid?: number;
  scenes_used?: number;
}

export interface EncroachmentCell {
  zone_id: string;
  assembly: string | null;
  lon: number;
  lat: number;
  years: Record<string, EncroachmentYearValue>;
  slope_per_year: number;
  n_years_used: number;
  trend_note: string;
  direction: EncroachmentDirection;
  slope_per_year_excl_2019: number | null;
  direction_excl_2019: EncroachmentDirection | null;
  sensitive_to_2019: boolean;
  documented_flood_years: number[];
  possible_flood_contamination: boolean;
}

// backend/routers/drain_priority.py -- Feature 3 (govt dashboard):
// composite vulnerability score + OSM channel-encroachment proximity,
// ranked for drain/channel maintenance budget allocation. Mirrors
// streamlit_app/features/govt_drain_priority.py's priority formula.
export interface DrainPriorityZone {
  zone_id: string;
  assembly: string;
  score: number;
  level: Level;
  confidence: number;
  min_dist_m: number;
  encroachment_text: string;
  obstruction_m: number | null;
  priority: number;
  geometry:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] };
}

export interface DrainPriorityGap {
  zone_id: string;
  assembly: string;
  score: number;
  level: Level;
}

export interface DrainPriorityResponse {
  with_data: DrainPriorityZone[];
  without_data: DrainPriorityGap[];
}

// risk_engine/export_raster_overlays.py's output, served statically from
// backend/main.py's /overlays mount -- pilot-scope-only raw SAR/DEM/
// WorldCover evidence behind District Vulnerability Dashboard's overlay
// toggle. bounds is [[south, west], [north, east]], same shape Leaflet's
// ImageOverlay expects directly.
export interface OverlayWorldCoverClass {
  code: number;
  name: string;
  color_rgb: [number, number, number];
}

export interface OverlayManifest {
  bounds: [[number, number], [number, number]];
  scenes_used: number;
  layers: {
    sar_water_occurrence?: { file: string; min: number; max: number; legend: string };
    dem_elevation?: { file: string; min_m: number; max_m: number; legend: string };
    worldcover?: { file: string; legend: string; classes_present: OverlayWorldCoverClass[] };
  };
}

export interface Cluster {
  reports: PendingReport[];
  n_reports: number;
  centroid: { lon: number; lat: number };
  district: string | null;
  max_severity: number;
  hazard_types: HazardType[];
  any_synthetic: boolean;
  corroborating_news: unknown[];
}
