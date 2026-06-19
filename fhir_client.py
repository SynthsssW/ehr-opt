"""
fhir_client.py
--------------
A thin client for Epic's FHIR R4 sandbox.

Handles two things:
  1. OAuth2 authentication using Epic's "backend services" JWT flow
     (a private key signs a client-assertion JWT; Epic returns an access
     token). See: https://fhir.epic.com/Documentation?docId=oauth2&section=BackendOAuth2Guide
  2. Convenience queries for the Encounter and Observation endpoints, plus
     a helper that resolves an Encounter into a scored patient case.

Network access to the live sandbox requires a *registered* CLIENT_ID and the
matching private key. Without them the CLI falls back to bundled sample data
so the tool (and the dashboard) still demonstrate the full pipeline.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

# `requests` and `authlib` are imported lazily inside the functions that need
# them, so the offline `--demo` path works even if they aren't installed.

from priority_scoring import Vitals, ScoreResult, score_vitals


# Base URL for Epic's public FHIR R4 sandbox.
FHIR_BASE_URL = "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
TOKEN_URL = "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token"

# LOINC codes used to recognise the vital signs we care about.
LOINC_HEART_RATE = {"8867-4"}
LOINC_O2_SAT = {"2708-6", "59408-5"}          # SpO2 (and pulse-ox variant)
LOINC_BP_PANEL = {"85354-9", "55284-4"}        # blood pressure panel
LOINC_SYSTOLIC = {"8480-6"}
LOINC_DIASTOLIC = {"8462-4"}


@dataclass
class PatientCase:
    """One row of the priority list."""

    name: str
    mrn: str
    patient_id: str
    encounter_id: str
    vitals: Vitals
    score: ScoreResult


# --- Authentication ---------------------------------------------------------

def get_access_token(client_id: str, private_key_pem: str) -> str:
    """Authenticate via the JWT client-assertion flow and return a token.

    `private_key_pem` is the PEM-encoded RSA private key whose public key was
    registered with Epic for this `client_id`.
    """
    import requests
    from authlib.jose import jwt

    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": TOKEN_URL,
        "jti": str(uuid.uuid4()),   # unique per request to prevent replay
        "iat": now,
        "exp": now + 300,            # Epic requires <= 5 minutes
    }
    # kid must match the key id published in our JWKS so Epic selects the
    # right public key to verify this assertion.
    header = {"alg": "RS384", "typ": "JWT", "kid": "ehr-opt-key-1"}
    assertion = jwt.encode(header, claims, private_key_pem)

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_assertion_type":
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion.decode("ascii"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# --- FHIR client ------------------------------------------------------------

class FHIRClient:
    """Minimal wrapper around requests for authenticated FHIR GETs."""

    def __init__(self, access_token: str, base_url: str = FHIR_BASE_URL):
        import requests

        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/fhir+json",
        })

    def _get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_active_encounters(self) -> list[dict[str, Any]]:
        """Query Encounter?status=in-progress and return the resources."""
        bundle = self._get("Encounter", {"status": "in-progress"})
        return [e["resource"] for e in bundle.get("entry", [])]

    def get_vital_observations(
        self, patient_id: str, encounter_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Fetch vital-signs Observations for a patient (optionally scoped to
        an encounter)."""
        params = {"patient": patient_id, "category": "vital-signs"}
        if encounter_id:
            params["encounter"] = encounter_id
        bundle = self._get("Observation", params)
        return [e["resource"] for e in bundle.get("entry", [])]

    def get_patient(self, patient_id: str) -> dict[str, Any]:
        return self._get(f"Patient/{patient_id}")


# --- FHIR parsing helpers ---------------------------------------------------

def _observation_codes(obs: dict[str, Any]) -> set[str]:
    return {
        c.get("code")
        for c in obs.get("code", {}).get("coding", [])
        if c.get("code")
    }


def _component_value(obs: dict[str, Any], codes: set[str]) -> Optional[float]:
    """Pull a numeric value from an Observation component matching `codes`."""
    for comp in obs.get("component", []):
        comp_codes = {
            c.get("code") for c in comp.get("code", {}).get("coding", [])
        }
        if comp_codes & codes:
            return comp.get("valueQuantity", {}).get("value")
    return None


def parse_vitals(observations: list[dict[str, Any]]) -> Vitals:
    """Reduce a list of Observation resources to a single Vitals snapshot.

    Observations are assumed to be sorted newest-first (Epic returns them in
    reverse-chronological order); the first match for each metric wins.
    """
    vitals = Vitals()
    for obs in observations:
        codes = _observation_codes(obs)
        value = obs.get("valueQuantity", {}).get("value")

        if codes & LOINC_HEART_RATE and vitals.heart_rate is None:
            vitals.heart_rate = value
        elif codes & LOINC_O2_SAT and vitals.o2_saturation is None:
            vitals.o2_saturation = value
        elif codes & LOINC_BP_PANEL:
            # Blood pressure is reported as a panel with two components.
            if vitals.systolic_bp is None:
                vitals.systolic_bp = _component_value(obs, LOINC_SYSTOLIC)
            if vitals.diastolic_bp is None:
                vitals.diastolic_bp = _component_value(obs, LOINC_DIASTOLIC)
    return vitals


def _patient_name(patient: dict[str, Any]) -> str:
    names = patient.get("name", [])
    if not names:
        return "Unknown"
    name = names[0]
    if name.get("text"):
        return name["text"]
    given = " ".join(name.get("given", []))
    return f"{given} {name.get('family', '')}".strip() or "Unknown"


def _patient_mrn(patient: dict[str, Any]) -> str:
    for ident in patient.get("identifier", []):
        type_text = ident.get("type", {}).get("text", "").upper()
        if "MR" in type_text or "MRN" in type_text:
            return ident.get("value", "N/A")
    # Fall back to the first identifier if none is explicitly an MRN.
    idents = patient.get("identifier", [])
    return idents[0].get("value", "N/A") if idents else "N/A"


def build_case(
    client: FHIRClient, encounter: dict[str, Any]
) -> Optional[PatientCase]:
    """Turn one Encounter resource into a fully scored PatientCase."""
    patient_ref = encounter.get("subject", {}).get("reference", "")
    patient_id = patient_ref.split("/")[-1]
    if not patient_id:
        return None

    patient = client.get_patient(patient_id)
    observations = client.get_vital_observations(patient_id, encounter.get("id"))
    vitals = parse_vitals(observations)

    return PatientCase(
        name=_patient_name(patient),
        mrn=_patient_mrn(patient),
        patient_id=patient_id,
        encounter_id=encounter.get("id", ""),
        vitals=vitals,
        score=score_vitals(vitals),
    )
