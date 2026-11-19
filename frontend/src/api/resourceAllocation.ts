import { api } from "./client";
import type { NearestFacilities } from "./types";

export async function fetchNearestFacilities(lat: number, lon: number): Promise<NearestFacilities> {
  const { data } = await api.get<NearestFacilities>("/resource-allocation/nearest-facilities", { params: { lat, lon } });
  return data;
}
