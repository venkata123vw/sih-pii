import pymupdf


def apply_redactions(filepath: str, decisions: dict, out_path: str) -> str:
    """
    Apply PII redactions to a PDF.

    decisions should contain a list of detections.

    Each detection must have:
        page_index
        bbox = [x1, y1, x2, y2]
        text

    Example:
        {
            "detections": [
                {
                    "page_index": 0,
                    "bbox": [100, 180, 300, 205],
                    "text": "1234 5678 9012"
                }
            ]
        }
    """

    doc = pymupdf.open(filepath)

    detections = decisions.get("detections", [])

    for detection in detections:
        page_index = detection["page_index"]
        x0, y0, x1, y1 = detection["bbox"]

        # Validate page index
        if page_index < 0 or page_index >= len(doc):
            raise ValueError(
                f"Invalid page_index: {page_index}"
            )

        # Validate bounding box
        if x1 <= x0 or y1 <= y0:
            raise ValueError(
                f"Invalid bbox: {detection['bbox']}"
            )

        page = doc[page_index]

        rect = pymupdf.Rect(
            x0,
            y0,
            x1,
            y1
        )

        page.add_redact_annot(
            rect,
            fill=(0, 0, 0)
        )

    # Permanently apply all redactions
    for page in doc:
        page.apply_redactions()

    # Save the redacted PDF
    doc.save(out_path)

    doc.close()

    return out_path