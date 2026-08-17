"""
Redaction integration tests.

Verifies that apply_redactions() actually removes text from the PDF's
text layer, not just draws a black box over it. A drawn-over-but-still-
extractable value is the worst possible outcome for this project: it
looks redacted to a human and is trivially recoverable with copy-paste.
"""
import pymupdf
import pytest

from redaction.redact import apply_redactions

INPUT_PDF = "testdata/documents/test.pdf"

# Label text that sits next to a redacted value. Asserting these survive
# proves redaction is surgical — the box removed the value without
# swallowing the surrounding line.
SURVIVING_LABEL = "Aadhaar:"

DECISIONS = {
    "detections": [
        {
            "page_num": 0,
            "bbox": [186.0, 177.0, 332.0, 207.0],
            "text": "1234 5678 9012",
        },
        {
            "page_num": 0,
            "bbox": [164.46, 228.50, 225.58, 255.98],
            "text": "Rithika",
        },
    ]
}


def _extract_text(path: str) -> str:
    doc = pymupdf.open(path)
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_pii_is_present_before_redaction():
    """
    Guard against a false pass. Without this, the redaction test below
    would pass trivially on a blank PDF or a scan with no text layer —
    nothing was redacted, but nothing is extractable either, so the
    'PII is gone' assertion would go green on a no-op.
    """
    text = _extract_text(INPUT_PDF)
    for detection in DECISIONS["detections"]:
        assert detection["text"] in text, (
            f"{detection['text']!r} not found in {INPUT_PDF}. "
            "The fixture PDF changed, or the bboxes are stale."
        )


def test_pii_is_removed_from_text_layer(tmp_path):
    """The core assertion: detected values are gone after redaction."""
    out_path = str(tmp_path / "redacted.pdf")
    result = apply_redactions(INPUT_PDF, DECISIONS, out_path)
    assert result == out_path

    text = _extract_text(out_path)
    for detection in DECISIONS["detections"]:
        assert detection["text"] not in text


def test_non_pii_text_survives(tmp_path):
    """Redaction must be surgical — unrelated content stays readable."""
    out_path = str(tmp_path / "redacted.pdf")
    apply_redactions(INPUT_PDF, DECISIONS, out_path)
    assert SURVIVING_LABEL in _extract_text(out_path)


def test_empty_detections_is_a_no_op(tmp_path):
    """
    A document with no detections must come out byte-for-byte readable.
    Asserting the PII is STILL present is the strong form — it proves
    the pipeline isn't redacting things nobody asked it to.
    """
    out_path = str(tmp_path / "clean.pdf")
    apply_redactions(INPUT_PDF, {"detections": []}, out_path)
    text = _extract_text(out_path)
    for detection in DECISIONS["detections"]:
        assert detection["text"] in text


def test_rejects_out_of_range_page_num(tmp_path):
    out_path = str(tmp_path / "bad.pdf")
    for bad_page in (-1, 99):
        bad = {"detections": [{"page_num": bad_page,
                               "bbox": [186.0, 177.0, 332.0, 207.0]}]}
        with pytest.raises(ValueError, match="page_num"):
            apply_redactions(INPUT_PDF, bad, out_path)


def test_rejects_inverted_bbox(tmp_path):
    """x1 <= x0 or y1 <= y0 means a zero-area box that redacts nothing."""
    out_path = str(tmp_path / "bad.pdf")
    for bad_box in ([332.0, 177.0, 186.0, 207.0], [186.0, 207.0, 332.0, 177.0]):
        bad = {"detections": [{"page_num": 0, "bbox": bad_box}]}
        with pytest.raises(ValueError, match="bbox"):
            apply_redactions(INPUT_PDF, bad, out_path)