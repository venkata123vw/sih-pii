"""
Policy lookup: given a detection + context profile, decide policy_action
and necessity. Lookup only -- no scoring logic lives here.
"""

from pathlib import Path

import yaml

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policy" / "profiles.yaml"

# necessity_for: is this pii_type actually needed for the document's
# purpose under this profile? First-draft mapping, not policy-reviewed.
# Falls back to OPTIONAL for anything not listed.
NECESSITY_MATRIX = {
    "REGULATED_KYC": {
        "AADHAAR": "REQUIRED", "PAN": "REQUIRED", "DL": "REQUIRED",
        "CREDIT_CARD": "OPTIONAL", "PHONE": "REQUIRED", "EMAIL": "REQUIRED",
        "NAME": "REQUIRED", "ADDRESS": "REQUIRED",
    },
    "THIRD_PARTY_SERVICE": {
        "AADHAAR": "EXCESS", "PAN": "EXCESS", "DL": "EXCESS",
        "CREDIT_CARD": "EXCESS", "PHONE": "OPTIONAL", "EMAIL": "OPTIONAL",
        "NAME": "OPTIONAL", "ADDRESS": "EXCESS",
    },
    "PUBLIC_DISCLOSURE": {
        "AADHAAR": "EXCESS", "PAN": "EXCESS", "DL": "EXCESS",
        "CREDIT_CARD": "EXCESS", "PHONE": "EXCESS", "EMAIL": "EXCESS",
        "NAME": "EXCESS", "ADDRESS": "EXCESS",
    },
    "INTERNAL_REVIEW": {
        "AADHAAR": "OPTIONAL", "PAN": "OPTIONAL", "DL": "OPTIONAL",
        "CREDIT_CARD": "OPTIONAL", "PHONE": "OPTIONAL", "EMAIL": "OPTIONAL",
        "NAME": "OPTIONAL", "ADDRESS": "OPTIONAL",
    },
}


def load_policy_matrix(path: Path = DEFAULT_POLICY_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def necessity_for(pii_type: str, profile: str) -> str:
    return NECESSITY_MATRIX.get(profile, {}).get(pii_type, "OPTIONAL")


def resolve(detection: dict, profile: str, policy_matrix: dict) -> tuple[str, str, list[str]]:
    pii_type = detection["pii_type"]
    action = policy_matrix.get(profile, {}).get(pii_type, "FLAG")
    necessity = necessity_for(pii_type, profile)
    reasons = [f"policy:{profile}:{pii_type}:{action}"]
    return action, necessity, reasons
