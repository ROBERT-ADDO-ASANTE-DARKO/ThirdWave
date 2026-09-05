-- ThirdWave MVP — Prediction-vs-Outcome logging schema.
--
-- Purpose (MVP Spec §13.3, §11.2): every rule-based prediction is logged from
-- day one so the AI Engineer has a labelled dataset to train and evaluate a
-- supervised model against once a full rainy season has passed. Without this
-- table, Phase 2's "ML model must beat the rule-based baseline" requirement
-- (§11.2) has no data to evaluate against.
--
-- Slots into the data model in Spec §9 (PostgreSQL + PostGIS). Assumes
-- risk_zone and incident tables already exist per that section.

-- One row every recompute cycle (~15 min) per zone: a durable snapshot of
-- what the model believed, and why, at that moment. risk_zone itself is
-- mutable/current-state; this table is the append-only history.
CREATE TABLE risk_prediction_log (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    hazard_type     TEXT NOT NULL,
    level           TEXT NOT NULL CHECK (level IN ('low', 'watch', 'warning', 'critical')),
    confidence      NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    is_degraded     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Raw feature values behind the decision — this is what a future
    -- supervised model will train on, not just the derived level.
    rainfall_6h_mm      NUMERIC(6,2),
    river_level_m       NUMERIC(6,2),
    dam_release_active  BOOLEAN,

    -- Which thresholds were in force at prediction time (thresholds get
    -- tuned during Sprint 5-6 per the delivery plan §15 — recording them
    -- per-row means old predictions stay interpretable after a retune).
    rainfall_warning_threshold_mm  NUMERIC(6,2),
    rainfall_critical_threshold_mm NUMERIC(6,2),
    river_warning_threshold_m      NUMERIC(6,2),
    river_critical_threshold_m     NUMERIC(6,2),

    contributing_factors   TEXT[] NOT NULL DEFAULT '{}',
    data_sources            JSONB NOT NULL DEFAULT '{}',  -- {"rainfall": "live", "river_level": "stale"}
    model_version           TEXT NOT NULL,

    computed_at     TIMESTAMPTZ NOT NULL,
    valid_from      TIMESTAMPTZ NOT NULL,
    valid_to        TIMESTAMPTZ NOT NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_prediction_log_zone_time ON risk_prediction_log (zone_id, computed_at DESC);
CREATE INDEX idx_prediction_log_level ON risk_prediction_log (level);

-- Links a verified incident back to whichever prediction(s) were "live" for
-- that zone at/near the incident's report time. This is the actual
-- prediction-vs-outcome pair: did the model say Warning/Critical before a
-- real, human-verified flood happened there, and how much lead time did it
-- give citizens/responders?
--
-- Populated by the Backend Engineer's incident-verification flow (spec §9,
-- Incident entity) calling back into the AI Engineer's service, or by a
-- scheduled job joining on zone_id + time window — either is fine for MVP,
-- but the row must exist for every verified incident.
CREATE TABLE incident_outcome_link (
    id                      BIGSERIAL PRIMARY KEY,
    incident_id             TEXT NOT NULL,          -- FK to incident.id (INC-GH-2026-######)
    matched_prediction_id   BIGINT REFERENCES risk_prediction_log(id),

    -- The prediction level that was active when the incident was first
    -- reported/verified — the core label for later precision/recall and
    -- lead-time analysis.
    predicted_level_at_report   TEXT CHECK (predicted_level_at_report IN ('low', 'watch', 'warning', 'critical')),

    -- Minutes between the matched prediction crossing Watch/Warning/Critical
    -- and the incident being verified. Negative or NULL means the model gave
    -- no advance warning — the single most important number for judging
    -- whether the rule-based model is doing its job.
    lead_time_minutes       INTEGER,

    incident_verified_at    TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outcome_link_incident ON incident_outcome_link (incident_id);

-- Convenience view: every verified incident next to the model's call at the
-- time, for the AI Engineer's own live-monitoring dashboard (Sprint 10,
-- spec §15) and for whoever evaluates the future ML model against baseline.
CREATE VIEW prediction_outcome_summary AS
SELECT
    l.incident_id,
    l.predicted_level_at_report,
    l.lead_time_minutes,
    l.incident_verified_at,
    p.zone_id,
    p.hazard_type,
    p.confidence,
    p.model_version,
    p.contributing_factors
FROM incident_outcome_link l
LEFT JOIN risk_prediction_log p ON p.id = l.matched_prediction_id;
