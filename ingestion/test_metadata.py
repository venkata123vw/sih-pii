"""
Metadata scanner tests.

metadata_findings is a new, unratified wire shape (see ingestion/metadata.py's
module docstring) -- these tests pin down what scan_metadata() actually
returns today, not a contract agreed with other tracks yet.
"""
from pathlib import Path

import pytest

from ingestion.metadata import scan_metadata

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def test_unsupported_extension_returns_empty_findings(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello", encoding="utf-8")
    r = scan_metadata(str(p))
    assert r == {"source_type": "unsupported", "findings": []}


def test_pdf_with_no_metadata_has_no_findings():
    """data/test_02.pdf's doc.metadata fields are all empty strings except
    creationDate -- confirmed directly against the real file."""
    r = scan_metadata(str(DATA_DIR / "test_02.pdf"))
    assert r["source_type"] == "pdf"
    fields = {f["field"] for f in r["findings"]}
    assert "creation_date" in fields
    assert "author" not in fields  # empty string in the real file, not emitted


def test_pdf_author_is_reported_when_present(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    doc.set_metadata({"author": "Real Author Name", "title": "Synthetic Test Doc"})
    p = tmp_path / "authored.pdf"
    doc.save(str(p))
    doc.close()

    r = scan_metadata(str(p))
    findings = {f["field"]: f for f in r["findings"]}
    assert findings["author"]["value"] == "Real Author Name"
    assert findings["author"]["category"] == "identity"
    assert findings["title"]["category"] == "content"


def test_pdf_embedded_files_are_reported(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    doc.embfile_add("hidden.txt", b"synthetic embedded content", filename="hidden.txt")
    p = tmp_path / "with_embed.pdf"
    doc.save(str(p))
    doc.close()

    r = scan_metadata(str(p))
    embedded = [f for f in r["findings"] if f["category"] == "embedded_file"]
    assert len(embedded) == 1
    assert embedded[0]["value"] == "hidden.txt"
