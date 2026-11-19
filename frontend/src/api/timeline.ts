import { api } from "./client";
import type { ReportTimeline } from "./types";

export async function fetchReportTimeline(reportId: string): Promise<ReportTimeline> {
  const { data } = await api.get<ReportTimeline>(`/reports/${encodeURIComponent(reportId)}/timeline`);
  return data;
}
