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


def scan_metadata(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _scan_pdf(filepath)
    return {"source_type": "unsupported", "findings": []}
