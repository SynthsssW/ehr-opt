# EHR-Opt

A Python command-line tool (plus a Streamlit dashboard) that connects to
**Epic's FHIR R4 sandbox**, pulls active patient encounters, scores each
patient's latest vital signs, and produces a triage-style **priority list**
with the most critical cases at the top.

> ⚠️ Educational demo against Epic's *public* sandbox. Not for clinical use.

## What it does

1. **Authenticates** with Epic via the OAuth2 JWT "backend services" flow
   (a private key signs a client-assertion JWT; Epic returns an access token).
2. **Queries** `Encounter?status=in-progress` for active cases.
3. For each patient, **queries** `Observation?category=vital-signs` (scoped to
   the encounter) for the latest heart rate, blood pressure, and O₂ saturation.
4. **Scores** each case and assigns a severity tier.
5. **Displays** a sorted priority list — in the terminal or in the dashboard.

## Priority scoring

| Vital | Critical (10 pts) | Urgent |
|-------|-------------------|--------|
| Heart rate | > 140 bpm | 100–140 bpm → 5 pts |
| O₂ saturation | < 90% | 90–94% → 6 pts |
| Systolic BP | < 90 mmHg | 90–100 mmHg → 5 pts |

**Tiers:** 🔴 CRITICAL (score ≥ 10) · 🟡 URGENT (5–9) · 🟢 STABLE (< 5)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your Epic sandbox credentials
```

Credentials are read from environment variables (never hard-coded):

- `EPIC_CLIENT_ID` — your registered Epic client_id
- `EPIC_PRIVATE_KEY_PATH` — path to your PEM private key
  (or `EPIC_PRIVATE_KEY` for the inline PEM string)

## Usage

### CLI

```bash
# Against the live Epic sandbox (requires credentials):
python ehr_opt.py

# Offline demo with bundled synthetic data (no credentials needed):
python ehr_opt.py --demo
```

### Streamlit dashboard

```bash
streamlit run dashboard.py
```

The dashboard shows summary metrics, a color-coded priority table, and
critical-case callouts. Toggle **"Use live Epic sandbox"** in the sidebar when
credentials are configured; otherwise it renders synthetic data.

## Project layout

| File | Responsibility |
|------|----------------|
| `priority_scoring.py` | Pure scoring rules + severity tiers (unit-testable) |
| `fhir_client.py` | OAuth2 auth + FHIR Encounter/Observation queries + parsing |
| `ehr_opt.py` | CLI orchestration and terminal presentation |
| `dashboard.py` | Streamlit dashboard |
| `sample_data.py` | Synthetic cases for offline/demo runs |

## Notes on the live sandbox

Epic's public sandbox requires a `client_id` registered in the
[Epic on FHIR](https://fhir.epic.com/) developer portal with the matching
public key uploaded. The sandbox's test patients may not always have an
`in-progress` encounter with fresh vitals — in that case the priority list may
be empty, which is expected. Use `--demo` to see the full pipeline regardless.
