"""
ThirdWave MVP Risk Engine — rule-based flood risk classifier.

Per MVP Spec §11.1: explainable threshold model over live rainfall + river-level
feeds. No ML in the MVP. Every output must carry full provenance (§11.1, §8.4)
and must never silently present stale data as current.

This module is framework-agnostic (no Django import) so it can run as a
standalone ingestion/scoring job and be called from wherever the AI Engineer's
service lives; it only needs to end up writing RiskZone rows (spec §9) and
RiskPredictionLog rows (see prediction_log_schema.sql) to Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"


class HazardType(str, Enum):
    RAINFALL_FLOOD = "rainfall_flood"
    FLASH_FLOOD = "flash_flood"
    URBAN_FLOOD = "urban_flood"
    RIVER_FLOOD = "river_flood"


MODEL_VERSION = "rule-based-v1"

# How old a feed reading can be before it's treated as unavailable rather
# than current. This is what lets the frontend enforce the fail-safe rule
# (§8.4: never silently show stale data).
MAX_READING_AGE = timedelta(minutes=45)  # ~3x the 15-min recompute interval


@dataclass(frozen=True)
class ZoneThresholdConfig:
    """Per-zone thresholds. One row per RiskZone-eligible area, tunable
    independently — a zone with fast-draining terrain and a zone prone to
    flash flooding should not share thresholds."""

    zone_id: str
    hazard_type: HazardType
    rainfall_6h_warning_mm: float
    rainfall_6h_critical_mm: float
    river_level_warning_m: float
    river_level_critical_m: float
    # If true, a dam-release flag alone forces Critical regardless of
    # rainfall/river readings (spec §11.1).
    dam_release_forces_critical: bool = True


@dataclass(frozen=True)
class RainfallReading:
    zone_id: str
    observed_mm_6h: float | None
    forecast_mm_6h: float | None
    observed_at: datetime | None  # None if the feed has no data at all


@dataclass(frozen=True)
class RiverLevelReading:
    zone_id: str
    level_m: float | None
    observed_at: datetime | None


@dataclass(frozen=True)
class DamReleaseFlag:
    zone_id: str
    active: bool
    observed_at: datetime | None


@dataclass(frozen=True)
class RiskAssessment:
    zone_id: str
    hazard_type: HazardType
    level: RiskLevel
    confidence: float  # 0.0-1.0
    contributing_factors: list[str]
    data_sources: dict[str, str]  # source name -> status ("live" | "stale" | "unavailable")
    computed_at: datetime
    valid_from: datetime
    valid_to: datetime
    model_version: str = MODEL_VERSION
    is_degraded: bool = False  # True if any feed was stale/missing — frontend must
    # surface this, not hide it (§8.4 non-negotiable rule)


def _is_fresh(observed_at: datetime | None, now: datetime) -> bool:
    if observed_at is None:
        return False
    return (now - observed_at) <= MAX_READING_AGE


def evaluate_zone_risk(
    config: ZoneThresholdConfig,
    rainfall: RainfallReading,
    river: RiverLevelReading,
    dam_flag: DamReleaseFlag | None,
    *,
    now: datetime | None = None,
    recompute_interval: timedelta = timedelta(minutes=15),
) -> RiskAssessment:
    """Evaluate a single zone. Pure function — no I/O — so it's trivially
    unit-testable and reusable regardless of what the ingestion job looks like."""

    now = now or datetime.now(timezone.utc)

    rainfall_fresh = _is_fresh(rainfall.observed_at, now)
    river_fresh = _is_fresh(river.observed_at, now)
    dam_active = bool(dam_flag and dam_flag.active and _is_fresh(dam_flag.observed_at, now))

    data_sources = {
        "rainfall": "live" if rainfall_fresh else ("stale" if rainfall.observed_at else "unavailable"),
        "river_level": "live" if river_fresh else ("stale" if river.observed_at else "unavailable"),
    }
    is_degraded = not (rainfall_fresh and river_fresh)

    # Fail-safe: if BOTH feeds are down, we cannot respons ibly assess risk.
    # Emit UNKNOWN-as-LOW-with-zero-confidence is explicitly wrong per §8.4 —
    # instead the caller must surface "source unavailable", so we mark maximum
    # degradation and let the frontend refuse to render a colour without this
    # being visibly flagged.
    if not rainfall_fresh and not river_fresh:
        return RiskAssessment(
            zone_id=config.zone_id,
            hazard_type=config.hazard_type,
            level=RiskLevel.LOW,
            confidence=0.0,
            contributing_factors=["no live data: rainfall and river feeds both unavailable"],
            data_sources=data_sources,
            computed_at=now,
            valid_from=now,
            valid_to=now + recompute_interval,
            is_degraded=True,
        )

    rainfall_mm = rainfall.observed_mm_6h if rainfall_fresh else None
    river_m = river.level_m if river_fresh else None

    factors: list[str] = []
    level = RiskLevel.LOW

    rainfall_warning = rainfall_mm is not None and rainfall_mm >= config.rainfall_6h_warning_mm
    rainfall_critical = rainfall_mm is not None and rainfall_mm >= config.rainfall_6h_critical_mm
    river_warning = river_m is not None and river_m >= config.river_level_warning_m
    river_critical = river_m is not None and river_m >= config.river_level_critical_m

    if rainfall_warning:
        factors.append(f"6h rainfall {rainfall_mm:.0f}mm >= warning threshold {config.rainfall_6h_warning_mm:.0f}mm")
    if river_warning:
        factors.append(f"river level {river_m:.2f}m >= warning threshold {config.river_level_warning_m:.2f}m")

    if rainfall_warning and river_warning:
        level = RiskLevel.WARNING
    elif rainfall_warning or river_warning:
        level = RiskLevel.WATCH

    if rainfall_critical and river_critical:
        level = RiskLevel.CRITICAL
        factors.append("both rainfall and river level exceed critical thresholds")

    if dam_active and config.dam_release_forces_critical:
        level = RiskLevel.CRITICAL
        factors.append("active dam-release flag")

    if not factors:
        factors.append("no thresholds exceeded")

    # Confidence: full if both feeds fresh, reduced if operating on a single
    # feed (still emitted, but frontend must show the reduced-confidence
    # fail-safe state per spec §11.1 / the AI Engineer's confidence-values
    # ownership in §13.3).
    confidence = 1.0 if not is_degraded else 0.6

    return RiskAssessment(
        zone_id=config.zone_id,
        hazard_type=config.hazard_type,
        level=level,
        confidence=confidence,
        contributing_factors=factors,
        data_sources=data_sources,
        computed_at=now,
        valid_from=now,
        valid_to=now + recompute_interval,
        is_degraded=is_degraded,
    )


if __name__ == "__main__":
    # Minimal smoke test / usage example.
    now = datetime.now(timezone.utc)
    cfg = ZoneThresholdConfig(
        zone_id="pilot-district-zone-1",
        hazard_type=HazardType.RIVER_FLOOD,
        rainfall_6h_warning_mm=40,
        rainfall_6h_critical_mm=80,
        river_level_warning_m=3.5,
        river_level_critical_m=4.5,
    )
    rainfall = RainfallReading(cfg.zone_id, observed_mm_6h=55, forecast_mm_6h=20, observed_at=now)
    river = RiverLevelReading(cfg.zone_id, level_m=3.8, observed_at=now)
    assessment = evaluate_zone_risk(cfg, rainfall, river, dam_flag=None, now=now)
    print(assessment)
