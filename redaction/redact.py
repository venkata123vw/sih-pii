import pymupdf


def apply_redactions(filepath: str, decisions: dict, out_path: str) -> str:
    """
    Apply PII redactions to a PDF.

    decisions should contain a list of detections.
    Each detection must have:
        page_num
        bbox = [x0, y0, x1, y1]
    """

    doc = pymupdf.open(filepath)

    detections = decisions.get("detections", [])

    for detection in detections:
        page_num = detection["page_num"]
        x0, y0, x1, y1 = detection["bbox"]

        # Validate page number
        if page_num < 0 or page_num >= len(doc):
            raise ValueError(
                f"Invalid page_num: {page_num}"
            )

        # Validate bounding box
        if x1 <= x0 or y1 <= y0:
            raise ValueError(
                f"Invalid bbox: {detection['bbox']}"
            )

        page = doc[page_num]

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