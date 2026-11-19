import { api } from "./client";
import type { EncroachmentAssemblyRow, EncroachmentCell } from "./types";

export async function fetchEncroachmentByAssembly(): Promise<EncroachmentAssemblyRow[]> {
  const { data } = await api.get<EncroachmentAssemblyRow[]>("/encroachment-trend/by-assembly", { timeout: 20_000 });
  return data;
}

export async function fetchEncroachmentCells(assembly?: string): Promise<EncroachmentCell[]> {
  const { data } = await api.get<EncroachmentCell[]>("/encroachment-trend/cells", {
    params: assembly ? { assembly } : {},
    timeout: 20_000,
  });
  return data;
}
