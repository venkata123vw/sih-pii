"""
pipeline.py — P5's orchestration layer, wired to real teammate modules.

Status per track (as of this integration pass):
    ingestion.extract  — REAL function, STUB body. extract(filepath) always
                          returns the same fixed fake Aadhaar-only page,
                          regardless of what file you upload. This is not a
                          bug in pipeline.py or app.py — until ingestion
                          ships real OCR/PDF-text-layer code, every upload
                          will show the same detections. Re-run this file's
                          smoke test once ingestion.extract is real.
    detection.detect    — REAL. Regex + checksum, tuned FP rates.
    scoring.score       — REAL. confidence + policy resolution + NER hook
                          (NER itself is still a stub returning []).
    redaction.redact    — REAL. Mutates a PDF file ON DISK — very different
                          calling convention from the old stub (see apply()).

Three integration fixes made in this pass, worth telling the team about:

1. page_ctx shape. score()'s real context.find_page() does
   `for page in page_ctx.get("pages", [])` — it wants the WHOLE extraction
   dict, not a {page_num: text} lookup map (my first attempt at fixing the
   earlier "confidence stuck at 0.4" bug used the wrong shape). Fixed here:
   page_ctx = extraction, passed straight through.

2. extract() takes a filepath, not bytes. Streamlit gives you bytes, so
   analyze() writes them to a temp file first.

3. apply_redactions() writes to disk and returns a manifest dict, not
   (bytes, report) like the old stub. apply() below wraps it with temp
   files both ways and reads the output back into bytes for the UI.

KNOWN BUG (verified, blocks paste-text) — scoring/context.py line 81,
ocr_confidence(): `t["bbox"]` and _bbox_overlap() both unconditionally
unpack bbox as a 4-tuple. Any candidate with bbox=None (pasted text, CSV,
any coordinate-less source — explicitly legal per detect.py's own test
test_bbox_none_survives_fieldless_sources) crashes score() with a
KeyError/TypeError. File-upload works fine today only because ingestion's
current stub always fills in a bbox. Report to whoever owns scoring/ —
needs a None-guard before line 81. Until fixed, app.py catches this and
shows a friendly message instead of crashing on the paste-text tab.

KNOWN RISK — coordinate spaces: ingestion's fake bboxes are in OCR pixel
space (~1240x1754, roughly A4 at 150dpi). redact.py's apply_redactions()
expects PDF-point space (pymupdf's native coordinate system, e.g. ~595x842
for A4). These do NOT match. This won't surface as an error today because
ingestion is still a stub feeding fixed data into a test — but the moment
real OCR output gets wired in for scanned images, redaction boxes will
land in the wrong place unless someone converts pixel coords to PDF points
(or ingestion emits PDF-point coordinates directly for the OCR path). Flag
this to whoever owns ingestion + redaction before that swap happens.

ASSUMPTION TO VERIFY: redact.py is imported below as `redaction.redact`,
matching the detection/scoring package pattern. But test_redact.py and
test_p4_to_p2.py both do `from redact import ...` (no package prefix) —
if their test runner works, check whether redact.py actually lives at
repo root instead of inside redaction/, and fix the import below if so.
"""

import os
import tempfile

from ingestion.extract import extract as extract_real
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