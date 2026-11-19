import { useCallback, useEffect, useState } from "react";
import { fetchActiveIncidents } from "../../api/incidents";
import { fetchNearestFacilities } from "../../api/resourceAllocation";
import { assignResponder, resolveIncident } from "../../api/reports";
import type { Incident, NearestFacilities } from "../../api/types";
import { hazardLabel } from "../../components/PendingQueue";
import { TopBar } from "../../components/TopBar";
import { Card, LevelPill, Pill } from "../../components/ui";
import { LEVEL_RANK } from "../../colors";
import { matchesQuery } from "../../searchMatch";
import "./ResourceAllocation.css";

// Mirrors streamlit_app/features/govt_resource_allocation.py's structure
// exactly -- see that module's docstring for the research behind it
// (NADMO's real district-first, multi-agency dispatch model). One
// deliberate scope difference: this page doesn't merge in
// demo_seed_incidents.json the way Streamlit does (that file lives
// outside the backend and exists only to keep Streamlit's queue from
// looking empty); it shows exactly what GET /incidents/active returns,
// consistent with every other Operations screen in this app.

const PILOT_ASSEMBLIES = [
  "Ablekuma Central Municipal",
  "Ablekuma North Municipal",
  "Ablekuma West Municipal",
  "Accra Metropolis",
  "Ayawaso Central Municipal",
  "Korle Klottey Municipal",
  "Weija Gbawe Municipal",
];

// Korle Klottey starts deployed so "the incident's own district team
// isn't free" is a real state the UI has to handle, not just the happy
// path -- same deliberate choice as the Streamlit feature.
const INITIAL_NADMO_TEAMS: Record<string, boolean> = Object.fromEntries(
  PILOT_ASSEMBLIES.map((a) => [`NADMO District Team — ${a}`, a !== "Korle Klottey Municipal"]),
);

const LIAISON_UNITS = ["Police Liaison", "Military Liaison (on request)"];

interface ResponderAssignment {
  type: "NADMO" | "Fire" | "Medical" | "Liaison";
  name: string;
  etaMinutes: number | null;
}

// This bookkeeping (who's dispatched where, which NADMO team/liaison is
// free) is deliberately NOT sent to the backend -- the Report model has
// a single assigned_responder field, not a multi-agency roster, same gap
// Streamlit's page documents ("session-local bookkeeping, not a
// real-time feed"). The one exception is the NADMO team dispatch itself,
// which does call the real assign-responder endpoint below, because
// that's the one field the shared backend model can actually represent.
// Resetting on reload is an accepted characteristic here, not a bug.

function IncidentCoordinationCard({
  incident,
  facilities,
  responders,
  nadmoTeams,
  liaisonUnits,
  facilityDispatch,
  busy,
  onDispatchTeam,
  onDispatchFire,
  onDispatchMedical,
  onRequestLiaison,
  onResolve,
}: {
  incident: Incident;
  facilities: NearestFacilities | null | undefined;
  responders: ResponderAssignment[];
  nadmoTeams: Record<string, boolean>;
  liaisonUnits: Record<string, boolean>;
  facilityDispatch: Record<string, boolean>;
  busy: boolean;
  onDispatchTeam: (team: string, eta: number) => void;
  onDispatchFire: (name: string) => void;
  onDispatchMedical: (name: string) => void;
  onRequestLiaison: (names: string[]) => void;
  onResolve: () => void;
}) {
  const district = incident.district;
  const ownTeam = district ? `NADMO District Team — ${district}` : null;
  const availableTeams = Object.entries(nadmoTeams)
    .filter(([, available]) => available)
    .map(([name]) => name);
  const [team, setTeam] = useState(ownTeam && availableTeams.includes(ownTeam) ? ownTeam : availableTeams[0] ?? "");
  const [eta, setEta] = useState(15);
  const [liaisonPicked, setLiaisonPicked] = useState<string[]>([]);

  const fire = facilities?.fire_station;
  const hospital = facilities?.hospital;
  const fireDispatched = fire ? facilityDispatch[fire.name] === false : false;
  const medicalDispatched = hospital ? facilityDispatch[hospital.name] === false : false;
  const availableLiaison = Object.entries(liaisonUnits)
    .filter(([, available]) => available)
    .map(([name]) => name);

  return (
    <Card className="ra-card">
      <div className="ra-card-head">
        <div className="ra-card-head-left">
          <code>{incident.id}</code>
          {incident.synthetic && <span className="ra-synthetic-badge">SYNTHETIC</span>}
          {incident.zone ? <LevelPill level={incident.zone.level} /> : <Pill tone="neutral">Unknown severity</Pill>}
        </div>
        <span className="ra-card-location">
          {incident.location_label ?? `${incident.lat.toFixed(4)}, ${incident.lon.toFixed(4)}`} ·{" "}
          {district ?? "outside pilot coverage"}
        </span>
      </div>
      <p className="ra-hazard">
        {hazardLabel(incident.hazard_type)} · Status: {(incident.response_status ?? "reported").replace(/^./, (c) => c.toUpperCase())}
      </p>

      {responders.length > 0 && (
        <div className="ra-responding-pill">Responding: {responders.map((r) => `${r.type}: ${r.name}`).join(" · ")}</div>
      )}

      <details className="ra-coordinate" open={responders.length === 0}>
        <summary className="ra-coordinate-summary">Coordinate response</summary>

        <div className="ra-columns">
          <div className="ra-column">
            <span className="ra-column-title">NADMO District Team</span>
            <p className="ra-column-note">Defaults to the incident's own district</p>
            {availableTeams.length > 0 ? (
              <>
                <select value={team} onChange={(e) => setTeam(e.target.value)} className="ra-select">
                  {availableTeams.map((t) => (
                    <option key={t} value={t}>
                      {t.replace("NADMO District Team — ", "")}
                    </option>
                  ))}
                </select>
                <div className="ra-eta-row">
                  <input type="number" min={1} max={180} value={eta} onChange={(e) => setEta(Number(e.target.value))} className="ra-eta-input" />
                  <span className="ra-eta-label">min ETA</span>
                </div>
                <button type="button" className="rq-btn rq-btn-primary rq-btn-sm ra-dispatch-btn" disabled={busy} onClick={() => onDispatchTeam(team, eta)}>
                  Dispatch team
                </button>
                {ownTeam && !availableTeams.includes(ownTeam) && (
                  <p className="ra-warning">{district}'s own team is deployed elsewhere.</p>
                )}
              </>
            ) : (
              <p className="ra-warning">No NADMO team available.</p>
            )}
          </div>

          <div className="ra-column">
            <span className="ra-column-title">Fire Service</span>
            <p className="ra-column-note ra-column-note-real">REAL — OSM nearest station</p>
            {fire ? (
              <>
                <span className="ra-facility-name">{fire.name}</span>
                <span className="ra-facility-distance">{fire.distance_km.toFixed(2)} km away</span>
                {fireDispatched ? (
                  <p className="ra-column-note">Dispatched elsewhere.</p>
                ) : (
                  <button type="button" className="rq-btn rq-btn-primary rq-btn-sm ra-dispatch-btn" onClick={() => onDispatchFire(fire.name)}>
                    Dispatch fire
                  </button>
                )}
              </>
            ) : (
              <p className="ra-column-note">No real fire station data for this location.</p>
            )}
          </div>

          <div className="ra-column">
            <span className="ra-column-title">Medical</span>
            <p className="ra-column-note ra-column-note-real">REAL — OSM nearest hospital</p>
            {hospital ? (
              <>
                <span className="ra-facility-name">{hospital.name}</span>
                <span className="ra-facility-distance">{hospital.distance_km.toFixed(2)} km away</span>
                {medicalDispatched ? (
                  <p className="ra-column-note">Dispatched elsewhere.</p>
                ) : (
                  <button type="button" className="rq-btn rq-btn-primary rq-btn-sm ra-dispatch-btn" onClick={() => onDispatchMedical(hospital.name)}>
                    Dispatch medical
                  </button>
                )}
              </>
            ) : (
              <p className="ra-column-note">No real hospital data for this location.</p>
            )}
          </div>
        </div>

        <div className="ra-liaison">
          <span className="ra-column-title">Police / Military liaison</span>
          <p className="ra-column-note">For larger events — multi-agency pooling, fabricated roster</p>
          {availableLiaison.length > 0 ? (
            <div className="ra-liaison-row">
              {availableLiaison.map((name) => (
                <label key={name} className="ra-liaison-check">
                  <input
                    type="checkbox"
                    checked={liaisonPicked.includes(name)}
                    onChange={(e) =>
                      setLiaisonPicked((prev) => (e.target.checked ? [...prev, name] : prev.filter((n) => n !== name)))
                    }
                  />
                  {name}
                </label>
              ))}
              <button
                type="button"
                className="rq-btn rq-btn-primary rq-btn-sm"
                disabled={liaisonPicked.length === 0}
                onClick={() => {
                  onRequestLiaison(liaisonPicked);
                  setLiaisonPicked([]);
                }}
              >
                Request
              </button>
            </div>
          ) : (
            <p className="ra-column-note">No liaison units available.</p>
          )}
        </div>
      </details>

      {responders.length > 0 && (
        <button type="button" className="rq-btn rq-btn-primary rq-btn-sm ra-resolve-btn" disabled={busy} onClick={onResolve}>
          Mark Resolved
        </button>
      )}
    </Card>
  );
}

export function ResourceAllocation() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [facilities, setFacilities] = useState<Record<string, NearestFacilities | null>>({});
  const [responders, setResponders] = useState<Record<string, ResponderAssignment[]>>({});
  const [nadmoTeams, setNadmoTeams] = useState<Record<string, boolean>>(INITIAL_NADMO_TEAMS);
  const [liaisonUnits, setLiaisonUnits] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(LIAISON_UNITS.map((n) => [n, true])),
  );
  const [facilityDispatch, setFacilityDispatch] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    return fetchActiveIncidents()
      .then((inc) => {
        setIncidents(inc);
        setError(null);
        inc.forEach((i) => {
          if (facilities[i.id] !== undefined) return;
          fetchNearestFacilities(i.lat, i.lon)
            .then((f) => setFacilities((prev) => ({ ...prev, [i.id]: f })))
            .catch(() => setFacilities((prev) => ({ ...prev, [i.id]: null })));
        });
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sorted = [...incidents]
    .filter((inc) => matchesQuery([inc.id, inc.district, inc.location_label, inc.hazard_type], query))
    .sort((a, b) => {
      const ra = a.zone ? LEVEL_RANK[a.zone.level] : -1;
      const rb = b.zone ? LEVEL_RANK[b.zone.level] : -1;
      return rb - ra;
    });

  function dispatchTeam(incidentId: string, team: string, eta: number) {
    setBusyIds((prev) => new Set(prev).add(incidentId));
    assignResponder(incidentId, team, eta)
      .then(() => {
        setResponders((prev) => ({
          ...prev,
          [incidentId]: [...(prev[incidentId] ?? []), { type: "NADMO", name: team, etaMinutes: eta }],
        }));
        setNadmoTeams((prev) => ({ ...prev, [team]: false }));
        return refresh();
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Could not dispatch team."))
      .finally(() =>
        setBusyIds((prev) => {
          const next = new Set(prev);
          next.delete(incidentId);
          return next;
        }),
      );
  }

  function dispatchFire(incidentId: string, name: string) {
    setResponders((prev) => ({ ...prev, [incidentId]: [...(prev[incidentId] ?? []), { type: "Fire", name, etaMinutes: null }] }));
    setFacilityDispatch((prev) => ({ ...prev, [name]: false }));
  }

  function dispatchMedical(incidentId: string, name: string) {
    setResponders((prev) => ({ ...prev, [incidentId]: [...(prev[incidentId] ?? []), { type: "Medical", name, etaMinutes: null }] }));
    setFacilityDispatch((prev) => ({ ...prev, [name]: false }));
  }

  function requestLiaison(incidentId: string, names: string[]) {
    setResponders((prev) => ({
      ...prev,
      [incidentId]: [...(prev[incidentId] ?? []), ...names.map((name) => ({ type: "Liaison" as const, name, etaMinutes: null }))],
    }));
    setLiaisonUnits((prev) => {
      const next = { ...prev };
      names.forEach((n) => (next[n] = false));
      return next;
    });
  }

  function resolve(incidentId: string) {
    setBusyIds((prev) => new Set(prev).add(incidentId));
    resolveIncident(incidentId)
      .then(() => {
        const freed = responders[incidentId] ?? [];
        setNadmoTeams((prev) => {
          const next = { ...prev };
          freed.filter((r) => r.type === "NADMO").forEach((r) => (next[r.name] = true));
          return next;
        });
        setLiaisonUnits((prev) => {
          const next = { ...prev };
          freed.filter((r) => r.type === "Liaison").forEach((r) => (next[r.name] = true));
          return next;
        });
        setFacilityDispatch((prev) => {
          const next = { ...prev };
          freed.filter((r) => r.type === "Fire" || r.type === "Medical").forEach((r) => (next[r.name] = true));
          return next;
        });
        setResponders((prev) => {
          const next = { ...prev };
          delete next[incidentId];
          return next;
        });
        return refresh();
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Could not resolve incident."))
      .finally(() =>
        setBusyIds((prev) => {
          const next = new Set(prev);
          next.delete(incidentId);
          return next;
        }),
      );
  }

  return (
    <>
      <TopBar
        title="Emergency Resource Allocation"
        subtitle="District-first NADMO dispatch, real Fire/Medical distance, multi-agency liaison for larger events"
        search={{ value: query, onChange: setQuery, placeholder: "Search incidents by ID, district, or location…" }}
      />

      {error && (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      )}

      <h2 className="section-title">Active Incidents — Resource Coordination</h2>
      {!loading && incidents.length === 0 && <p className="section-caption">No active incidents.</p>}
      {!loading && incidents.length > 0 && sorted.length === 0 && <p className="section-caption">No matches for "{query}".</p>}
      <div className="ra-incident-list">
        {sorted.map((inc) => (
          <IncidentCoordinationCard
            key={inc.id}
            incident={inc}
            facilities={facilities[inc.id]}
            responders={responders[inc.id] ?? []}
            nadmoTeams={nadmoTeams}
            liaisonUnits={liaisonUnits}
            facilityDispatch={facilityDispatch}
            busy={busyIds.has(inc.id)}
            onDispatchTeam={(team, eta) => dispatchTeam(inc.id, team, eta)}
            onDispatchFire={(name) => dispatchFire(inc.id, name)}
            onDispatchMedical={(name) => dispatchMedical(inc.id, name)}
            onRequestLiaison={(names) => requestLiaison(inc.id, names)}
            onResolve={() => resolve(inc.id)}
          />
        ))}
      </div>

      <div className="ra-availability-strip">
        <Card>
          <span className="ra-availability-title">NADMO district team availability</span>
          <div className="ra-availability-pills">
            {Object.entries(nadmoTeams).map(([name, available]) => (
              <Pill key={name} tone={available ? "green" : "neutral"}>
                {name.replace("NADMO District Team — ", "")} — {available ? "Available" : "Deployed"}
              </Pill>
            ))}
          </div>
        </Card>
        <Card>
          <span className="ra-availability-title">Liaison availability</span>
          <div className="ra-availability-pills">
            {Object.entries(liaisonUnits).map(([name, available]) => (
              <Pill key={name} tone={available ? "green" : "neutral"}>
                {name} — {available ? "Available" : "Requested"}
              </Pill>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
