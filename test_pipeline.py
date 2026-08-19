"""
pipeline.py tests.

Only group_detections_for_review() is covered here -- analyze()/apply()
are thin orchestration wrappers around the other tracks' real functions,
already exercised indirectly by every other track's own tests plus the
end-to-end scripts/evaluate.py run.
"""
import pymupdf
import pytest

from pipeline import group_detections_for_review, apply
from ingestion.extract import extract
from detection.detect import detect
from scoring.score import score
from redaction.redact import RedactionError


def _detection(pii_type, value, page_num=0):
    return {
        "pii_type": pii_type, "value": value, "page_num": page_num,
        "bbox": [0, 0, 10, 10], "checksum_valid": None, "match_source": "regex",
        "confidence": 0.5, "policy_action": "REMOVE", "necessity": "EXCESS",
        "reasons": [],
    }


def test_distinct_pairs_stay_separate_groups():
    detections = [
        _detection("AADHAAR", "2341 2341 2346"),
        _detection("PAN", "ALWPG5809L"),
        _detection("PHONE", "9876543210"),
    ]
    groups = group_detections_for_review(detections)
    assert len(groups) == 3
    assert all(len(g) == 1 for g in groups)


def test_same_type_and_value_grouped_together():
    d1 = _detection("AADHAAR", "2341 2341 2346", page_num=0)
    d2 = _detection("PAN", "ALWPG5809L", page_num=0)
    d3 = _detection("AADHAAR", "2341 2341 2346", page_num=1)  # same value, different page

    groups = group_detections_for_review([d1, d2, d3])

    assert len(groups) == 2  # 3 detections, 2 unique (type, value) pairs
    aadhaar_group = next(g for g in groups if g[0]["pii_type"] == "AADHAAR")
    assert len(aadhaar_group) == 2
    assert d1 in aadhaar_group and d3 in aadhaar_group


def test_different_type_same_value_string_stay_separate():
    """A digit string matching two different types (however unlikely)
    must not be merged -- the grouping key is (type, value), not value
    alone."""
    d1 = _detection("AADHAAR", "123456789012")
    d2 = _detection("CREDIT_CARD", "123456789012")

    groups = group_detections_for_review([d1, d2])
    assert len(groups) == 2


def test_grouping_preserves_object_identity_not_copies():
    """The caller mutates user_confirmed on every member of a group --
    this only works if the returned lists hold the SAME dict objects,
    not copies."""
    d1 = _detection("PHONE", "9876543210")
    d2 = _detection("PHONE", "9876543210")

    [group] = group_detections_for_review([d1, d2])
    for d in group:
        d["user_confirmed"] = True

    assert d1["user_confirmed"] is True
    assert d2["user_confirmed"] is True


def test_value_whitespace_is_stripped_before_grouping():
    d1 = _detection("EMAIL", "taylor@example.com")
    d2 = _detection("EMAIL", "  taylor@example.com  ")

    groups = group_detections_for_review([d1, d2])
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_empty_input_returns_empty_list():
    assert group_detections_for_review([]) == []


def test_group_order_is_first_seen():
    d1 = _detection("PAN", "ALWPG5809L")
    d2 = _detection("AADHAAR", "2341 2341 2346")
    d3 = _detection("PAN", "ALWPG5809L")  # repeats PAN -- must not move its group

    groups = group_detections_for_review([d1, d2, d3])
    assert [g[0]["pii_type"] for g in groups] == ["PAN", "AADHAAR"]


# --- Regression: this is the actual bug group_detections_for_review()
# exists to make unreachable. A value printed twice on the same page,
# confirmed for redaction at one occurrence but not the other, crashes
# apply_redactions() with RedactionError -- reproduced here with a real
# 2-line PDF and the real extract -> detect -> score -> redact chain,
# then again with grouping applied to prove the fix actually prevents
# the scenario, not just documents it.
def _build_duplicate_value_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Aadhaar: 2341 2341 2346")
    page.insert_text((50, 100), "Copy again: 2341 2341 2346")
    doc.save(path)
    doc.close()


def test_partial_confirmation_of_duplicate_value_crashes_without_grouping(tmp_path):
    src = tmp_path / "dup.pdf"
    _build_duplicate_value_pdf(str(src))

    extraction = extract(str(src))
    candidates = detect(extraction)
    result = score(candidates, "THIRD_PARTY_SERVICE", extraction)

    detections = result["detections"]
    assert len(detections) == 2  # same value, two physical occurrences

    # confirm only the first occurrence -- the ungrouped, naive path
    for i, d in enumerate(detections):
        d["user_confirmed"] = (i == 0)

    analysis = result
    with open(src, "rb") as f:
        file_bytes = f.read()

    with pytest.raises(RedactionError, match="still extractable"):
        apply(file_bytes, "dup.pdf", analysis)


def test_grouped_confirmation_of_duplicate_value_redacts_cleanly(tmp_path):
    src = tmp_path / "dup2.pdf"
    _build_duplicate_value_pdf(str(src))

    extraction = extract(str(src))
    candidates = detect(extraction)
    result = score(candidates, "THIRD_PARTY_SERVICE", extraction)

    groups = group_detections_for_review(result["detections"])
    assert len(groups) == 1  # one unique value -> one review row

    # confirm the ONE group -- propagates to every occurrence, as the
    # real review UI does
    for d in groups[0]:
        d["user_confirmed"] = True

    analysis = result
    with open(src, "rb") as f:
        file_bytes = f.read()

    output_bytes, report = apply(file_bytes, "dup2.pdf", analysis)
    assert report["verified"] is True
    assert report["removed"] == 2
