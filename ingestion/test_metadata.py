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


def test_docx_reports_python_docx_authorship_metadata():
    """data/test_03.docx really was built with python-docx -- its own
    core properties say so. This is itself the kind of leak this scanner
    exists to catch (a document's authoring tool is on the record)."""
    r = scan_metadata(str(DATA_DIR / "test_03.docx"))
    assert r["source_type"] == "docx"
    findings = {f["field"]: f for f in r["findings"]}
    assert findings["author"]["value"] == "python-docx"
    assert findings["author"]["category"] == "identity"
    assert findings["created"]["category"] == "timestamp"


def test_docx_company_and_manager_reported_when_present(tmp_path):
    import zipfile
    import shutil

    src = DATA_DIR / "test_03.docx"
    dst = tmp_path / "with_company.docx"
    shutil.copy(src, dst)

    with zipfile.ZipFile(dst, "a") as z:
        app_xml = z.read("docProps/app.xml").decode("utf-8")
    app_xml = app_xml.replace("<Company/>", "<Company>Acme Synthetic Corp</Company>")
    app_xml = app_xml.replace("<Manager/>", "<Manager>Jamie Synthetic Manager</Manager>")

    # zipfile can't overwrite an entry in place -- rewrite the whole archive
    tmp_zip = tmp_path / "rebuilt.docx"
    with zipfile.ZipFile(dst) as zin, zipfile.ZipFile(tmp_zip, "w") as zout:
        for item in zin.infolist():
            data = app_xml.encode("utf-8") if item.filename == "docProps/app.xml" else zin.read(item.filename)
            zout.writestr(item, data)

    r = scan_metadata(str(tmp_zip))
    findings = {f["field"]: f for f in r["findings"]}
    assert findings["company"]["value"] == "Acme Synthetic Corp"
    assert findings["company"]["category"] == "organization"
    assert findings["manager"]["value"] == "Jamie Synthetic Manager"
    assert findings["manager"]["category"] == "identity"


def _make_synthetic_jpeg_with_exif(path, *, make=None, model=None, software=None, gps=None):
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    im = Image.new("RGB", (4, 4), color="red")
    exif = im.getexif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    if software:
        exif[0x0131] = software
    if gps:
        lat_deg, lat_ref, lon_deg, lon_ref = gps
        exif[0x8825] = {
            1: lat_ref, 2: tuple(IFDRational(v, 1) for v in lat_deg),
            3: lon_ref, 4: tuple(IFDRational(v, 1) for v in lon_deg),
        }
    im.save(path, format="jpeg", exif=exif)


def test_image_with_no_exif_has_no_findings(tmp_path):
    from PIL import Image

    p = tmp_path / "plain.jpg"
    Image.new("RGB", (4, 4), color="blue").save(p, format="jpeg")

    r = scan_metadata(str(p))
    assert r["source_type"] == "image"
    assert r["findings"] == []


def test_image_device_metadata_reported(tmp_path):
    p = tmp_path / "device.jpg"
    _make_synthetic_jpeg_with_exif(p, make="TestCam", model="TestModel X", software="TestSoftware")

    r = scan_metadata(str(p))
    findings = {f["field"]: f for f in r["findings"]}
    assert findings["camera_make"]["value"] == "TestCam"
    assert findings["camera_make"]["category"] == "device"
    assert findings["camera_model"]["value"] == "TestModel X"
    assert findings["software"]["category"] == "tooling"


def test_image_gps_decoded_to_decimal_degrees(tmp_path):
    p = tmp_path / "geotagged.jpg"
    _make_synthetic_jpeg_with_exif(
        p,
        gps=((12, 58, 0), "N", (77, 35, 0), "E"),
    )

    r = scan_metadata(str(p))
    findings = {f["field"]: f for f in r["findings"]}
    assert findings["gps_coordinates"]["category"] == "location"
    lat_str, lon_str = findings["gps_coordinates"]["value"].split(", ")
    assert abs(float(lat_str) - 12.9667) < 0.001
    assert abs(float(lon_str) - 77.5833) < 0.001


def test_image_gps_south_west_are_negative(tmp_path):
    p = tmp_path / "geotagged_sw.jpg"
    _make_synthetic_jpeg_with_exif(
        p,
        gps=((12, 58, 0), "S", (77, 35, 0), "W"),
    )

    r = scan_metadata(str(p))
    findings = {f["field"]: f for f in r["findings"]}
    lat_str, lon_str = findings["gps_coordinates"]["value"].split(", ")
    assert float(lat_str) < 0
    assert float(lon_str) < 0
