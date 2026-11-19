import { api } from "./client";
import type { Briefing, BriefingQueueEntry, BriefingSectionKey } from "./types";

// "K. Asante / Weija Gbawe NADMO" -- this prototype's one fixed officer
// identity (see Sidebar.tsx), same convention api/reports.ts's
// VERIFIED_BY uses.
const REVIEWED_BY = "K. Asante";

export async function fetchPendingBriefings(district?: string): Promise<Briefing[]> {
  const { data } = await api.get<Briefing[]>("/briefings/pending", { params: district ? { district } : {} });
  return data;
}

export async function fetchBriefingQueue(): Promise<BriefingQueueEntry[]> {
  const { data } = await api.get<BriefingQueueEntry[]>("/briefings/queue");
  return data;
}

export interface CreateDraftInput {
  district: string;
  trigger_reason: string;
  source_finding: string | null;
  sections: Partial<Record<BriefingSectionKey, string>>;
}

export async function createDraft(input: CreateDraftInput): Promise<Briefing> {
  const { data } = await api.post<Briefing>("/briefings/draft", input);
  return data;
}

export async function updateSections(id: string, sections: Partial<Record<BriefingSectionKey, string>>): Promise<Briefing> {
  const { data } = await api.patch<Briefing>(`/briefings/${id}/sections`, { sections });
  return data;
}

export async function rejectBriefing(id: string): Promise<Briefing> {
  const { data } = await api.post<Briefing>(`/briefings/${id}/review`, { approve: false, reviewed_by: REVIEWED_BY });
  return data;
}

export async function approveBriefing(id: string, docUrl: string): Promise<Briefing> {
  const { data } = await api.post<Briefing>(`/briefings/${id}/review`, { approve: true, reviewed_by: REVIEWED_BY, doc_url: docUrl });
  return data;
}
