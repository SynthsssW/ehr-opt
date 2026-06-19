#!/usr/bin/env python3
"""
ehr_opt.py — EHR-Opt priority-list CLI
======================================

Connects to Epic's FHIR R4 sandbox, pulls active (in-progress) encounters,
scores each patient's latest vital signs, and prints a triage-style priority
list with the most critical patients at the top.

Usage
-----
    # Credentials are read from environment variables:
    export EPIC_CLIENT_ID="your-registered-client-id"
    export EPIC_PRIVATE_KEY_PATH="/path/to/private_key.pem"
    python ehr_opt.py

    # Or run against bundled synthetic data with no credentials:
    python ehr_opt.py --demo

The OAuth2 + FHIR plumbing lives in fhir_client.py; the scoring rules live in
priority_scoring.py. This file is just orchestration + presentation.
"""

from __future__ import annotations

import argparse
import os
import sys

from priority_scoring import TIER_CRITICAL, TIER_URGENT
from fhir_client import (
    FHIRClient,
    PatientCase,
    build_case,
    get_access_token,
)


# --- Credential loading -----------------------------------------------------
# CLIENT_ID and the private key are read from environment variables so that
# secrets never live in source control. Replace the env var names below if
# your deployment uses a secret manager instead.

def load_credentials() -> tuple[str, str]:
    """Return (client_id, private_key_pem) from the environment.

    Expected variables:
      EPIC_CLIENT_ID         — the client_id registered with Epic
      EPIC_PRIVATE_KEY_PATH  — path to the PEM private key file
                               (or EPIC_PRIVATE_KEY for the inline PEM string)
    """
    client_id = os.environ.get("EPIC_CLIENT_ID")
    key_path = os.environ.get("EPIC_PRIVATE_KEY_PATH")
    inline_key = os.environ.get("EPIC_PRIVATE_KEY")

    if not client_id:
        raise RuntimeError("EPIC_CLIENT_ID is not set.")

    if inline_key:
        private_key_pem = inline_key
    elif key_path:
        with open(key_path, "r", encoding="utf-8") as fh:
            private_key_pem = fh.read()
    else:
        raise RuntimeError(
            "Set EPIC_PRIVATE_KEY_PATH (file) or EPIC_PRIVATE_KEY (inline PEM)."
        )

    return client_id, private_key_pem


# --- Case retrieval ---------------------------------------------------------

def fetch_live_cases() -> list[PatientCase]:
    """Authenticate, query the sandbox, and build scored cases."""
    client_id, private_key_pem = load_credentials()
    print("Authenticating with Epic OAuth2 ...", file=sys.stderr)
    token = get_access_token(client_id, private_key_pem)

    client = FHIRClient(token)
    print("Querying active (in-progress) encounters ...", file=sys.stderr)
    encounters = client.get_active_encounters()

    cases: list[PatientCase] = []
    for enc in encounters:
        case = build_case(client, enc)
        if case is not None:
            cases.append(case)
    return cases


def get_cases(demo: bool) -> list[PatientCase]:
    """Return cases from the live sandbox, falling back to demo data."""
    if demo:
        from sample_data import sample_cases
        return sample_cases()
    try:
        return fetch_live_cases()
    except Exception as exc:  # noqa: BLE001 — surface any failure, then fall back
        print(f"\n[!] Live fetch failed: {exc}", file=sys.stderr)
        print("[!] Falling back to bundled synthetic data.\n", file=sys.stderr)
        from sample_data import sample_cases
        return sample_cases()


# --- Presentation -----------------------------------------------------------

def sort_cases(cases: list[PatientCase]) -> list[PatientCase]:
    """Sort by score descending so the most critical patients come first."""
    return sorted(cases, key=lambda c: c.score.total, reverse=True)


def print_priority_list(cases: list[PatientCase]) -> None:
    cases = sort_cases(cases)

    header = (
        f"{'PRIORITY':<12} {'SCORE':>5}  {'PATIENT':<22} {'MRN':<12} "
        f"{'HR':>5} {'SpO2':>5} {'BP':>9}"
    )
    line = "═" * len(header)
    print("\n" + line)
    print(f"{'EHR-OPT — ACTIVE CASE PRIORITY LIST':^{len(header)}}")
    print(line)
    print(header)
    print("─" * len(header))

    for c in cases:
        v = c.vitals
        hr = f"{v.heart_rate:.0f}" if v.heart_rate is not None else "—"
        spo2 = f"{v.o2_saturation:.0f}%" if v.o2_saturation is not None else "—"
        print(
            f"{c.score.tier:<11} {c.score.total:>5}  {c.name:<22} {c.mrn:<12} "
            f"{hr:>5} {spo2:>5} {v.bp_display():>9}"
        )
        if c.score.reasons:
            print(f"{'':<19}↳ " + "; ".join(c.score.reasons))

    print(line)

    n_crit = sum(1 for c in cases if c.score.tier == TIER_CRITICAL)
    n_urg = sum(1 for c in cases if c.score.tier == TIER_URGENT)
    n_stable = len(cases) - n_crit - n_urg
    print(
        f"Total: {len(cases)} active  |  "
        f"{n_crit} critical  |  {n_urg} urgent  |  {n_stable} stable\n"
    )


# --- Entry point ------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a triage priority list from Epic's FHIR sandbox."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use bundled synthetic data instead of calling the live sandbox.",
    )
    args = parser.parse_args(argv)

    cases = get_cases(demo=args.demo)
    if not cases:
        print("No active encounters found.")
        return 0

    print_priority_list(cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
