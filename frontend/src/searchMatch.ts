// Shared by every page's local search filter (see TopBar's `search` prop) --
// plain case-insensitive substring match across whichever fields that
// page considers searchable. Never a backend call: it only narrows data
// the page already has loaded.
export function matchesQuery(fields: (string | null | undefined)[], query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return fields.some((f) => f?.toLowerCase().includes(q));
}
