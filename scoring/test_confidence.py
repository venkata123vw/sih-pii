from scoring import confidence

AADHAAR_PAGE = {
    "page_num": 0, "width": 1240, "height": 1754,
    "tokens": [
        {"text": "1234", "bbox": [100, 200, 160, 230], "ocr_conf": 0.95},
        {"text": "5678", "bbox": [165, 200, 225, 230], "ocr_conf": 0.95},
        {"text": "9012", "bbox": [230, 200, 290, 230], "ocr_conf": 0.55},
    ],
    "full_text": "Government of India\nAadhaar 1234 5678 9012",
}
AADHAAR_CTX = {"doc_id": "d1", "pages": [AADHAAR_PAGE]}
AADHAAR_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
    "bbox": [100, 200, 290, 230], "checksum_valid": True, "match_source": "regex",
}

# checksum(+0.4) + keyword(+0.25) + doc_type_boost(+0.1), avg ocr_conf ~0.82 (no dampen)
score = confidence.score(AADHAAR_CANDIDATE, AADHAAR_CTX)
assert abs(score - 0.75) < 1e-9

reasons = confidence.signal_reasons(AADHAAR_CANDIDATE, AADHAAR_CTX)
assert "checksum_pass" in reasons
assert "keyword_nearby:aadhaar" in reasons
assert "doc_type_boost" in reasons

INVOICE_PAGE = {
    "page_num": 0, "width": 1240, "height": 1754, "tokens": [],
    "full_text": "INVOICE DOCUMENT\nInvoice Number: 123456789012\nAmount: 1499 INR",
}
INVOICE_CTX = {"doc_id": "d2", "pages": [INVOICE_PAGE]}
INVOICE_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "123456789012", "page_num": 0,
    "bbox": [0, 0, 1, 1], "checksum_valid": False, "match_source": "regex",
}

# checksum fail(-0.5) + negative signal(-0.3) -> clamped to 0.0, not negative
score = confidence.score(INVOICE_CANDIDATE, INVOICE_CTX)
assert score == 0.0

reasons = confidence.signal_reasons(INVOICE_CANDIDATE, INVOICE_CTX)
assert "checksum_fail" in reasons
assert any(r.startswith("negative_signal:") for r in reasons)

# Low OCR confidence dampens an otherwise-positive score
LOW_OCR_PAGE = {
    "page_num": 0, "width": 100, "height": 100,
    "tokens": [{"text": "x", "bbox": [0, 0, 10, 10], "ocr_conf": 0.5}],
    "full_text": "Aadhaar card number here",
}
LOW_OCR_CTX = {"doc_id": "d3", "pages": [LOW_OCR_PAGE]}
LOW_OCR_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "card number", "page_num": 0,
    "bbox": [0, 0, 10, 10], "checksum_valid": True, "match_source": "regex",
}
# checksum(+0.4) + keyword(+0.25) = 0.65, then *= 0.5 ocr_conf -> 0.325
score = confidence.score(LOW_OCR_CANDIDATE, LOW_OCR_CTX)
assert abs(score - 0.325) < 1e-9

# NER match_source is capped at 0.5 even when raw signals sum higher
NER_CANDIDATE = {
    "pii_type": "NAME", "value": "1234 5678 9012", "page_num": 0,
    "bbox": [100, 200, 290, 230], "checksum_valid": True, "match_source": "ner",
}
score = confidence.score(NER_CANDIDATE, AADHAAR_CTX)
assert score == 0.5

# Regression: a bare NER hit with NO other signal must land AT the
# ceiling (0.5), not at 0 -- previously the ceiling only capped, never
# provided a base, so every clean NER detection silently scored 0.0.
CLEAN_NAME_PAGE = {"pages": [{"page_num": 0, "width": 100, "height": 100,
                              "tokens": [], "full_text": "Matthew Davis"}]}
CLEAN_NAME_CANDIDATE = {
    "pii_type": "NAME", "value": "Matthew Davis", "page_num": 0,
    "bbox": None, "checksum_valid": None, "match_source": "ner",
}
assert confidence.score(CLEAN_NAME_CANDIDATE, CLEAN_NAME_PAGE) == 0.5
assert "ner_match" in confidence.signal_reasons(CLEAN_NAME_CANDIDATE, CLEAN_NAME_PAGE)

# A negative signal can still pull an NER hit below the ceiling
NOISY_NAME_PAGE = {"pages": [{"page_num": 0, "width": 100, "height": 100,
                              "tokens": [], "full_text": "Invoice: Wireless Keyboard"}]}
NOISY_NAME_CANDIDATE = {
    "pii_type": "NAME", "value": "Wireless Keyboard", "page_num": 0,
    "bbox": None, "checksum_valid": None, "match_source": "ner",
}
score = confidence.score(NOISY_NAME_CANDIDATE, NOISY_NAME_PAGE)
assert abs(score - 0.2) < 1e-9   # 0.5 base - 0.3 negative signal

# --- PAN signals (detection.pan.pan_signals()): PAN has no checksum, so
# entity-code/serial plausibility feed confidence as signals, not a gate.
def _pan_page(text):
    return {"pages": [{"page_num": 0, "width": 100, "height": 100, "tokens": [], "full_text": text}]}

# Known entity code (P), nonzero serial -> keyword match only, no PAN penalty
clean_pan = {"pii_type": "PAN", "value": "ALWPG5809L", "page_num": 0,
             "bbox": None, "checksum_valid": None, "match_source": "regex"}
score = confidence.score(clean_pan, _pan_page("PAN Number: ALWPG5809L"))
assert abs(score - 0.25) < 1e-9
assert "pan_unknown_entity_code" not in confidence.signal_reasons(clean_pan, _pan_page("PAN Number: ALWPG5809L"))

# Unknown entity code ('D' is not an ITD entity code) -> -0.15
unknown_entity_pan = {"pii_type": "PAN", "value": "ABCDE1234F", "page_num": 0,
                       "bbox": None, "checksum_valid": None, "match_source": "regex"}
ctx = _pan_page("PAN Number: ABCDE1234F")
score = confidence.score(unknown_entity_pan, ctx)
assert abs(score - (0.25 - 0.15)) < 1e-9
assert "pan_unknown_entity_code" in confidence.signal_reasons(unknown_entity_pan, ctx)

# Zero serial ('0000') -> -0.25
zero_serial_pan = {"pii_type": "PAN", "value": "ALWPP0000L", "page_num": 0,
                    "bbox": None, "checksum_valid": None, "match_source": "regex"}
ctx = _pan_page("PAN Number: ALWPP0000L")
score = confidence.score(zero_serial_pan, ctx)
assert abs(score - (0.25 - 0.25)) < 1e-9
assert "pan_zero_serial" in confidence.signal_reasons(zero_serial_pan, ctx)

# Both penalties stack, clamped to 0 rather than going negative
both_pan = {"pii_type": "PAN", "value": "ABCDE0000F", "page_num": 0,
            "bbox": None, "checksum_valid": None, "match_source": "regex"}
ctx = _pan_page("PAN Number: ABCDE0000F")
assert confidence.score(both_pan, ctx) == 0.0
reasons = confidence.signal_reasons(both_pan, ctx)
assert "pan_unknown_entity_code" in reasons and "pan_zero_serial" in reasons

# Non-PAN candidates are never touched by the PAN signal path
assert "pan_unknown_entity_code" not in confidence.signal_reasons(AADHAAR_CANDIDATE, AADHAAR_CTX)

print("All confidence tests passed")
