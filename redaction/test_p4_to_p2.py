"""
Real P2 -> P1 -> P3 -> P4 integration test.

P4 consumes the actual return value of scoring.score.score()
verbatim. No simulated detection dictionary is used.
"""

import pymupdf

from ingestion.extract import extract
from detection.detect import detect
from scoring.score import score
from redact import apply_redactions


INPUT_PDF = "testdata/documents/test.pdf"
OUTPUT_PDF = "testdata/documents/integration_redacted.pdf"


def test_real_p3_to_p4_contract():

    # P2: real extraction
    extraction = extract(INPUT_PDF)

    assert extraction["doc_id"]
    assert extraction["pages"]

    # P1: real detection
    candidates = detect(extraction)

    assert candidates["doc_id"] == extraction["doc_id"]
    assert "candidates" in candidates

    print("\nREAL P1 DETECTION OUTPUT:")
    for candidate in candidates["candidates"]:
        print(
            candidate["pii_type"],
            candidate["value"],
            candidate["page_num"],
            candidate["bbox"],
            candidate["checksum_valid"],
            candidate["match_source"],
        )

    # P3: real scoring
    scored = score(
        candidates,
        profile="THIRD_PARTY_SERVICE",
        page_ctx=extraction,
    )

    assert scored["doc_id"] == extraction["doc_id"]
    assert scored["context_profile"] == "THIRD_PARTY_SERVICE"
    assert "detections" in scored
    assert "excess_pii_alert" in scored

    print("\nREAL P3 SCORE OUTPUT:")
    for detection in scored["detections"]:
        print(
            detection["pii_type"],
            detection["value"],
            detection["page_num"],
            detection["bbox"],
            detection["policy_action"],
            detection["confidence"],
        )

    # Confirm the valid Aadhaar reached P3.
    aadhaar = "2341 2341 2346"

    aadhaar_detections = [
        d for d in scored["detections"]
        if d["value"] == aadhaar
    ]

    assert aadhaar_detections, (
        "Valid Aadhaar was not detected/scored. "
        "This is a P1/P2 issue, not a P4 redaction issue."
    )

    # P4 consumes the REAL P3 output verbatim.
    manifest = apply_redactions(
        INPUT_PDF,
        scored,
        OUTPUT_PDF,
    )

    assert manifest["verified"] is True
    assert manifest["doc_id"] == scored["doc_id"]

    # Verify resulting PDF.
    doc = pymupdf.open(OUTPUT_PDF)
    try:
        text = "".join(page.get_text() for page in doc)
    finally:
        doc.close()

    assert aadhaar not in text

    # Non-PII should remain.
    assert "Rithika" in text
    assert "rithika@example.com" in text

    print("\nPASS: real P2 -> P1 -> P3 -> P4 integration works.")
