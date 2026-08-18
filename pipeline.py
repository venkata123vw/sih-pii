"""
pipeline.py — P5's orchestration layer.

Right now every stage below is a STUB: it returns fake data shaped exactly
like what P1 (detection), P2 (extraction), P3 (scoring/policy) and P4
(redaction) will eventually hand off, per contracts.md.

When a teammate's real module is ready, replace ONLY that function body
(e.g. swap `extract_stub` for `ingestion.extract`) — nothing else in this
file, or in app.py, needs to change, because the shape stays the same.
"""

import random
import time

# ---------------------------------------------------------------------
# Config the UI needs
# ---------------------------------------------------------------------

PROFILES = ["PUBLIC_DISCLOSURE", "THIRD_PARTY_SERVICE", "REGULATED_KYC", "INTERNAL_REVIEW"]

# profiles.yaml stand-in (P6/P3 own the real version)
POLICY_MATRIX = {
    "AADHAAR":      {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "REMOVE", "REGULATED_KYC": "MASK", "INTERNAL_REVIEW": "FLAG"},
    "PAN":          {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "REMOVE", "REGULATED_KYC": "KEEP", "INTERNAL_REVIEW": "FLAG"},
    "DL":           {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "MASK",   "REGULATED_KYC": "MASK", "INTERNAL_REVIEW": "FLAG"},
    "CREDIT_CARD":  {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "REMOVE", "REGULATED_KYC": "MASK", "INTERNAL_REVIEW": "FLAG"},
    "PHONE":        {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "KEEP",   "REGULATED_KYC": "KEEP", "INTERNAL_REVIEW": "FLAG"},
    "EMAIL":        {"PUBLIC_DISCLOSURE": "REMOVE", "THIRD_PARTY_SERVICE": "KEEP",   "REGULATED_KYC": "KEEP", "INTERNAL_REVIEW": "FLAG"},
}

# which types this profile never needs -> feeds the excess-PII alert
EXCESS_RULES = {
    "PUBLIC_DISCLOSURE": {"AADHAAR", "PAN", "DL", "CREDIT_CARD", "PHONE", "EMAIL"},
    "THIRD_PARTY_SERVICE": {"AADHAAR", "CREDIT_CARD"},
    "REGULATED_KYC": {"CREDIT_CARD"},
    "INTERNAL_REVIEW": set(),
}


# ---------------------------------------------------------------------
# Stub: P2 — extraction (OCR / text layer)
# ---------------------------------------------------------------------
def extract_stub(file_bytes, filename):
    time.sleep(0.3)
    source_type = "scanned_image" if filename.lower().endswith((".jpg", ".jpeg", ".png")) else "native_pdf"
    return {
        "doc_id": "stub-doc-001",
        "source_type": source_type,
        "pages": [
            {
                "page_num": 0,
                "width": 1240,
                "height": 1754,
                "tokens": [
                    {"text": "1234", "bbox": [100, 150, 260, 190], "ocr_conf": 0.95},
                    {"text": "5678", "bbox": [270, 150, 430, 190], "ocr_conf": 0.95},
                    {"text": "9012", "bbox": [440, 150, 600, 190], "ocr_conf": 0.95},
                ],
                "full_text": "Sample extracted text containing Aadhaar 1234 5678 9012, "
                             "PAN ABCPD1234E, phone 9876543210, email demo@example.com",
            }
        ],
    }


# ---------------------------------------------------------------------
# Stub: P1 — detection engine (regex + checksum)
# ---------------------------------------------------------------------
def detect_stub(extraction):
    time.sleep(0.3)
    return {
        "doc_id": extraction["doc_id"],
        "candidates": [
            {"pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
             "bbox": [100, 150, 600, 190], "checksum_valid": True, "match_source": "regex"},
            {"pii_type": "PAN", "value": "ABCPD1234E", "page_num": 0,
             "bbox": [100, 220, 400, 260], "checksum_valid": True, "match_source": "regex"},
            {"pii_type": "PHONE", "value": "9876543210", "page_num": 0,
             "bbox": [100, 290, 350, 330], "checksum_valid": None, "match_source": "regex"},
            {"pii_type": "EMAIL", "value": "demo@example.com", "page_num": 0,
             "bbox": [100, 360, 450, 400], "checksum_valid": None, "match_source": "regex"},
        ],
    }


# ---------------------------------------------------------------------
# Stub: P3 — scoring + policy resolution
# ---------------------------------------------------------------------
def score_stub(candidates, profile):
    time.sleep(0.3)
    detections = []
    excess = {}
    for c in candidates["candidates"]:
        ptype = c["pii_type"]
        action = POLICY_MATRIX.get(ptype, {}).get(profile, "FLAG")
        is_excess = ptype in EXCESS_RULES.get(profile, set())
        necessity = "EXCESS" if is_excess else ("REQUIRED" if action == "KEEP" else "OPTIONAL")
        conf = round(random.uniform(0.85, 0.99), 2)

        detections.append({
            **c,
            "confidence": conf,
            "policy_action": action,
            "necessity": necessity,
            "reasons": ["checksum_pass" if c["checksum_valid"] else "pattern_match",
                        f"policy:{profile.lower()}_default"],
            "user_confirmed": action in ("REMOVE", "MASK"),  # defaults to policy recommendation
            "mask_reveal_last": 4 if action == "MASK" else 0,
        })
        if is_excess:
            excess[ptype] = excess.get(ptype, 0) + 1

    return {
        "doc_id": candidates["doc_id"],
        "context_profile": profile,
        "detections": detections,
        "excess_pii_alert": [{"pii_type": k, "count": v} for k, v in excess.items()],
    }


# ---------------------------------------------------------------------
# Stub: P4 — redaction engine
# ---------------------------------------------------------------------
def redact_stub(file_bytes, confirmed_detections):
    time.sleep(0.3)
    removed = sum(1 for d in confirmed_detections if d["user_confirmed"] and d["policy_action"] == "REMOVE")
    masked = sum(1 for d in confirmed_detections if d["user_confirmed"] and d["policy_action"] == "MASK")
    kept = sum(1 for d in confirmed_detections if not d["user_confirmed"] or d["policy_action"] == "KEEP")

    # stub: pass the original bytes straight through, tagged so it's obvious
    # this isn't real redaction yet
    output_bytes = file_bytes

    report = {
        "removed": removed,
        "masked": masked,
        "kept": kept,
        "flagged": sum(1 for d in confirmed_detections if d["policy_action"] == "FLAG"),
    }
    return output_bytes, report


# ---------------------------------------------------------------------
# Public orchestration — analyze() / apply() split (section 3c)
# ---------------------------------------------------------------------
def analyze(file_bytes, filename, profile,
            extract_fn=extract_stub, detect_fn=detect_stub, score_fn=score_stub):
    """Runs extract -> detect -> score. Returns findings for user review.
    Nothing is written to disk / modified at this stage."""
    extraction = extract_fn(file_bytes, filename)
    candidates = detect_fn(extraction)
    scored = score_fn(candidates, profile)
    return scored


def apply(file_bytes, confirmed_detections, redact_fn=redact_stub):
    """Takes ONLY user-confirmed detections and produces the redacted output.
    Nothing unconfirmed is touched."""
    return redact_fn(file_bytes, confirmed_detections)


def analyze_pasted_text(text, profile, score_fn=score_stub):
    """Same pipeline for the paste-text entry path (P5 item 9) — skips
    extraction since there's no file, but still runs detect -> score."""
    fake_extraction = {
        "doc_id": "pasted-text",
        "source_type": "plain_text",
        "pages": [{"page_num": 0, "width": 0, "height": 0, "tokens": [], "full_text": text}],
    }
    candidates = detect_stub(fake_extraction)
    return score_fn(candidates, profile)
