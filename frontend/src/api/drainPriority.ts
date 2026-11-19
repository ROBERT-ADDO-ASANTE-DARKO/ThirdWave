import { api } from "./client";
import type { DrainPriorityResponse } from "./types";

export async function fetchDrainPriority(): Promise<DrainPriorityResponse> {
  const { data } = await api.get<DrainPriorityResponse>("/drain-priority", { timeout: 20_000 });
  return data;
}
