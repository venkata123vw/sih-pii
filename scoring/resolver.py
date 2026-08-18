"""
Policy lookup: given a detection + context profile, decide policy_action
and necessity. Lookup only -- no scoring logic lives here.
"""

from pathlib import Path

import yaml

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policy" / "profiles.yaml"

# necessity_for: is this pii_type actually needed for the document's
# purpose under this profile? Falls back to OPTIONAL for anything not
# listed.
#
# REGULATED_KYC: most types are REQUIRED here because KYC verification
# genuinely needs them present and legible -- necessity ("is it needed")
# is intentionally a separate axis from policy_action ("what happens to
# it"). policy/profiles.yaml MASKs the government IDs (AADHAAR, DL,
# CREDIT_CARD) rather than fully exposing them, so a type can be both
# REQUIRED and still redacted down to a partial value; that's not a
# contradiction, it's the point of keeping the two axes separate. This
# row's specific REQUIRED/OPTIONAL split is the team's own judgment call,
# matched to the workplan but not independently reviewed by a compliance
# source (see DPDP_COMPLIANCE.md's "Known limitation" section).
NECESSITY_MATRIX = {
    "REGULATED_KYC": {
        "AADHAAR": "REQUIRED", "PAN": "REQUIRED", "DL": "REQUIRED",
        "CREDIT_CARD": "OPTIONAL", "PHONE": "REQUIRED", "EMAIL": "REQUIRED",
        "NAME": "REQUIRED", "ADDRESS": "REQUIRED",
    },
    # DL/ADDRESS are MASK (not REMOVE) in policy/profiles.yaml here, so
    # EXCESS ("never needed") would contradict masking-instead-of-removing.
    # NAME/EMAIL are REQUIRED per section 3b's own wording: "name and email
    # kept because the service legitimately needs them."
    "THIRD_PARTY_SERVICE": {
        "AADHAAR": "EXCESS", "PAN": "EXCESS", "DL": "OPTIONAL",
        "CREDIT_CARD": "EXCESS", "PHONE": "OPTIONAL", "EMAIL": "REQUIRED",
        "NAME": "REQUIRED", "ADDRESS": "OPTIONAL",
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
