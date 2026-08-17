import pymupdf


def apply_redactions(filepath: str, decisions: dict, out_path: str) -> str:
    """
    Apply PII redactions to a PDF.

    decisions should contain a list of detections.
    Each detection must have:
        page_num
        bbox = [x0, y0, x1, y1]

    Example:
        {
            "detections": [
                {
                    "page_num": 0,
                    "bbox": [100, 180, 300, 205]
                }
            ]
        }
    """

    doc = pymupdf.open(filepath)

    detections = decisions.get("detections", [])

    for detection in detections:

        page_num = detection["page_num"]
        x0, y0, x1, y1 = detection["bbox"]

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