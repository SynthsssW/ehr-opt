"""
priority_scoring.py
-------------------
Pure, side-effect-free scoring logic for the EHR-Opt priority list.

Keeping this separate from the FHIR/network code means the scoring rules
can be unit-tested in isolation and reused by both the CLI and the
Streamlit dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- Severity tiers ---------------------------------------------------------
# A tier is chosen from the total score. Thresholds are inclusive on the low
# end (score >= 10 -> CRITICAL, etc.).
TIER_CRITICAL = "🔴 CRITICAL"
TIER_URGENT = "🟡 URGENT"
TIER_STABLE = "🟢 STABLE"


@dataclass
class Vitals:
    """Latest vital signs for a single patient/encounter.

    Any field may be None when the corresponding Observation is missing in
    the sandbox data — the scoring functions treat None as "no contribution".
    """

    heart_rate: Optional[float] = None          # beats per minute (bpm)
    o2_saturation: Optional[float] = None        # percent (%)
    systolic_bp: Optional[float] = None          # mmHg
    diastolic_bp: Optional[float] = None          # mmHg (display only)

    def bp_display(self) -> str:
        """Human-readable blood pressure, e.g. '120/80' or 'N/A'."""
        if self.systolic_bp is None and self.diastolic_bp is None:
            return "N/A"
        sys_s = f"{self.systolic_bp:.0f}" if self.systolic_bp is not None else "?"
        dia_s = f"{self.diastolic_bp:.0f}" if self.diastolic_bp is not None else "?"
        return f"{sys_s}/{dia_s}"


# --- Individual scoring rules ----------------------------------------------
# Each rule mirrors one row of the scoring table in the project brief and
# returns (points, reason) so the UI can explain *why* a patient scored.

def score_heart_rate(hr: Optional[float]) -> tuple[int, Optional[str]]:
    """Heart Rate > 140 bpm = 10 (Critical); 100-140 bpm = 5 (Urgent)."""
    if hr is None:
        return 0, None
    if hr > 140:
        return 10, f"HR {hr:.0f} bpm (>140, critical)"
    if hr >= 100:
        return 5, f"HR {hr:.0f} bpm (100-140, urgent)"
    return 0, None


def score_o2_saturation(spo2: Optional[float]) -> tuple[int, Optional[str]]:
    """O2 Saturation < 90% = 10 (Critical); 90-94% = 6 (Urgent)."""
    if spo2 is None:
        return 0, None
    if spo2 < 90:
        return 10, f"SpO2 {spo2:.0f}% (<90, critical)"
    if spo2 <= 94:
        return 6, f"SpO2 {spo2:.0f}% (90-94, urgent)"
    return 0, None


def score_systolic_bp(sbp: Optional[float]) -> tuple[int, Optional[str]]:
    """Systolic BP < 90 mmHg = 10 (Critical); 90-100 mmHg = 5 (Urgent)."""
    if sbp is None:
        return 0, None
    if sbp < 90:
        return 10, f"SBP {sbp:.0f} mmHg (<90, critical)"
    if sbp <= 100:
        return 5, f"SBP {sbp:.0f} mmHg (90-100, urgent)"
    return 0, None


@dataclass
class ScoreResult:
    total: int
    tier: str
    reasons: list[str] = field(default_factory=list)


def tier_for_score(score: int) -> str:
    """Map a numeric score to a severity tier."""
    if score >= 10:
        return TIER_CRITICAL
    if score >= 5:
        return TIER_URGENT
    return TIER_STABLE


def score_vitals(vitals: Vitals) -> ScoreResult:
    """Combine the individual rules into a total score, tier, and reasons."""
    total = 0
    reasons: list[str] = []
    for points, reason in (
        score_heart_rate(vitals.heart_rate),
        score_o2_saturation(vitals.o2_saturation),
        score_systolic_bp(vitals.systolic_bp),
    ):
        total += points
        if reason:
            reasons.append(reason)
    return ScoreResult(total=total, tier=tier_for_score(total), reasons=reasons)
