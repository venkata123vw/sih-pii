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

# --- End-to-end VID false-positive regression (real detect() + score(),
# not hand-built candidates): reproduces an observed real-world false
# positive on a scanned Aadhaar card, where the VID (Virtual ID) field's
# tail digits got matched as a second AADHAAR candidate.
def _tok(text, i):
    return {"text": text, "bbox": [10 * i, 100, 10 * i + 40, 120], "ocr_conf": 1.0}


vid_words = ["Aadhaar", "2341", "2341", "2346", "VID", ":", "9111", "8122", "7978", "3936"]
vid_page = {
    "page_num": 0, "width": 1240, "height": 1754,
    "tokens": [_tok(w, i) for i, w in enumerate(vid_words)],
    "full_text": "Aadhaar 2341 2341 2346 VID : 9111 8122 7978 3936",
}
vid_extraction = {"doc_id": "vid-doc", "source_type": "scanned_image", "pages": [vid_page]}

vid_candidates = detect(vid_extraction)
# detection stays recall-biased -- both are still emitted as candidates,
# not suppressed here (see detection.pan's docstring for why the project
# favors recall over precision at this layer)
assert {c["value"] for c in vid_candidates["candidates"]} == {"2341 2341 2346", "8122 7978 3936"}

vid_result = score(vid_candidates, "THIRD_PARTY_SERVICE", vid_extraction)
by_value = {d["value"]: d for d in vid_result["detections"] if d["pii_type"] == "AADHAAR"}
assert by_value["2341 2341 2346"]["confidence"] > by_value["8122 7978 3936"]["confidence"]
assert "vid_adjacent" in by_value["8122 7978 3936"]["reasons"]
assert "vid_adjacent" not in by_value["2341 2341 2346"]["reasons"]

# --- Same VID problem, different type: on a second real card, the VID's
# digits matched PHONE instead of AADHAAR (a 12-digit substring starting
# "91" self-evidently reads as a +91-prefixed number). The original fix
# only gated AADHAAR -- this reproduces the exact real false positive
# that gap allowed through, and confirms PHONE is now covered too.
# "VID" itself also got picked up by NER as a spurious NAME here (a
# separate bug, fixed in ner.py's _NON_NAME_LABELS) -- confirmed absent.
vid_phone_words = ["Aadhaar", "6563", "2299", "1528", "VID", ":", "9168", "7651", "8239", "5143"]
vid_phone_page = {
    "page_num": 0, "width": 1240, "height": 1754,
    "tokens": [_tok(w, i) for i, w in enumerate(vid_phone_words)],
    "full_text": "Aadhaar 6563 2299 1528 VID : 9168 7651 8239 5143",
}
vid_phone_extraction = {"doc_id": "vid-phone-doc", "source_type": "scanned_image", "pages": [vid_phone_page]}

vid_phone_candidates = detect(vid_phone_extraction)
assert {c["pii_type"] for c in vid_phone_candidates["candidates"]} == {"AADHAAR", "PHONE"}

vid_phone_result = score(vid_phone_candidates, "THIRD_PARTY_SERVICE", vid_phone_extraction)
aadhaar = next(d for d in vid_phone_result["detections"] if d["pii_type"] == "AADHAAR")
phone = next(d for d in vid_phone_result["detections"] if d["pii_type"] == "PHONE")
assert aadhaar["value"] == "6563 2299 1528"
assert phone["value"] == "9168 7651 8239"
assert "vid_adjacent" in phone["reasons"]
assert aadhaar["confidence"] > phone["confidence"]
assert not any(d["value"].strip().lower() == "vid" for d in vid_phone_result["detections"])

print("All score wiring tests passed")
