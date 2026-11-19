import { api } from "./client";
import type { DistrictCount, HotspotsResponse, ResponseTimeStats } from "./types";

export async function fetchResponseTimes(): Promise<ResponseTimeStats> {
  const { data } = await api.get<ResponseTimeStats>("/analytics/response-times", { timeout: 20_000 });
  return data;
}

export async function fetchByDistrict(): Promise<DistrictCount[]> {
  const { data } = await api.get<DistrictCount[]>("/analytics/by-district", { timeout: 20_000 });
  return data;
}

export async function fetchHotspots(): Promise<HotspotsResponse> {
  const { data } = await api.get<HotspotsResponse>("/analytics/hotspots", { timeout: 20_000 });
  return data;
}
