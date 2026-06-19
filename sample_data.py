"""
sample_data.py
--------------
Synthetic patient cases used when no Epic credentials are configured.

This lets the CLI and the Streamlit dashboard demonstrate the full
priority-scoring pipeline offline, without hitting the live sandbox. The
numbers are chosen to land in each severity tier.
"""

from fhir_client import PatientCase
from priority_scoring import Vitals, score_vitals


def _case(name, mrn, pid, enc, hr, spo2, sbp, dbp):
    vitals = Vitals(
        heart_rate=hr, o2_saturation=spo2, systolic_bp=sbp, diastolic_bp=dbp
    )
    return PatientCase(
        name=name, mrn=mrn, patient_id=pid, encounter_id=enc,
        vitals=vitals, score=score_vitals(vitals),
    )


def sample_cases() -> list[PatientCase]:
    return [
        _case("Theodore Mychart", "MRN-100021", "eXY1", "encA",
              hr=152, spo2=86, sbp=84, dbp=52),     # critical on all three
        _case("Camila Lopez", "MRN-100007", "eXY2", "encB",
              hr=118, spo2=92, sbp=128, dbp=80),    # urgent HR + urgent SpO2
        _case("Warren Mcginnis", "MRN-100013", "eXY3", "encC",
              hr=88, spo2=97, sbp=95, dbp=64),       # urgent low BP only
        _case("Derrick Lin", "MRN-100002", "eXY4", "encD",
              hr=72, spo2=99, sbp=120, dbp=78),      # stable
        _case("Olivia Roberts", "MRN-100045", "eXY5", "encE",
              hr=134, spo2=88, sbp=110, dbp=70),     # urgent HR + critical SpO2
    ]
