import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { approveBriefing, createDraft, fetchPendingBriefings, rejectBriefing, updateSections } from "../../api/briefings";
import { BRIEFING_SECTION_KEYS, type Briefing, type BriefingSectionKey } from "../../api/types";
import "../../components/PendingQueue.css";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile, Pill } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./BriefingReview.css";

// Mirrors streamlit_app/features/govt_briefing_review.py's review/edit/
// approve/reject workflow, backed by the same real /briefings endpoints.
//
// Scope note: that Streamlit page's "Draft with AI" button calls
// streamlit_app/geo_tools.py's draft_briefing() -- a Claude tool-calling
// pipeline (its own system prompt + tools, grounded in the risk engine
// data) that only exists in Streamlit-local Python, not as a backend
// HTTP endpoint. POST /briefings/draft itself only ever *stores*
// already-drafted sections (see routers/briefings.py's docstring) -- it
// never generated them. Porting that drafting pipeline into the backend
// is real, separate work (its own system prompt and tool definitions),
// not something to fake here. This form instead takes the five section
// texts directly -- typed, or pasted in from a draft produced elsewhere
// -- and saves them through the exact same real endpoint. The review/
// edit/approve/reject half below is fully real either way.

const KNOWN_DISTRICTS = [
  "Ablekuma Central Municipal", "Ablekuma North Municipal", "Ablekuma West Municipal",
  "Accra Metropolis", "Ayawaso Central Municipal", "Korle Klottey Municipal",
  "Weija Gbawe Municipal", "Ayawaso West Municipal", "La-Nkwantanang-Madina Municipal",
  "South Tongu", "North Tongu", "Central Tongu", "Lower Manya", "Asuogyaman",
  "Ada East", "Ada West",
];

const TRIGGER_REASONS = ["manual", "new_encroachment_finding", "new_historical_event"];

const SECTION_TITLES: Record<BriefingSectionKey, string> = {
  purpose: "Purpose",
  context: "Context",
  finding: "Finding",
  implications: "What this means for the Assembly",
  sources: "Sources",
};

const SECTION_ROWS: Record<BriefingSectionKey, number> = {
  purpose: 2,
  context: 4,
  finding: 4,
  implications: 4,
  sources: 2,
};

function emptySections(): Record<BriefingSectionKey, string> {
  return Object.fromEntries(BRIEFING_SECTION_KEYS.map((k) => [k, ""])) as Record<BriefingSectionKey, string>;
}

function DraftForm({ onDrafted }: { onDrafted: () => void }) {
  // Pre-filled when arriving from the District Vulnerability Dashboard's
  // briefing-queue banner "Draft ->" link -- same real mechanism
  // Streamlit's brf_prefill session-state did, just carried as query
  // params (React Router's natural equivalent of cross-page handoff)
  // instead of shared session state.
  const [searchParams] = useSearchParams();
  const prefillDistrict = searchParams.get("district");
  const [district, setDistrict] = useState(prefillDistrict ?? KNOWN_DISTRICTS[0]);
  const [reason, setReason] = useState(searchParams.get("reason") ?? TRIGGER_REASONS[0]);
  const [sourceFinding, setSourceFinding] = useState(searchParams.get("source_finding") ?? "");
  const [sections, setSections] = useState(emptySections());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  // The briefing queue's district strings don't always match
  // KNOWN_DISTRICTS exactly (e.g. "La-Nkwantanang-Madina" vs this list's
  // "La-Nkwantanang-Madina Municipal") -- same real naming inconsistency
  // the Streamlit version hit. Union instead of silently dropping an
  // unmatched prefill.
  const districtOptions = useMemo(
    () => (prefillDistrict && !KNOWN_DISTRICTS.includes(prefillDistrict) ? [prefillDistrict, ...KNOWN_DISTRICTS] : KNOWN_DISTRICTS),
    [prefillDistrict],
  );

  function submit() {
    setBusy(true);
    setStatus(null);
    createDraft({ district, trigger_reason: reason, source_finding: sourceFinding.trim() || null, sections })
      .then((b) => {
        setStatus(`Saved ${b.id}. Scroll down to review it.`);
        setSections(emptySections());
        setSourceFinding("");
        onDrafted();
      })
      .catch((err) => setStatus(err?.response?.data?.detail ?? err?.message ?? "Could not save the draft."))
      .finally(() => setBusy(false));
  }

  const hasAnySection = BRIEFING_SECTION_KEYS.some((k) => sections[k].trim());

  return (
    <Card className="br-draft-panel">
      <span className="br-draft-title">Draft a new briefing</span>
      <p className="br-draft-subtitle">
        AI-assisted drafting isn't wired up in this build yet (see the note in this page's source) — write or
        paste the five sections below. They're saved through the same real endpoint either way.
      </p>
      {prefillDistrict && <p className="br-prefill-note">Pre-filled from the briefing queue.</p>}

      <div className="br-draft-meta-row">
        <label className="br-field">
          <span>District</span>
          <select value={district} onChange={(e) => setDistrict(e.target.value)}>
            {districtOptions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="br-field">
          <span>Reason</span>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {TRIGGER_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="br-field">
        <span>Source finding (optional note on what prompted this)</span>
        <input type="text" value={sourceFinding} onChange={(e) => setSourceFinding(e.target.value)} />
      </label>

      {BRIEFING_SECTION_KEYS.map((key) => (
        <label className="br-field" key={key}>
          <span>{SECTION_TITLES[key]}</span>
          <textarea
            rows={SECTION_ROWS[key]}
            value={sections[key]}
            onChange={(e) => setSections((prev) => ({ ...prev, [key]: e.target.value }))}
          />
        </label>
      ))}

      <button type="button" className="rq-btn rq-btn-primary br-save-btn" disabled={busy || !hasAnySection} onClick={submit}>
        {busy ? "Saving…" : "Save draft"}
      </button>
      {status && <p className="br-status">{status}</p>}
    </Card>
  );
}

function BriefingCard({
  briefing,
  busy,
  onSave,
  onReject,
  onApprove,
}: {
  briefing: Briefing;
  busy: boolean;
  onSave: (sections: Partial<Record<BriefingSectionKey, string>>) => void;
  onReject: () => void;
  onApprove: (docUrl: string) => void;
}) {
  const [sections, setSections] = useState<Record<BriefingSectionKey, string>>(() => {
    const base = emptySections();
    BRIEFING_SECTION_KEYS.forEach((k) => (base[k] = briefing.sections[k] ?? ""));
    return base;
  });
  const [docUrl, setDocUrl] = useState("");

  return (
    <Card className="br-card">
      <div className="br-card-head">
        <span className="br-card-title">
          <code>{briefing.id}</code> — {briefing.district}
        </span>
        <Pill tone={briefing.status === "approved" ? "green" : briefing.status === "rejected" ? "neutral" : "teal"}>
          {briefing.status}
        </Pill>
      </div>
      {briefing.source_finding && <p className="rq-report-caption">{briefing.source_finding}</p>}

      {BRIEFING_SECTION_KEYS.map((key) => (
        <label className="br-field" key={key}>
          <span>{SECTION_TITLES[key]}</span>
          <textarea
            rows={SECTION_ROWS[key]}
            value={sections[key]}
            onChange={(e) => setSections((prev) => ({ ...prev, [key]: e.target.value }))}
          />
        </label>
      ))}

      <div className="br-actions-row">
        <button type="button" className="rq-btn rq-btn-outline rq-btn-sm" disabled={busy} onClick={() => onSave(sections)}>
          Save edits
        </button>
        <button type="button" className="rq-btn rq-btn-reject rq-btn-sm" disabled={busy} onClick={onReject}>
          Reject
        </button>
        <input
          type="text"
          placeholder="Published doc URL (paste in once available)"
          value={docUrl}
          onChange={(e) => setDocUrl(e.target.value)}
          className="br-doc-input"
        />
        <button
          type="button"
          className="rq-btn rq-btn-verify rq-btn-sm"
          disabled={busy || !docUrl.trim()}
          onClick={() => onApprove(docUrl.trim())}
        >
          Approve &amp; record
        </button>
      </div>
      <p className="br-publish-note">
        Publishing creates a real, shareable document. This page can't call the Claude Docs connector itself (not
        reachable from a standalone backend) — the resulting link gets pasted in above to finalize the record.
      </p>
    </Card>
  );
}

export function BriefingReview() {
  const [pending, setPending] = useState<Briefing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    return fetchPendingBriefings()
      .then((data) => {
        setPending(data);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function withBusy(id: string, fn: () => Promise<unknown>) {
    setBusyIds((prev) => new Set(prev).add(id));
    return fn()
      .then(() => refresh())
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Action failed."))
      .finally(() =>
        setBusyIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        }),
      );
  }

  const filteredPending = pending.filter((b) => matchesQuery([b.id, b.district, b.trigger_reason, b.source_finding], query));

  return (
    <>
      <TopBar
        title="District Briefing Review"
        subtitle="AI-drafted, human-reviewed briefing documents — never sent anywhere without an officer editing it first"
        search={{ value: query, onChange: setQuery, placeholder: "Search by district, reason, or ID…" }}
      />

      {error && (
        <Card>
          <p className="error-text">Could not reach the backend: {error}</p>
        </Card>
      )}

      <section className="section-kpis">
        <Card>
          <KpiTile label="Pending review" value={pending.length} />
        </Card>
      </section>

      <DraftForm onDrafted={refresh} />

      <h2 className="section-title section-title-spaced">Pending briefings</h2>
      {!loading && pending.length === 0 && <p className="section-caption">No briefings pending review.</p>}
      {pending.length > 0 && filteredPending.length === 0 && <p className="section-caption">No matches for "{query}".</p>}
      <div className="br-list">
        {filteredPending.map((b) => (
          <BriefingCard
            key={b.id}
            briefing={b}
            busy={busyIds.has(b.id)}
            onSave={(sections) => withBusy(b.id, () => updateSections(b.id, sections))}
            onReject={() => withBusy(b.id, () => rejectBriefing(b.id))}
            onApprove={(docUrl) => withBusy(b.id, () => approveBriefing(b.id, docUrl))}
          />
        ))}
      </div>
    </>
  );
}
