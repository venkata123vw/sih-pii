def extract(filepath: str) -> dict:
    return {"doc_id": "stub", "source_type": "scanned_image",
            "pages": [{"page_num": 0, "width": 1240, "height": 1754,
                       "tokens": [{"text": "2341", "bbox": [100,200,160,230], "ocr_conf": 0.95},
                                  {"text": "2341", "bbox": [165,200,225,230], "ocr_conf": 0.95},
                                  {"text": "2346", "bbox": [230,200,290,230], "ocr_conf": 0.95}],
                       "full_text": "Aadhaar 2341 2341 2346"}]}
"""
P2 - PDF/Image Text Extraction Module

Emits the contract shape agreed with detection/scoring/redaction:

{
    "doc_id": "<sha256 prefix>",
    "source_type": "text_pdf" | "scanned_image",
    "pages": [
        {
            "page_num": 0,              # zero-indexed
            "width": 595.0,             # PDF POINTS, not pixels
            "height": 842.0,
            "full_text": "...",
            "tokens": [
                {
                    "text": "John",
                    "bbox": [x0, y0, x1, y1],   # top-left origin, points
                    "ocr_conf": 1.0              # 1.0 for native text, <1.0 for OCR
                },
                ...
            ]
        },
        ...
    ]
}

Native text-layer PDFs are handled directly (fast, exact bboxes).
Pages with no text layer fall back to OCR (EasyOCR) automatically,
so scanned PDFs and images both work without a separate code path.
"""

import hashlib
import os

import pymupdf


def _doc_id(filepath: str) -> str:
    """Stable ID from file contents, so re-running gives the same doc_id."""
    with open(filepath, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def _extract_native_page(page):
    """
    Native text-layer extraction for one page.
    get_text("words") -> (x0, y0, x1, y1, word, block, line, word_no)
    Already in [x0, y0, x1, y1] order, top-left origin, in PDF points.
    """
    words = page.get_text("words")
    tokens = [
        {
            "text": w[4],
            "bbox": [w[0], w[1], w[2], w[3]],
            "ocr_conf": 1.0,  # native text layer, not OCR
        }
        for w in words
        if w[4].strip()
    ]
    return tokens, page.get_text()


def _extract_ocr_page(page, reader, zoom=2.0):
    """
    Fallback for pages with no text layer: render to an image and OCR it.
    Rendered pixel coords are converted back into PDF point coords so
    bboxes line up with the page's own width/height (both in points).
    """
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")

    ocr_results = reader.readtext(img_bytes)

    tokens = []
    full_text_parts = []
    for bbox_points, text, confidence in ocr_results:
        if not text.strip():
            continue
        xs = [p[0] / zoom for p in bbox_points]  # pixels -> points
        ys = [p[1] / zoom for p in bbox_points]
        tokens.append({
            "text": text,
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "ocr_conf": float(confidence),
        })
        full_text_parts.append(text)

    return tokens, " ".join(full_text_parts)


def extract(filepath: str, reader=None) -> dict:
    """
    Main entry point. Reads the real file at `filepath`.

    Per-page logic:
      - if the page has a native text layer, extract it directly (fast, exact).
      - if not, fall back to OCR for that page only (so mixed PDFs work too).

    `source_type` on the doc is "scanned_image" only if NO page anywhere
    in the doc had a native text layer; otherwise "text_pdf".
    """
    doc = pymupdf.open(filepath)
    pages = []
    any_native_text = False
    needs_ocr = any(len(p.get_text().strip()) < 20 for p in doc)

    if needs_ocr and reader is None:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False)

    for page_num, page in enumerate(doc):
        rect = page.rect
        has_native = len(page.get_text().strip()) >= 20

        if has_native:
            any_native_text = True
            tokens, full_text = _extract_native_page(page)
        else:
            tokens, full_text = _extract_ocr_page(page, reader)

        pages.append({
            "page_num": page_num,
            "width": rect.width,
            "height": rect.height,
            "tokens": tokens,
            "full_text": full_text,
        })

    doc.close()

    return {
        "doc_id": _doc_id(filepath),
        "source_type": "text_pdf" if any_native_text else "scanned_image",
        "pages": pages,
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python extract.py <path_to_pdf>")
        sys.exit(1)

    input_path = sys.argv[1]
    output = extract(input_path)

    print(json.dumps(output, indent=2))

    out_path = os.path.splitext(input_path)[0] + "_extracted.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved output to: {out_path}")