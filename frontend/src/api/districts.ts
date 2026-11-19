import { api } from "./client";
import type { PilotDistrictsResponse } from "./types";

export async function fetchPilotDistricts(): Promise<PilotDistrictsResponse> {
  const { data } = await api.get<PilotDistrictsResponse>("/districts/pilot");
  return data;
}
