from scoring import ner, resolver

POLICY_MATRIX = resolver.load_policy_matrix()

# --- NAME + ADDRESS(GPE) in one page, with bbox mapping verified by hand ---
NAME_ADDRESS_PAGE = {
    "page_num": 0, "width": 1000, "height": 100,
    "tokens": [
        {"text": "Contact:", "bbox": [0, 0, 60, 20], "ocr_conf": 0.9},
        {"text": "Ravi", "bbox": [65, 0, 100, 20], "ocr_conf": 0.9},
        {"text": "Kumar,", "bbox": [105, 0, 150, 20], "ocr_conf": 0.9},
        {"text": "City:", "bbox": [155, 0, 190, 20], "ocr_conf": 0.9},
        {"text": "Mumbai", "bbox": [195, 0, 240, 20], "ocr_conf": 0.9},
    ],
    "full_text": "Contact: Ravi Kumar, City: Mumbai",
}

detections = ner.detect(NAME_ADDRESS_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX)
assert len(detections) == 2, detections

name = next(d for d in detections if d["pii_type"] == "NAME")
assert name["value"] == "Ravi Kumar"
assert name["checksum_valid"] is None
assert name["match_source"] == "ner"
assert 0.0 <= name["confidence"] <= 0.5          # NER ceiling from confidence.py
assert name["bbox"] == [65, 0, 150, 20]           # union of the "Ravi" + "Kumar," tokens
assert "policy_action" in name and "necessity" in name

address = next(d for d in detections if d["pii_type"] == "ADDRESS")
assert address["value"] == "Mumbai"
assert address["bbox"] == [195, 0, 240, 20]       # exactly the "Mumbai" token

# --- Noise entities (DATE/CARDINAL/WORK_OF_ART) must not leak through ---
# Real spaCy output on this text (spotchecked): PERSON 'Alex Morgan',
# DATE '45821', WORK_OF_ART 'Date of Birth', CARDINAL '15-04-2005' --
# only the PERSON should survive into detections.
DL_PAGE = {
    "page_num": 0, "width": 1000, "height": 100,
    "tokens": [
        {"text": "Alex", "bbox": [0, 0, 30, 20], "ocr_conf": 0.9},
        {"text": "Morgan", "bbox": [35, 0, 80, 20], "ocr_conf": 0.9},
    ],
    "full_text": "DRIVING LICENCE TEST DOCUMENT\nName: Alex Morgan\nLicence Number: DL-SYN-2026-45821\nDate of Birth: 15-04-2005",
}

detections = ner.detect(DL_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX)
assert len(detections) == 1, detections
assert detections[0]["pii_type"] == "NAME"
assert detections[0]["value"] == "Alex Morgan"

# --- No relevant entities at all -> empty list, not an error ---
NUMBERS_PAGE = {
    "page_num": 0, "width": 1000, "height": 100, "tokens": [],
    "full_text": "Invoice Number: INV-2026-0045\nTotal Amount: 2499 INR",
}
assert ner.detect(NUMBERS_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX) == []

# --- Empty full_text short-circuits without calling the model ---
EMPTY_PAGE = {"page_num": 0, "width": 1000, "height": 100, "tokens": [], "full_text": ""}
assert ner.detect(EMPTY_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX) == []

# --- Regression: pasted-text tokens carry no bbox/ocr_conf at all
# (pipeline.py builds them as {"text": w} only). This used to crash with
# KeyError: 'bbox' inside _bbox_for_span() the moment an entity overlapped
# one of these tokens. Must now report the detection with bbox=None
# rather than crash OR silently drop it -- dropping would under-report
# real PII that NER did find, just because the source had no coordinates.
PASTED_TEXT_PAGE = {
    "page_num": 0, "width": 0, "height": 0,
    "tokens": [{"text": w} for w in "Contact Ravi Kumar at Mumbai regarding Aadhaar 6563 2299 1528".split()],
    "full_text": "Contact Ravi Kumar at Mumbai regarding Aadhaar 6563 2299 1528",
}
detections = ner.detect(PASTED_TEXT_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX)
assert len(detections) == 2, detections   # NAME "Ravi Kumar" + ADDRESS "Mumbai"
for d in detections:
    assert d["bbox"] is None
    assert d["confidence"] == 0.5   # bare NER hit, no other signal, at the ceiling

# --- Mixed page: some tokens have bbox, some don't. Union must only use
# the ones that do, not crash on the ones that don't.
MIXED_PAGE = {
    "page_num": 0, "width": 1000, "height": 100,
    "tokens": [
        {"text": "Name:"},  # no bbox -- e.g. a field pasted in without coordinates
        {"text": "Ravi", "bbox": [65, 0, 100, 20], "ocr_conf": 0.9},
        {"text": "Kumar", "bbox": [105, 0, 150, 20], "ocr_conf": 0.9},
    ],
    "full_text": "Name: Ravi Kumar",
}
detections = ner.detect(MIXED_PAGE, "THIRD_PARTY_SERVICE", POLICY_MATRIX)
assert len(detections) == 1
assert detections[0]["bbox"] == [65, 0, 150, 20]   # union of only the tokens that have one

print("All ner tests passed")
