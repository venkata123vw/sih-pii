def extract(filepath: str) -> dict:
    return {"doc_id": "stub", "source_type": "scanned_image",
            "pages": [{"page_num": 0, "width": 1240, "height": 1754,
                       "tokens": [{"text": "2341", "bbox": [100,200,160,230], "ocr_conf": 0.95},
                                  {"text": "2341", "bbox": [165,200,225,230], "ocr_conf": 0.95},
                                  {"text": "2346", "bbox": [230,200,290,230], "ocr_conf": 0.95}],
                       "full_text": "Aadhaar 2341 2341 2346"}]}
