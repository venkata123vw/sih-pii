"""
Redaction tests (P4).

Verifies that apply_redactions() removes text from the PDF's text layer rather
than drawing a box over it. A drawn-over-but-still-extractable value is the
worst possible outcome for this project: it looks redacted to a human and is
recoverable with copy-paste.

Fixtures use the real scoring.score.score() output shape — `value`, not `text`,
and every detection carries a policy_action.
"""

import pymupdf
import pytest

from redact import RedactionError, apply_redactions, mask_value

INPUT_PDF = "testdata/documents/test.pdf"

# Text sitting next to a redacted value. Asserting it survives proves redaction
# is surgical: the box removed the value without swallowing the line's label.
SURVIVING_LABEL = "Aadhaar:"

AADHAAR = "2341 2341 2346"
NAME = "Rithika"
EMAIL = "rithika@example.com"


def _detection(pii_type, value, bbox, action, page_num=0, **extra):
    """A detection in the exact shape scoring.score.score() emits."""
    base = {
        "pii_type": pii_type,
        "value": value,
        "page_num": page_num,
        "bbox": bbox,
        "checksum_valid": True,
        "match_source": "regex",
        "confidence": 0.85,
        "policy_action": action,
        "necessity": "EXCESS",
        "reasons": ["checksum_pass"],
    }
    base.update(extra)
    return base


def _decisions(*detections):
    return {
        "doc_id": "fixture-001",
        "context_profile": "THIRD_PARTY_SERVICE",
        "detections": list(detections),
        "excess_pii_alert": [],
    }


AADHAAR_BOX = [186.71998596191406, 128.5, 331.2799377441406, 155.97999572753906]
NAME_BOX = [164.45999145507812, 178.5, 225.57998657226562, 205.97999572753906]
EMAIL_BOX = [108.67, 187.10, 224.21, 203.59]

DECISIONS = _decisions(
    _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE"),
    _detection("NAME", NAME, NAME_BOX, "REMOVE", checksum_valid=None, match_source="ner"),
)


def _extract_text(path: str) -> str:
    doc = pymupdf.open(path)
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


# --- guard ------------------------------------------------------------------

def test_pii_is_present_before_redaction():
    """
    Guard against a false pass. Without this, the redaction test below would
    pass trivially on a blank PDF or a scan with no text layer — nothing was
    redacted, but nothing is extractable either, so 'PII is gone' goes green
    on a no-op.
    """
    text = _extract_text(INPUT_PDF)
    for detection in DECISIONS["detections"]:
        assert detection["value"] in text, (
            f"{detection['value']!r} not found in {INPUT_PDF}. "
            "The fixture PDF changed, or the bboxes are stale."
        )


# --- core behaviour ----------------------------------------------------------

def test_pii_is_removed_from_text_layer(tmp_path):
    out_path = str(tmp_path / "redacted.pdf")
    manifest = apply_redactions(INPUT_PDF, DECISIONS, out_path)

    assert manifest["out_path"] == out_path
    assert manifest["verified"] is True
    text = _extract_text(out_path)
    for detection in DECISIONS["detections"]:
        assert detection["value"] not in text


def test_non_pii_text_survives(tmp_path):
    """Redaction must be surgical — unrelated content stays readable."""
    out_path = str(tmp_path / "redacted.pdf")
    apply_redactions(INPUT_PDF, DECISIONS, out_path)
    text = _extract_text(out_path)
    assert SURVIVING_LABEL in text
    assert EMAIL in text


def test_manifest_carries_doc_identity(tmp_path):
    """P5 needs to tie the manifest back to the document scoring ran on."""
    out_path = str(tmp_path / "redacted.pdf")
    manifest = apply_redactions(INPUT_PDF, DECISIONS, out_path)
    assert manifest["doc_id"] == "fixture-001"
    assert manifest["context_profile"] == "THIRD_PARTY_SERVICE"
    assert len(manifest["redacted"]) == 2
    assert manifest["counts"]["REMOVE"] == 2


def test_empty_detections_is_a_no_op(tmp_path):
    """
    A document with no detections comes out fully readable. Asserting the PII
    is STILL present is the strong form — it proves the pipeline isn't
    redacting things nobody asked it to.
    """
    out_path = str(tmp_path / "clean.pdf")
    apply_redactions(INPUT_PDF, _decisions(), out_path)
    text = _extract_text(out_path)
    for detection in DECISIONS["detections"]:
        assert detection["value"] in text


# --- policy_action gating ----------------------------------------------------

def test_keep_is_never_redacted(tmp_path):
    """The contract's whole point: KEEP means leave it alone."""
    out_path = str(tmp_path / "keep.pdf")
    decisions = _decisions(
        _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE"),
        _detection("NAME", NAME, NAME_BOX, "KEEP"),
    )
    manifest = apply_redactions(INPUT_PDF, decisions, out_path)

    text = _extract_text(out_path)
    assert AADHAAR not in text
    assert NAME in text
    assert manifest["counts"]["KEEP"] == 1
    assert manifest["skipped"][0]["reason"] == "policy:KEEP"


def test_mask_leaves_tail_visible(tmp_path):
    out_path = str(tmp_path / "masked.pdf")
    decisions = _decisions(_detection("AADHAAR", AADHAAR, AADHAAR_BOX, "MASK"))
    apply_redactions(INPUT_PDF, decisions, out_path)

    text = _extract_text(out_path)
    assert AADHAAR not in text
    assert "XXXX XXXX 2346" in text


def test_flag_fails_closed_by_default(tmp_path):
    """FLAG needs human review; the default must not leak it in the meantime."""
    out_path = str(tmp_path / "flag.pdf")
    decisions = _decisions(_detection("AADHAAR", AADHAAR, AADHAAR_BOX, "FLAG"))
    apply_redactions(INPUT_PDF, decisions, out_path)
    assert AADHAAR not in _extract_text(out_path)


def test_flag_can_be_deferred(tmp_path):
    out_path = str(tmp_path / "flag_skip.pdf")
    decisions = _decisions(_detection("AADHAAR", AADHAAR, AADHAAR_BOX, "FLAG"))
    manifest = apply_redactions(INPUT_PDF, decisions, out_path, flag_action="SKIP")
    assert AADHAAR in _extract_text(out_path)
    assert manifest["skipped"][0]["reason"] == "policy:FLAG:deferred_to_review"


def test_rejects_unknown_policy_action(tmp_path):
    out_path = str(tmp_path / "bad.pdf")
    decisions = _decisions(_detection("AADHAAR", AADHAAR, AADHAAR_BOX, "OBLITERATE"))
    with pytest.raises(ValueError, match="policy_action"):
        apply_redactions(INPUT_PDF, decisions, out_path)


def test_rejects_missing_policy_action(tmp_path):
    out_path = str(tmp_path / "bad.pdf")
    detection = _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE")
    del detection["policy_action"]
    with pytest.raises(ValueError, match="policy_action"):
        apply_redactions(INPUT_PDF, _decisions(detection), out_path)


def test_rejects_text_key_instead_of_value(tmp_path):
    """Catches the old P4 shape, where the field was called `text`."""
    out_path = str(tmp_path / "bad.pdf")
    detection = _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE")
    detection["text"] = detection.pop("value")
    with pytest.raises(ValueError, match="value"):
        apply_redactions(INPUT_PDF, _decisions(detection), out_path)


# --- coordinate-less sources -------------------------------------------------

def test_null_bbox_is_skipped_not_crashed(tmp_path):
    """CSV/text sources emit bbox: None. That's legal, not a crash."""
    out_path = str(tmp_path / "nobbox.pdf")
    decisions = _decisions(
        _detection("EMAIL", EMAIL, None, "REMOVE"),
        _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE"),
    )
    manifest = apply_redactions(INPUT_PDF, decisions, out_path)

    assert manifest["counts"]["no_bbox"] == 1
    assert manifest["skipped"][0]["reason"] == "no_bbox:coordinate_less_source"
    assert AADHAAR not in _extract_text(out_path)


# --- input validation --------------------------------------------------------

def test_rejects_out_of_range_page_num(tmp_path):
    out_path = str(tmp_path / "bad.pdf")
    for bad_page in (-1, 99):
        decisions = _decisions(
            _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE", page_num=bad_page)
        )
        with pytest.raises(ValueError, match="page_num"):
            apply_redactions(INPUT_PDF, decisions, out_path)


def test_rejects_inverted_bbox(tmp_path):
    """x1 <= x0 or y1 <= y0 means a zero-area box that redacts nothing."""
    out_path = str(tmp_path / "bad.pdf")
    for bad_box in ([210.0, 157.0, 124.0, 173.0], [124.0, 173.0, 210.0, 157.0]):
        decisions = _decisions(_detection("AADHAAR", AADHAAR, bad_box, "REMOVE"))
        with pytest.raises(ValueError, match="bbox"):
            apply_redactions(INPUT_PDF, decisions, out_path)


def test_rejects_malformed_bbox(tmp_path):
    out_path = str(tmp_path / "bad.pdf")
    for bad_box in ([1, 2, 3], [1, 2, 3, "x"]):
        decisions = _decisions(_detection("AADHAAR", AADHAAR, bad_box, "REMOVE"))
        with pytest.raises(ValueError, match="bbox"):
            apply_redactions(INPUT_PDF, decisions, out_path)


def test_validation_happens_before_mutation(tmp_path):
    """A bad detection late in the list must not leave a half-redacted file."""
    out_path = str(tmp_path / "partial.pdf")
    decisions = _decisions(
        _detection("AADHAAR", AADHAAR, AADHAAR_BOX, "REMOVE"),
        _detection("NAME", NAME, NAME_BOX, "REMOVE", page_num=99),
    )
    with pytest.raises(ValueError, match="page_num"):
        apply_redactions(INPUT_PDF, decisions, out_path)
    assert not (tmp_path / "partial.pdf").exists()


def test_rejects_in_place_redaction(tmp_path):
    with pytest.raises(ValueError, match="out_path"):
        apply_redactions(INPUT_PDF, DECISIONS, INPUT_PDF)


# --- rotated pages -----------------------------------------------------------

def test_rotated_page_redaction(tmp_path):
    """
    Page 1 of the fixture has rotation=90. Coordinates from get_text("words")
    and add_redact_annot share a space regardless of rotation, so no correction
    is needed — this test exists to catch it if that ever stops being true.
    """
    out_path = str(tmp_path / "rotated.pdf")
    decisions = _decisions(
        _detection("AADHAAR", "4321 8765 2109", [124.03, 127.10, 210.77, 143.59],
                   "REMOVE", page_num=1)
    )
    apply_redactions(INPUT_PDF, decisions, out_path)
    assert "4321 8765 2109" not in _extract_text(out_path)


# --- mask_value unit tests ---------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("2341 2341 2346", "XXXX XXXX 2346"),
        ("ABCDE1234F", "XXXXXX234F"),
        ("4111-1111-1111-1111", "XXXX-XXXX-XXXX-1111"),
    ],
)
def test_mask_value(value, expected):
    assert mask_value(value) == expected
