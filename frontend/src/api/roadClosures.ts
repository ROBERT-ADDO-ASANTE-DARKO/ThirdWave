import { api } from "./client";
import type { RoadClosureByIncident, RoadClosureScore } from "./types";

export async function fetchRoadClosureScores(): Promise<RoadClosureScore[]> {
  const { data } = await api.get<RoadClosureScore[]>("/routing/road-closure-scores", { timeout: 30_000 });
  return data;
}

export async function fetchRoadClosuresByIncident(): Promise<RoadClosureByIncident[]> {
  const { data } = await api.get<RoadClosureByIncident[]>("/routing/road-closures", { timeout: 30_000 });
  return data;
}
