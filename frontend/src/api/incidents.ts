import { api } from "./client";
import type { Cluster, Incident, PendingReport } from "./types";

export async function fetchPendingReports(district?: string): Promise<PendingReport[]> {
  const { data } = await api.get<PendingReport[]>("/reports/pending", { params: district ? { district } : {} });
  return data;
}

export async function fetchActiveIncidents(district?: string): Promise<Incident[]> {
  const { data } = await api.get<Incident[]>("/incidents/active", { params: district ? { district } : {} });
  return data;
}

export async function fetchPendingClusters(district?: string): Promise<Cluster[]> {
  const { data } = await api.get<Cluster[]>("/reports/clusters", { params: district ? { district } : {} });
  return data;
}

export async function fetchResolvedIncidents(limit = 20, district?: string): Promise<Incident[]> {
  const { data } = await api.get<Incident[]>("/incidents/resolved", { params: { limit, ...(district ? { district } : {}) } });
  return data;
}
