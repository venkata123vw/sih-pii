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

print("All confidence tests passed")
