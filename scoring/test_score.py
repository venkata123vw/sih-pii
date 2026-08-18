from detection.detect import detect
from scoring.score import score

PAGE_CTX = {
    "doc_id": "abc123",
    "source_type": "scanned_image",
    "pages": [{
        "page_num": 0, "width": 1240, "height": 1754,
        "tokens": [
            {"text": "1234", "bbox": [100, 200, 160, 230], "ocr_conf": 0.95},
            {"text": "5678", "bbox": [165, 200, 225, 230], "ocr_conf": 0.95},
            {"text": "9012", "bbox": [230, 200, 290, 230], "ocr_conf": 0.95},
        ],
        "full_text": "Government of India\nAadhaar 1234 5678 9012",
    }],
}
CANDIDATES_PAYLOAD = {
    "doc_id": "abc123",
    "candidates": [{
        "pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
        "bbox": [100, 200, 290, 230], "checksum_valid": True, "match_source": "regex",
    }],
}

result = score(CANDIDATES_PAYLOAD, "THIRD_PARTY_SERVICE", PAGE_CTX)

assert result["doc_id"] == "abc123"
assert result["context_profile"] == "THIRD_PARTY_SERVICE"
assert len(result["detections"]) == 1

d = result["detections"][0]
# carried through unchanged from the candidate
assert d["pii_type"] == "AADHAAR"
assert d["value"] == "1234 5678 9012"
assert d["checksum_valid"] is True
# added by scoring
assert 0.0 <= d["confidence"] <= 1.0
assert d["policy_action"] == "REMOVE"       # policy/profiles.yaml: THIRD_PARTY_SERVICE.AADHAAR
assert d["necessity"] == "EXCESS"
assert "checksum_pass" in d["reasons"]
assert "policy:THIRD_PARTY_SERVICE:AADHAAR:REMOVE" in d["reasons"]

# excess_pii_alert aggregates EXCESS-necessity detections by type
assert result["excess_pii_alert"] == [{"pii_type": "AADHAAR", "count": 1}]

# score() works without page_ctx (matches pipeline.py's current call site:
# score(candidates, profile)), just with degraded confidence signals
result_no_ctx = score(CANDIDATES_PAYLOAD, "REGULATED_KYC")
assert result_no_ctx["detections"][0]["policy_action"] == "MASK"
assert result_no_ctx["detections"][0]["confidence"] < result["detections"][0]["confidence"]

# confidence and policy_action are computed independently -- never collapsed
assert "confidence" in d and "policy_action" in d and d["confidence"] != d["policy_action"]

# --- Pasted-text regression: exact shape pipeline.py's analyze_pasted_text()
# builds (tokens = [{"text": w} for w in text.split()], no bbox/ocr_conf at
# all). Real detection.detect() -> scoring.score() end to end, matching a
# reported bug where NER's bbox handling crashed on exactly this shape.
def _pasted(text: str) -> dict:
    tokens = [{"text": w} for w in text.split()]
    return {
        "doc_id": "pasted-text", "source_type": "plain_text",
        "pages": [{"page_num": 0, "width": 0, "height": 0, "tokens": tokens, "full_text": text}],
    }


for text in [
    "6563 2299 1528",                                    # valid Aadhaar alone
    "Email: taylor.synthetic@example.com",               # email
    "Phone: 9876543210",                                 # phone
    "Just a plain sentence with no identifiers at all",  # no PII
    "Contact Ravi Kumar at Mumbai regarding Aadhaar 6563 2299 1528",  # NER + regex together
]:
    extraction = _pasted(text)
    candidates = detect(extraction)
    result = score(candidates, "THIRD_PARTY_SERVICE", extraction)  # must not raise
    for detection in result["detections"]:
        assert detection["bbox"] is None   # coordinate-less source -> stays None, never invented

print("All score wiring tests passed")
