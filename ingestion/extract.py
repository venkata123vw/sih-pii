"""
P2 - PDF/Image Text Extraction Module

Emits the contract shape agreed with detection/scoring/redaction:

{
    "doc_id": "<sha256 prefix>",
    "source_type": "text_pdf" | "scanned_image" | "plain_text",  # plain_text: .csv/.json
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

.csv and .json have no pymupdf document handler, so they're read as
plain text: one page, tokens are cell/value words with no bbox/ocr_conf
keys (coordinate-less, same shape pipeline.py's pasted-text path uses).
"""

import csv
import hashlib
import json
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


def _split_line_to_words(text, line_bbox, confidence):
    """
    EasyOCR returns whole LINES as single results (e.g. "Aadhaar: 1234 5678
    9012"), but the native PDF path returns individual WORDS. Detection
    joins adjacent word-level tokens to find values split across them, so
    line-level tokens make detection match nothing on scanned documents.

    This splits a line into words and spreads the line's bbox across them
    proportionally by character position. Not pixel-perfect (doesn't
    account for variable character width, e.g. "i" vs "W"), but close
    enough for redaction boxes, and keeps the contract identical to the
    native path (word-level tokens either way).
    """
    words = text.split()
    if not words:
        return []

    x0, y0, x1, y1 = line_bbox
    line_width = x1 - x0
    total_len = len(text)

    tokens = []
    cursor = 0
    for word in words:
        start = text.index(word, cursor)
        end = start + len(word)
        cursor = end

        frac_start = start / total_len
        frac_end = end / total_len
        word_x0 = x0 + frac_start * line_width
        word_x1 = x0 + frac_end * line_width

        tokens.append({
            "text": word,
            "bbox": [word_x0, y0, word_x1, y1],
            "ocr_conf": confidence,
        })

    return tokens


def _flatten_json_values(node, out):
    """Collect leaf string/number/bool values from arbitrary JSON,
    ignoring keys -- detection matches against values, not field names."""
    if isinstance(node, dict):
        for v in node.values():
            _flatten_json_values(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten_json_values(v, out)
    elif node is not None:
        out.append(str(node))


def _extract_csv(filepath):
    """
    CSV has no native pymupdf document handler (confirmed: opening one
    raises pymupdf.FileDataError and orphans a file handle on Windows,
    which is the actual PermissionError this function exists to avoid).
    Cells are the token unit -- splitting only on whitespace would leave
    comma-glued cells like 'Morgan,9876543210,x@example.com' as one
    token, which detection's anchored (^...$) patterns can't match.
    """
    with open(filepath, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    words = []
    for row in rows:
        for cell in row:
            words.extend(cell.split())
    tokens = [{"text": w} for w in words]
    full_text = "\n".join(",".join(row) for row in rows)
    return tokens, full_text


def _extract_json(filepath):
    """
    Same rationale as _extract_csv: pymupdf has no JSON handler, and raw
    whitespace-splitting would leave quotes/commas/braces glued to
    values (e.g. '"9000012345",'), which anchored patterns can't match.
    """
    with open(filepath, encoding="utf-8") as fh:
        raw_text = fh.read()
    data = json.loads(raw_text)

    values = []
    _flatten_json_values(data, values)
    words = []
    for v in values:
        words.extend(v.split())
    tokens = [{"text": w} for w in words]
    return tokens, raw_text


def _extract_ocr_page(page, reader, zoom=2.0):
    """
    Fallback for pages with no text layer: render to an image and OCR it.
    Rendered pixel coords are converted back into PDF point coords so
    bboxes line up with the page's own width/height (both in points).

    EasyOCR returns whole lines as single results, so each line is split
    into word-level tokens (see _split_line_to_words) to match the
    word-level contract the native text path already produces.
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
        line_bbox = [min(xs), min(ys), max(xs), max(ys)]

        tokens.extend(_split_line_to_words(text, line_bbox, float(confidence)))
        full_text_parts.append(text)

    return tokens, " ".join(full_text_parts)


_PLAIN_TEXT_EXTENSIONS = {".csv", ".json"}


def extract(filepath: str, reader=None) -> dict:
    """
    Main entry point. Reads the real file at `filepath`.

    .csv/.json are read as plain text and never handed to pymupdf, which
    has no document handler for either -- doing so raises FileDataError
    and, on Windows, orphans a file handle that later breaks the temp
    file's cleanup (see pipeline.py's analyze()). Every other extension
    (including .txt and .docx, both of which pymupdf opens natively)
    goes through the existing PDF/OCR path unchanged.

    Per-page logic for the pymupdf path:
      - if the page has a native text layer, extract it directly (fast, exact).
      - if not, fall back to OCR for that page only (so mixed PDFs work too).

    `source_type` on the doc is "scanned_image" only if NO page anywhere
    in the doc had a native text layer; "plain_text" for .csv/.json;
    otherwise "text_pdf".
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in _PLAIN_TEXT_EXTENSIONS:
        extractor = _extract_csv if ext == ".csv" else _extract_json
        tokens, full_text = extractor(filepath)
        return {
            "doc_id": _doc_id(filepath),
            "source_type": "plain_text",
            "pages": [{
                "page_num": 0,
                "width": 0,
                "height": 0,
                "tokens": tokens,
                "full_text": full_text,
            }],
        }

    doc = pymupdf.open(filepath)
    pages = []
    any_native_text = False
    needs_ocr = any(len(p.get_text().strip()) < 20 for p in doc)

    if needs_ocr and reader is None:
        import easyocr
        # Indian government IDs (Aadhaar, PAN, ...) are bilingual by
        # design -- Hindi (Devanagari) alongside English on the same
        # card. An English-only reader forces Devanagari glyphs into
        # English character predictions, producing garbled tokens that
        # then feed bad text into NER. "hi" is EasyOCR's supported
        # Devanagari-script code and combines with "en" (confirmed:
        # both share EasyOCR's Latin+Devanagari-compatible model group).
        reader = easyocr.Reader(["en", "hi"], gpu=False)

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
