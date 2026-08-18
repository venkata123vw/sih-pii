from scoring import context

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

INVOICE_PAGE = {
    "page_num": 0, "width": 1240, "height": 1754,
    "tokens": [],
    "full_text": "INVOICE DOCUMENT\nInvoice Number: 123456789012\nAmount: 1499 INR",
}
INVOICE_CTX = {"doc_id": "d2", "pages": [INVOICE_PAGE]}
INVOICE_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "123456789012", "page_num": 0,
    "bbox": [0, 0, 1, 1], "checksum_valid": False, "match_source": "regex",
}

# keyword_proximity: finds nearby Aadhaar keyword
matched, kw = context.keyword_proximity(AADHAAR_PAGE["full_text"], AADHAAR_CANDIDATE["value"], "AADHAAR")
assert matched is True
assert kw == "aadhaar"

# keyword_proximity: no keyword nearby a bare invoice number
matched, kw = context.keyword_proximity(INVOICE_PAGE["full_text"], INVOICE_CANDIDATE["value"], "AADHAAR")
assert matched is False
assert kw is None

# negative_signal: "Invoice"/"Amount" nearby suppresses a false positive
matched, neg_kw = context.negative_signal(INVOICE_PAGE["full_text"], INVOICE_CANDIDATE["value"])
assert matched is True
assert neg_kw in ("invoice", "amount")

# negative_signal: no negative keyword nearby the real Aadhaar
matched, neg_kw = context.negative_signal(AADHAAR_PAGE["full_text"], AADHAAR_CANDIDATE["value"])
assert matched is False

# doc_type_boost: "Government of India" boosts the whole doc
assert context.doc_type_boost(AADHAAR_PAGE["full_text"]) is True
assert context.doc_type_boost(INVOICE_PAGE["full_text"]) is False

# ocr_confidence: averages overlapping token confidences
avg = context.ocr_confidence(AADHAAR_PAGE, AADHAAR_CANDIDATE["bbox"])
assert abs(avg - (0.95 + 0.95 + 0.55) / 3) < 1e-9

# ocr_confidence: None when no tokens overlap
assert context.ocr_confidence(INVOICE_PAGE, [9000, 9000, 9010, 9010]) is None

# get_signals: full bundle for the Aadhaar candidate
signals = context.get_signals(AADHAAR_CANDIDATE, AADHAAR_CTX)
assert signals["keyword_match"] is True
assert signals["doc_type_boost"] is True
assert signals["negative_match"] is False

# get_signals: full bundle for the invoice false-positive candidate
signals = context.get_signals(INVOICE_CANDIDATE, INVOICE_CTX)
assert signals["keyword_match"] is False
assert signals["negative_match"] is True

# find_page: missing page_num returns None
assert context.find_page(AADHAAR_CTX, 7) is None

# --- Regression: bbox=None must not crash (pasted text / CSV, legal per
# the detection contract) -- previously an unguarded 4-tuple unpack in
# ocr_confidence()/_bbox_overlap() raised TypeError here, verified as a
# real crash blocking the paste-text feature in pipeline.py.
assert context.ocr_confidence(AADHAAR_PAGE, None) is None

# Regression: pasted-text tokens carry neither bbox nor ocr_conf at all
# (pipeline.py builds them as {"text": w} only) -- must be skipped, not KeyError.
PASTED_TEXT_PAGE = {
    "page_num": 0, "width": 0, "height": 0,
    "tokens": [{"text": "Aadhaar"}, {"text": "1234"}, {"text": "5678"}, {"text": "9012"}],
    "full_text": "Aadhaar 1234 5678 9012",
}
PASTED_TEXT_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
    "bbox": None, "checksum_valid": True, "match_source": "regex",
}
assert context.ocr_confidence(PASTED_TEXT_PAGE, PASTED_TEXT_CANDIDATE["bbox"]) is None
signals = context.get_signals(PASTED_TEXT_CANDIDATE, {"pages": [PASTED_TEXT_PAGE]})
assert signals["keyword_match"] is True   # keyword/negative signals still work, they don't need bbox
assert signals["ocr_conf"] is None

print("All context tests passed")
