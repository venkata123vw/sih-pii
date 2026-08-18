"""
pipeline.py — P5's orchestration layer, wired to real teammate modules.

Status per track (verified directly against each module, not assumed):
    ingestion.extract  — REAL. Native text-layer PDFs handled directly;
                          pages with no text layer fall back to OCR
                          (EasyOCR) automatically. Emits PDF-point-space
                          bboxes uniformly for both paths (see below).
    detection.detect    — REAL. Regex + checksum, tuned FP rates.
    scoring.score       — REAL. confidence + policy resolution + real NER
                          (spaCy en_core_web_sm — no longer a stub).
    redaction.redact    — REAL. Mutates a PDF file ON DISK — very different
                          calling convention from the old stub (see apply()).
    ingestion.metadata   — REAL. PDF/DOCX/image metadata scan, attached
                            additively as analysis["metadata"]. Not part
                            of the P3 scoring contract.

Three integration fixes made in an earlier pass, still relevant:

1. page_ctx shape. score()'s real context.find_page() does
   `for page in page_ctx.get("pages", [])` — it wants the WHOLE extraction
   dict, not a {page_num: text} lookup map. Fixed here: page_ctx =
   extraction, passed straight through.

2. extract() takes a filepath, not bytes. Streamlit gives you bytes, so
   analyze() writes them to a temp file first.

3. apply_redactions() writes to disk and returns a manifest dict, not
   (bytes, report) like the old stub. apply() below wraps it with temp
   files both ways and reads the output back into bytes for the UI.

RESOLVED — bbox=None crash on paste-text/CSV: two separate bugs, both
fixed. scoring/context.py's ocr_confidence() used to unpack bbox as a
4-tuple unconditionally; scoring/ner.py's _bbox_for_span() had the same
issue for NER-derived detections specifically (needed a name/address in
the text to trigger, not just a bare coordinate-less candidate). Both
now treat bbox=None as the legal state it is for coordinate-less sources
(pasted text, CSV) rather than crashing or silently dropping the
detection. If paste-text still crashes with a 'bbox' KeyError after
pulling this, that's a different bug — get the full server-side
traceback rather than assuming it's either of these two again.

RESOLVED — coordinate spaces: ingestion.extract() emits bboxes in PDF
points for both the native-text and OCR paths (documented and enforced
in its own module docstring), matching what redact.py expects. There is
no pixel/point mismatch to convert.

RESOLVED — redact.py's location: it lives in redaction/redact.py, and
the package-qualified import below is correct. redaction/test_redact.py
and test_p4_to_p2.py use a different (`from redact import ...`) style
because they're run standalone from within redaction/ itself — same
dual-convention pattern scoring/'s own tests use, not a bug.
"""

import os
import tempfile

from ingestion.extract import extract as extract_real
from ingestion.metadata import scan_metadata
from detection.detect import detect as detect_real
from scoring.score import score as score_real
from redaction.redact import apply_redactions  # see assumption note above

PROFILES = ["PUBLIC_DISCLOSURE", "THIRD_PARTY_SERVICE", "REGULATED_KYC", "INTERNAL_REVIEW"]


# ---------------------------------------------------------------------
# analyze() — extract -> detect -> score. No mutation of the source file.
# ---------------------------------------------------------------------
def analyze(file_bytes, filename, profile,
            extract_fn=extract_real, detect_fn=detect_real, score_fn=score_real):
    """Runs extract -> detect -> score. Returns findings for user review.
    A temp copy of the upload is made because extract() needs a filepath;
    it's deleted before this function returns."""
    suffix = os.path.splitext(filename)[1] or ".pdf"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)

        extraction = extract_fn(tmp_path)
        candidates = detect_fn(extraction)
        # page_ctx = the whole extraction dict — see module docstring, fix (1)
        scored = score_fn(candidates, profile, extraction)
        # Additive only — metadata_findings has not been proposed to
        # scoring/policy, so it rides alongside detections, not inside them.
        scored["metadata"] = scan_metadata(tmp_path)
    finally:
        os.unlink(tmp_path)

    _add_review_defaults(scored)
    return scored


def analyze_pasted_text(text, profile, detect_fn=detect_real, score_fn=score_real):
    """Same pipeline for the paste-text entry path — there's no file, so
    this skips extract() entirely and builds the extraction shape directly
    from the pasted text, then runs detect -> score as normal."""
    # detect.py scans page['tokens'], NOT full_text directly — an empty
    # tokens list here would silently detect nothing no matter what was
    # pasted. bbox/ocr_conf are omitted (legal — see detect.py's
    # _union_bbox and confs handling, both None-safe for CSV/text sources).
    tokens = [{"text": w} for w in text.split()]
    fake_extraction = {
        "doc_id": "pasted-text",
        "source_type": "plain_text",
        "pages": [{"page_num": 0, "width": 0, "height": 0, "tokens": tokens, "full_text": text}],
    }
    candidates = detect_fn(fake_extraction)
    scored = score_fn(candidates, profile, fake_extraction)
    _add_review_defaults(scored)
    return scored


def _add_review_defaults(scored):
    """P5's addition on top of the P3 contract: a default checkbox state
    for the human-in-the-loop review UI. Real score() does not emit this
    field — mutate it in here, once, right after scoring."""
    for d in scored["detections"]:
        d.setdefault("user_confirmed", d["policy_action"] in ("REMOVE", "MASK"))


# ---------------------------------------------------------------------
# apply() — redact ONLY user-confirmed detections.
# ---------------------------------------------------------------------
def apply(file_bytes, filename, analysis, flag_action="REMOVE", redact_fn=apply_redactions):
    """Takes the full analysis dict (as returned by analyze()) and applies
    redaction. Detections the user did NOT confirm are forced to
    policy_action="KEEP" before calling the real redactor — redact.py only
    understands policy_action, it has no concept of "confirmed", so this
    is where P5's human-in-the-loop rule actually gets enforced.

    Only works on file uploads — pasted text has no file to redact.
    Returns (output_bytes, report)."""
    if file_bytes is None:
        raise ValueError("apply() needs the original file — pasted text has no "
                          "redaction target; detection/alert only for that path.")

    detections = []
    for d in analysis["detections"]:
        d = dict(d)
        if not d.get("user_confirmed"):
            d["policy_action"] = "KEEP"
        detections.append(d)

    decisions = {
        "doc_id": analysis["doc_id"],
        "context_profile": analysis["context_profile"],
        "detections": detections,
        "excess_pii_alert": analysis["excess_pii_alert"],
    }

    suffix = os.path.splitext(filename)[1] or ".pdf"
    fd, in_path = tempfile.mkstemp(suffix=suffix)
    out_path = in_path + ".out" + suffix
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)

        manifest = redact_fn(in_path, decisions, out_path, flag_action=flag_action)

        with open(out_path, "rb") as f:
            output_bytes = f.read()
    finally:
        os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)

    counts = manifest["counts"]
    report = {
        "removed": counts["REMOVE"],
        "masked": counts["MASK"],
        "kept": counts["KEEP"],
        "flagged": counts["FLAG"],
        "no_bbox": counts["no_bbox"],
        "verified": manifest["verified"],
    }
    return output_bytes, report