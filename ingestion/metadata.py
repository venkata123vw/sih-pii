"""
P2 - Metadata Scanner

Scans a document for identity-revealing metadata that never shows up in
the visible page content: PDF document-info fields, embedded files, and
hidden (OCG) layers today; DOCX core/extended properties and image EXIF
(including GPS) are added in later tasks.

metadata_findings has NOT been proposed to scoring/ or policy/ yet -- do
not wire this into detect()/score() or policy/profiles.yaml. It is a
standalone, additive output surfaced only for direct display.

    scan_metadata(filepath: str) -> dict

{
    "source_type": "pdf" | "docx" | "image" | "unsupported",
    "findings": [
        {"field": "author", "value": "...", "category": "identity"},
        ...
    ],
}

Only non-empty fields are emitted -- an absent field means "not present
in this document", not "checked and blank".
"""
import os
import zipfile
from xml.etree import ElementTree

import docx
import pymupdf

# field -> category. Fields not listed here are skipped even if pymupdf
# returns them (e.g. 'format', 'trapped' aren't identity-revealing).
_PDF_INFO_FIELDS = {
    "author": "identity",
    "creator": "tooling",
    "producer": "tooling",
    "title": "content",
    "subject": "content",
    "keywords": "content",
    "creationDate": "timestamp",
    "modDate": "timestamp",
}
_PDF_FIELD_NAMES = {
    "author": "author",
    "creator": "creator_application",
    "producer": "pdf_producer",
    "title": "title",
    "subject": "subject",
    "keywords": "keywords",
    "creationDate": "creation_date",
    "modDate": "modification_date",
}


def _scan_pdf(filepath):
    findings = []
    doc = pymupdf.open(filepath)
    try:
        info = doc.metadata or {}
        for key, category in _PDF_INFO_FIELDS.items():
            value = info.get(key)
            if value:
                findings.append({
                    "field": _PDF_FIELD_NAMES[key],
                    "value": value,
                    "category": category,
                })

        if info.get("encryption"):
            findings.append({
                "field": "encryption",
                "value": info["encryption"],
                "category": "form",
            })

        for name in doc.embfile_names():
            findings.append({
                "field": "embedded_file",
                "value": name,
                "category": "embedded_file",
            })

        for layer in doc.get_layers():
            layer_name = layer.get("name") if isinstance(layer, dict) else str(layer)
            findings.append({
                "field": "hidden_layer",
                "value": layer_name,
                "category": "hidden_layer",
            })

        if doc.is_form_pdf:
            findings.append({
                "field": "has_form_fields",
                "value": "true",
                "category": "form",
            })
    finally:
        doc.close()

    return {"source_type": "pdf", "findings": findings}


_DOCX_CORE_FIELDS = {
    "author": "identity",
    "last_modified_by": "identity",
    "created": "timestamp",
    "modified": "timestamp",
    "revision": "tooling",
    "title": "content",
    "subject": "content",
    "keywords": "content",
    "comments": "content",
    "category": "content",
}

_APP_XML_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
_APP_XML_FIELDS = {
    "Company": ("company", "organization"),
    "Manager": ("manager", "identity"),
    "Application": ("application", "tooling"),
}


def _scan_docx_app_properties(filepath):
    """docProps/app.xml isn't exposed by python-docx's core_properties --
    Company/Manager/Application live only here, parsed directly."""
    findings = []
    with zipfile.ZipFile(filepath) as zf:
        if "docProps/app.xml" not in zf.namelist():
            return findings
        root = ElementTree.fromstring(zf.read("docProps/app.xml"))

    for tag, (field, category) in _APP_XML_FIELDS.items():
        el = root.find(f"{_APP_XML_NS}{tag}")
        if el is not None and el.text and el.text.strip():
            findings.append({"field": field, "value": el.text.strip(), "category": category})
    return findings


def _scan_docx(filepath):
    findings = []
    cp = docx.Document(filepath).core_properties
    for attr, category in _DOCX_CORE_FIELDS.items():
        value = getattr(cp, attr, None)
        if value in (None, ""):
            continue
        findings.append({"field": attr, "value": str(value), "category": category})

    findings.extend(_scan_docx_app_properties(filepath))
    return {"source_type": "docx", "findings": findings}


def scan_metadata(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _scan_pdf(filepath)
    if ext == ".docx":
        return _scan_docx(filepath)
    return {"source_type": "unsupported", "findings": []}
