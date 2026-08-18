"""
Ingestion extraction tests.

Runs extract() against the real files in data/ rather than hand-built
fixtures, since the whole point of this track is real PDF/OCR/DOCX/CSV/
JSON handling. All files under data/ and testdata/ are synthetic.
"""
import json
from pathlib import Path

import pytest

from ingestion.extract import extract

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def test_doc_id_is_stable_sha256_prefix():
    r1 = extract(str(DATA_DIR / "test_01.txt"))
    r2 = extract(str(DATA_DIR / "test_01.txt"))
    assert r1["doc_id"] == r2["doc_id"]
    assert len(r1["doc_id"]) == 12
    int(r1["doc_id"], 16)  # raises ValueError if not valid hex


def test_native_pdf_reports_text_pdf_with_point_coords():
    r = extract(str(DATA_DIR / "test_02.pdf"))
    assert r["source_type"] == "text_pdf"
    page = r["pages"][0]
    assert page["page_num"] == 0
    assert page["width"] > 0 and page["height"] > 0
    assert page["tokens"], "expected native text tokens"
    for tok in page["tokens"]:
        assert tok["ocr_conf"] == 1.0
        x0, y0, x1, y1 = tok["bbox"]
        assert x1 > x0 and y1 > y0


def test_docx_is_extracted_as_text_pdf():
    """pymupdf opens .docx natively -- confirms this is NOT an open gap."""
    r = extract(str(DATA_DIR / "test_03.docx"))
    assert r["source_type"] == "text_pdf"
    assert len(r["pages"]) == 1
    assert "College Notice" in r["pages"][0]["full_text"]
    assert len(r["pages"][0]["tokens"]) > 0


def test_csv_is_extracted_as_plain_text_with_no_bbox():
    r = extract(str(DATA_DIR / "test_07.csv"))
    assert r["source_type"] == "plain_text"
    assert len(r["pages"]) == 1
    tokens = r["pages"][0]["tokens"]
    texts = [t["text"] for t in tokens]
    assert "9876543210" in texts
    assert "alex.synthetic@example.com" in texts
    for t in tokens:
        assert "bbox" not in t
        assert "ocr_conf" not in t


def test_json_is_extracted_as_plain_text_with_no_bbox():
    r = extract(str(DATA_DIR / "test_09.json"))
    assert r["source_type"] == "plain_text"
    tokens = r["pages"][0]["tokens"]
    texts = [t["text"] for t in tokens]
    assert "9000012345" in texts
    assert "taylor.synthetic@example.com" in texts
    for t in tokens:
        assert "bbox" not in t
        assert "ocr_conf" not in t


def test_json_nested_values_are_flattened(tmp_path):
    payload = {"contact": {"phone": "9123456780", "tags": ["primary", "verified"]}}
    p = tmp_path / "nested.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    r = extract(str(p))
    texts = [t["text"] for t in r["pages"][0]["tokens"]]
    assert "9123456780" in texts
    assert "primary" in texts and "verified" in texts


def test_csv_does_not_raise_permission_error_on_cleanup(tmp_path):
    """Regression test for the Windows PermissionError this task fixes:
    pymupdf must never be asked to open .csv/.json, so no lingering
    file handle should prevent an immediate unlink."""
    src = DATA_DIR / "test_07.csv"
    dst = tmp_path / "copy.csv"
    dst.write_bytes(src.read_bytes())
    extract(str(dst))
    dst.unlink()  # raises PermissionError on Windows if extract() locked it
