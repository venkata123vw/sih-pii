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

# get_signals: prefers the candidate's own ocr_conf (detect.py's
# min-across-joined-tokens) over the bbox-overlap reconstruction --
# even when bbox is None, which would otherwise force a None result.
OWN_OCR_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
    "bbox": None, "checksum_valid": True, "match_source": "regex", "ocr_conf": 0.42,
}
signals = context.get_signals(OWN_OCR_CANDIDATE, AADHAAR_CTX)
assert signals["ocr_conf"] == 0.42

# get_signals: falls back to bbox-overlap when the candidate has no
# ocr_conf of its own (e.g. NER candidates never carry this field).
assert "ocr_conf" not in AADHAAR_CANDIDATE
signals = context.get_signals(AADHAAR_CANDIDATE, AADHAAR_CTX)
assert abs(signals["ocr_conf"] - (0.95 + 0.95 + 0.55) / 3) < 1e-9

# --- vid_adjacent: Aadhaar's VID (Virtual ID) field is a 16-digit run
# printed right next to the real 12-digit number on every card. A
# sliding-window join can pick a 12-digit substring of the VID that
# passes the Aadhaar regex (and, rarely, its checksum too). Values here
# mirror an actual observed false positive: real Aadhaar "2341 2341
# 2346", VID "9111 8122 7978 3936" -- the tail "8122 7978 3936" got
# matched as a second AADHAAR candidate.
VID_PAGE = {
    "page_num": 0, "width": 1240, "height": 1754, "tokens": [],
    "full_text": "Aadhaar 2341 2341 2346\nVID : 9111 8122 7978 3936",
}
VID_CTX = {"doc_id": "d4", "pages": [VID_PAGE]}
REAL_AADHAAR_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "2341 2341 2346", "page_num": 0,
    "bbox": [0, 0, 1, 1], "checksum_valid": True, "match_source": "regex",
}
VID_SUBSTRING_CANDIDATE = {
    "pii_type": "AADHAAR", "value": "8122 7978 3936", "page_num": 0,
    "bbox": [0, 0, 1, 1], "checksum_valid": True, "match_source": "regex",
}

# The real Aadhaar number is NOT penalized -- "vid" is 34 chars away,
# well outside VID_LABEL_GAP, even though it's within the generic
# ±WINDOW_CHARS=50 negative_signal() window (proving a symmetric window
# genuinely can't tell these two matches apart -- this had to be a
# narrower, backward-only check).
assert context.vid_adjacent(VID_PAGE["full_text"], REAL_AADHAAR_CANDIDATE["value"]) is False
signals = context.get_signals(REAL_AADHAAR_CANDIDATE, VID_CTX)
assert signals["vid_adjacent"] is False

# The VID substring IS flagged -- "VID :" directly precedes it
assert context.vid_adjacent(VID_PAGE["full_text"], VID_SUBSTRING_CANDIDATE["value"]) is True
signals = context.get_signals(VID_SUBSTRING_CANDIDATE, VID_CTX)
assert signals["vid_adjacent"] is True

# VID also structurally threatens PHONE (a 12-digit substring starting
# "91" self-evidently matches the +91-prefix pattern) and CREDIT_CARD
# (the full 16-digit VID directly satisfies \d{12,19}, no substring
# needed) -- confirmed on a real card for PHONE specifically.
for vulnerable_type in ("PHONE", "CREDIT_CARD"):
    candidate = {**VID_SUBSTRING_CANDIDATE, "pii_type": vulnerable_type}
    signals = context.get_signals(candidate, VID_CTX)
    assert signals["vid_adjacent"] is True, vulnerable_type

# Types VID can't structurally collide with (VID is pure digits; these
# all require letters) are never flagged, even sitting right after a
# "vid" label.
NON_VULNERABLE_CANDIDATE = {**VID_SUBSTRING_CANDIDATE, "pii_type": "PAN"}
signals = context.get_signals(NON_VULNERABLE_CANDIDATE, VID_CTX)
assert signals["vid_adjacent"] is False

# vid_adjacent: no match at all -> False, not a crash
assert context.vid_adjacent(VID_PAGE["full_text"], "0000 0000 0000") is False

print("All context tests passed")
