"""
Detection engine tests.

Built against a hand-written extraction fixture rather than
ingestion.extract(), so this track is testable independently of P2.
All identifiers here are SYNTHETIC.
"""
import pytest

from detection.detect import detect


def _tok(text, i, conf=1.0):
    """Token at a predictable x offset so union bboxes are checkable."""
    return {"text": text, "bbox": [10 * i, 100, 10 * i + 40, 120],
            "ocr_conf": conf}


def _page(words, page_num=0):
    return {"page_num": page_num, "width": 1240, "height": 1754,
            "tokens": [_tok(w, i) for i, w in enumerate(words)],
            "full_text": " ".join(words)}


def _extraction(*pages, doc_id="test_doc"):
    return {"doc_id": doc_id, "source_type": "scanned_image",
            "pages": list(pages)}


def _types(out):
    return sorted(c["pii_type"] for c in out["candidates"])


def _by_type(out, pii_type):
    return next(c for c in out["candidates"] if c["pii_type"] == pii_type)


def test_aadhaar_split_across_tokens():
    """
    The core reason this module exists: OCR emits '2341 2341 2346' as
    three separate tokens, so a per-token validator finds nothing.
    """
    out = detect(_extraction(_page(["Aadhaar", "No", "2341", "2341", "2346"])))
    hit = _by_type(out, "AADHAAR")
    assert hit["value"] == "2341 2341 2346"
    assert hit["checksum_valid"] is True
    assert hit["page_num"] == 0


def test_union_bbox_spans_all_tokens():
    """P4 draws one box over the whole value, not three."""
    out = detect(_extraction(_page(["Aadhaar", "2341", "2341", "2346"])))
    hit = _by_type(out, "AADHAAR")
    assert hit["bbox"] == [10, 100, 70, 120]   # token 1 left .. token 3 right


def test_checksum_failure_is_not_a_candidate():
    """Pattern match alone must not produce a detection."""
    out = detect(_extraction(_page(["ID", "2341", "2341", "2347"])))
    assert "AADHAAR" not in _types(out)


def test_reserved_first_digit_rejected():
    """Aadhaar never starts with 0 or 1 — UIDAI reserves those."""
    out = detect(_extraction(_page(["ID", "1234", "5678", "9012"])))
    assert "AADHAAR" not in _types(out)


def test_card_not_double_reported_as_aadhaar():
    """
    A 16-digit card contains 12-digit runs. Overlap resolution must keep
    the longest span so P4 doesn't redact the same pixels twice.
    """
    out = detect(_extraction(_page(["Card", "4242", "4242", "4242", "4242"])))
    assert _types(out) == ["CREDIT_CARD"]
    assert _by_type(out, "CREDIT_CARD")["value"] == "4242 4242 4242 4242"


def test_pan_inline():
    """PAN has no published check-digit algorithm, so checksum_valid is None."""
    out = detect(_extraction(_page(["PAN", "ALWPG5809L"])))
    assert _by_type(out, "PAN")["checksum_valid"] is None


def test_formatless_types_report_checksum_none():
    """
    Phone/email/voter have no checksum. checksum_valid must be None, not
    False — P3 weighs 'no checksum exists' differently from 'failed'.
    """
    out = detect(_extraction(_page(["Mob", "98765", "43210", "a@b.com"])))
    assert _by_type(out, "PHONE")["checksum_valid"] is None
    assert _by_type(out, "EMAIL")["checksum_valid"] is None


def test_bare_ten_digits_is_not_a_phone():
    """
    Measured 10% FP: a bare unpunctuated 10-digit run starting 6-9 is a
    rupee amount as often as a phone number. Require grouping or an
    explicit +91/0 prefix.
    """
    out = detect(_extraction(_page(["Total", "9432835008"])))
    assert "PHONE" not in _types(out)


def test_phone_formats_still_detected():
    """The tightening must not cost recall on real-world formats."""
    for words in (["Mob", "98765", "43210"], ["+919876543210"],
                  ["09876543210"], ["919876543210"]):
        out = detect(_extraction(_page(words)))
        assert "PHONE" in _types(out), words


def test_voter_id_requires_context_keyword():
    """
    EPIC shape (AAA9999999) is identical to courier tracking codes —
    measured 20% FP. The string alone cannot distinguish them, so a
    keyword must appear in the page text.
    """
    page = _page(["Tracking", "SZS1656930"])
    assert "VOTER_ID" not in _types(detect(_extraction(page)))

    page = _page(["Voter", "ID", "ABC1234567"])
    assert "VOTER_ID" in _types(detect(_extraction(page)))


def test_multi_page_page_num_preserved():
    out = detect(_extraction(
        _page(["Aadhaar", "2341", "2341", "2346"], page_num=0),
        _page(["PAN", "ALWPG5809L"], page_num=3),
    ))
    assert _by_type(out, "AADHAAR")["page_num"] == 0
    assert _by_type(out, "PAN")["page_num"] == 3


def test_clean_document_yields_nothing():
    out = detect(_extraction(_page(["Invoice", "total", "4500", "rupees"])))
    assert out["candidates"] == []


def test_output_matches_scoring_input_contract():
    """
    Every field score() carries through must be present. Guards the
    P1 -> P3 handoff against the same drift that hit page_num.
    """
    out = detect(_extraction(_page(["Aadhaar", "2341", "2341", "2346"])))
    assert set(out) == {"doc_id", "candidates"}
    assert out["doc_id"] == "test_doc"
    required = {"pii_type", "value", "page_num", "bbox",
                "checksum_valid", "match_source", "ocr_conf"}
    for candidate in out["candidates"]:
        assert set(candidate) == required     # no extra fields leaked
        assert candidate["match_source"] == "regex"
        assert len(candidate["bbox"]) == 4
        assert candidate["checksum_valid"] in (True, None)   # never False


def test_bbox_none_survives_fieldless_sources():
    """CSV rows have no coordinates. Must not crash."""
    page = {"page_num": 0, "tokens": [{"text": "234123412346"}],
            "full_text": "234123412346"}
    out = detect(_extraction(page))
    assert _by_type(out, "AADHAAR")["bbox"] is None