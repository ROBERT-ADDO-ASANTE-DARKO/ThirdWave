import { api } from "./client";
import type { DistrictScope, PilotDistrictsResponse } from "./types";

const SCOPE_PATH: Record<DistrictScope, string> = {
  pilot: "/districts/pilot",
  extended: "/districts/extended",
  lower_volta: "/districts/lower-volta",
};

export async function fetchDistricts(scope: DistrictScope): Promise<PilotDistrictsResponse> {
  const { data } = await api.get<PilotDistrictsResponse>(SCOPE_PATH[scope], { timeout: 20_000 });
  return data;
}
