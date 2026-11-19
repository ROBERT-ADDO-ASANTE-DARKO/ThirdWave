import { api } from "./client";
import type { Incident, PendingReport } from "./types";

// "K. Asante / Weija Gbawe NADMO" is this prototype's one fixed officer
// identity (see Sidebar.tsx) -- same single-shared-key auth model as
// auth.py's require_officer, so there's no real per-officer login to pull
// a name from yet.
const VERIFIED_BY = "K. Asante";

export async function verifyReport(reportId: string, approve: boolean): Promise<PendingReport> {
  const { data } = await api.post(`/reports/${reportId}/verify`, { approve, verified_by: VERIFIED_BY });
  return data;
}

export async function verifyBulk(reportIds: string[], approve: boolean): Promise<void> {
  await api.post("/reports/verify-bulk", { report_ids: reportIds, approve, verified_by: VERIFIED_BY });
}

export async function resolveIncident(incidentId: string): Promise<Incident> {
  const { data } = await api.post(`/incidents/${incidentId}/resolve`);
  return data;
}

export async function assignResponder(incidentId: string, responderName: string, etaMinutes: number): Promise<Incident> {
  const { data } = await api.post(`/incidents/${incidentId}/assign-responder`, {
    responder_name: responderName,
    eta_minutes: etaMinutes,
  });
  return data;
}

// Officer-triggered, can take real wall-clock time (a live Sentinel-1
// catalog query) -- see sar_corroboration.py's docstring for why this is
// deliberate, not automatic.
export async function runSarCheck(incidentId: string): Promise<Incident> {
  // Can take up to ~a minute (live Sentinel-1/STAC query) -- override the
  // client's default 10s timeout for this one call.
  const { data } = await api.post(`/incidents/${incidentId}/sar-check`, {}, { timeout: 90_000 });
  return data;
}

export interface GeocodeResult {
  lat: number;
  lon: number;
  resolved_address: string;
}

export async function geocodeAddress(address: string): Promise<GeocodeResult> {
  const { data } = await api.get<GeocodeResult | { error: string }>("/geocode", { params: { address } });
  if ("error" in data) throw new Error(data.error);
  return data;
}

export interface SubmitTestReportInput {
  lon: number;
  lat: number;
  hazardType: string;
  description: string;
  locationLabel?: string;
  depthLoM?: number;
  depthHiM?: number;
}

// Seeds a report through the exact same public pipeline a citizen's phone
// uses (POST /reports, no officer key) with synthetic=true -- the same
// tagging convention incident_store.py's sandbox uses, just without
// porting that sandbox's rainfall-ponding depth model: this calls the
// real endpoint directly rather than building a second, parallel seeding
// mechanism. Exists so the verification queue has something to act on
// when the live DB is empty, same purpose Streamlit's sandbox panel served.
export async function submitTestReport(input: SubmitTestReportInput): Promise<PendingReport> {
  const form = new FormData();
  form.set("lon", String(input.lon));
  form.set("lat", String(input.lat));
  form.set("hazard_type", input.hazardType);
  form.set("description", input.description);
  if (input.locationLabel) form.set("location_label", input.locationLabel);
  if (input.depthLoM != null) form.set("depth_lo_m", String(input.depthLoM));
  if (input.depthHiM != null) form.set("depth_hi_m", String(input.depthHiM));
  form.set("reporter_ref", "react-dashboard-test-seed");
  form.set("synthetic", "true");
  const { data } = await api.post("/reports", form);
  return data;
}
