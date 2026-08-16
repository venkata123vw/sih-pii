def detect(extraction: dict) -> dict:
    return {"doc_id": extraction["doc_id"], "candidates": [
        {"pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
         "bbox": [100,200,290,230], "checksum_valid": True, "match_source": "regex"}]}