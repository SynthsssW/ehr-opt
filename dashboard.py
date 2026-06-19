"""
dashboard.py — EHR-Opt Streamlit dashboard
===========================================

A visual front-end for the same priority-scoring pipeline used by the CLI.

Run with:
    streamlit run dashboard.py

If EPIC_CLIENT_ID + a private key are configured (env vars or the sidebar),
the dashboard pulls live in-progress encounters from Epic's FHIR R4 sandbox.
Otherwise it renders bundled synthetic cases so the UI is always populated.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from priority_scoring import TIER_CRITICAL, TIER_URGENT, TIER_STABLE
from fhir_client import PatientCase
from ehr_opt import fetch_live_cases, sort_cases


st.set_page_config(page_title="EHR-Opt Priority Dashboard", page_icon="🏥",
                   layout="wide")


# --- Data loading -----------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_demo_cases() -> list[PatientCase]:
    from sample_data import sample_cases
    return sample_cases()


def load_cases(use_live: bool) -> tuple[list[PatientCase], str]:
    """Return (cases, source_label)."""
    if use_live:
        try:
            return fetch_live_cases(), "Live Epic FHIR sandbox"
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Live fetch failed, showing demo data. ({exc})")
    return _load_demo_cases(), "Bundled synthetic data"


def cases_to_dataframe(cases: list[PatientCase]) -> pd.DataFrame:
    rows = []
    for c in sort_cases(cases):
        v = c.vitals
        rows.append({
            "Priority": c.score.tier,
            "Score": c.score.total,
            "Patient": c.name,
            "MRN": c.mrn,
            "Heart Rate (bpm)": v.heart_rate,
            "SpO2 (%)": v.o2_saturation,
            "Blood Pressure": v.bp_display(),
            "Flags": "; ".join(c.score.reasons) or "—",
        })
    return pd.DataFrame(rows)


# --- Styling ----------------------------------------------------------------

def _row_style(row: pd.Series):
    colors = {
        TIER_CRITICAL: "background-color: #fdecea",
        TIER_URGENT: "background-color: #fff7e0",
        TIER_STABLE: "background-color: #eafaf0",
    }
    return [colors.get(row["Priority"], "")] * len(row)


# --- UI ---------------------------------------------------------------------

st.title("🏥 EHR-Opt — Active Case Priority Dashboard")
st.caption(
    "Triage view of in-progress encounters from Epic's FHIR R4 sandbox, "
    "ranked by a vital-signs priority score."
)

with st.sidebar:
    st.header("Data source")
    have_env = bool(os.environ.get("EPIC_CLIENT_ID")) and bool(
        os.environ.get("EPIC_PRIVATE_KEY_PATH")
        or os.environ.get("EPIC_PRIVATE_KEY")
    )
    use_live = st.toggle(
        "Use live Epic sandbox",
        value=have_env,
        help="Requires EPIC_CLIENT_ID and a private key in the environment.",
    )
    if use_live and not have_env:
        st.info("Set EPIC_CLIENT_ID and EPIC_PRIVATE_KEY_PATH to enable live data.")
    st.divider()
    st.subheader("Scoring rules")
    st.markdown(
        "- **HR** > 140 → 10 · 100–140 → 5\n"
        "- **SpO2** < 90 → 10 · 90–94 → 6\n"
        "- **Systolic BP** < 90 → 10 · 90–100 → 5\n\n"
        "**Tiers:** 🔴 ≥10 · 🟡 5–9 · 🟢 <5"
    )
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

cases, source = load_cases(use_live)
df = cases_to_dataframe(cases)

# --- Summary metrics --------------------------------------------------------
n_crit = int((df["Priority"] == TIER_CRITICAL).sum())
n_urg = int((df["Priority"] == TIER_URGENT).sum())
n_stable = int((df["Priority"] == TIER_STABLE).sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Active cases", len(df))
m2.metric("🔴 Critical", n_crit)
m3.metric("🟡 Urgent", n_urg)
m4.metric("🟢 Stable", n_stable)

st.caption(f"Source: {source}")

# --- Priority table ---------------------------------------------------------
st.subheader("Priority list")
styled = df.style.apply(_row_style, axis=1)
st.dataframe(styled, use_container_width=True, hide_index=True)

# --- Critical callouts ------------------------------------------------------
critical = df[df["Priority"] == TIER_CRITICAL]
if not critical.empty:
    st.subheader("🔴 Critical — immediate attention")
    for _, row in critical.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{row['Patient']}**  ·  MRN {row['MRN']}")
            c1.caption(row["Flags"])
            c2.metric("Score", row["Score"])

st.divider()
st.caption("EHR-Opt · educational demo against Epic's public FHIR sandbox.")
