"""
P4 — redaction.

Consumes the return value of `scoring.score.score()` verbatim and burns the
selected values out of a PDF's text layer.

Contract notes (why this file looks the way it does):

* The value field is `value`, not `text`. Detection emits `value` and scoring
  carries it through unchanged.
* `policy_action` gates redaction. It is NOT optional and it is NOT advisory:
  a detection marked KEEP must come out of this function untouched.
* `bbox` may be `None` for sources with no coordinates (CSV, plain text).
  Those cannot be redacted geometrically and are reported as skipped, not
  crashed on.
* Coordinates are top-left origin and pages are zero-indexed, matching
  PyMuPDF's own convention, so bboxes pass straight through to `pymupdf.Rect`.
  Verified against rotated pages too — `get_text("words")` coordinates and
  `add_redact_annot` share a coordinate space regardless of `page.rotation`.
* `add_redact_annot` + `apply_redactions` removes glyphs from the content
  stream. A drawn rectangle would not. Never swap this for a draw call.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pymupdf

# --- policy_action vocabulary, from scoring/resolver.py ----------------------

REDACTING_ACTIONS = frozenset({"REMOVE", "MASK"})
PASSTHROUGH_ACTIONS = frozenset({"KEEP"})
REVIEW_ACTIONS = frozenset({"FLAG"})
VALID_ACTIONS = REDACTING_ACTIONS | PASSTHROUGH_ACTIONS | REVIEW_ACTIONS


class RedactionError(RuntimeError):
    """Raised when redaction did not achieve what it claimed to."""


# --- helpers -----------------------------------------------------------------

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Collapse whitespace so verification survives extraction line breaks."""
    return _WS.sub(" ", text)


def mask_value(value: str, visible_tail: int = 4) -> str:
    """
    Replacement string for MASK: keep the last `visible_tail` alphanumeric
    characters, X out everything before them, preserve separators.

        "1234 5678 9012" -> "XXXX XXXX 9012"
        "ABCDE1234F"     -> "XXXXXX234F"
        "rithika@example.com" -> "XXXXXXX@XXXXXXX.com"
    """
    alnum_positions = [i for i, ch in enumerate(value) if ch.isalnum()]
    keep_from = len(alnum_positions) - max(visible_tail, 0)
    keep = set(alnum_positions[keep_from:]) if keep_from < len(alnum_positions) else set()
    return "".join(
        ch if (not ch.isalnum() or i in keep) else "X" for i, ch in enumerate(value)
    )


def _validate(detection: dict, index: int, page_count: int) -> None:
    """Fail loudly on contract violations before touching the document."""
    for field in ("page_num", "policy_action", "value"):
        if field not in detection:
            raise ValueError(
                f"detections[{index}] is missing required field {field!r}. "
                f"Expected the shape returned by scoring.score.score()."
            )

    action = detection["policy_action"]
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"detections[{index}] has unknown policy_action {action!r}. "
            f"Expected one of {sorted(VALID_ACTIONS)}."
        )

    page_num = detection["page_num"]
    if not isinstance(page_num, int) or isinstance(page_num, bool):
        raise ValueError(f"detections[{index}] page_num must be an int, got {page_num!r}")
    if page_num < 0 or page_num >= page_count:
        raise ValueError(
            f"detections[{index}] invalid page_num: {page_num} "
            f"(document has {page_count} pages, zero-indexed)"
        )

    bbox = detection.get("bbox")
    if bbox is None:
        return  # legitimate: coordinate-less source. Handled as a skip.

    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError(
            f"detections[{index}] invalid bbox: expected 4 numbers, got {bbox!r}"
        )
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox):
        raise ValueError(f"detections[{index}] invalid bbox: non-numeric value in {bbox!r}")

    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        raise ValueError(
            f"detections[{index}] invalid bbox: {list(bbox)} has zero or negative "
            f"area (needs x1 > x0 and y1 > y0, top-left origin)"
        )


def _record(detection: dict, reason: str) -> dict:
    return {
        "pii_type": detection.get("pii_type"),
        "page_num": detection.get("page_num"),
        "policy_action": detection.get("policy_action"),
        "confidence": detection.get("confidence"),
        "necessity": detection.get("necessity"),
        "reason": reason,
    }


# --- main entry point ---------------------------------------------------------

def apply_redactions(
    filepath: str,
    decisions: dict,
    out_path: str,
    *,
    flag_action: str = "REMOVE",
    mask_visible_tail: int = 4,
    verify: bool = True,
) -> dict:
    """
    Apply PII redactions to a PDF according to per-detection policy_action.

    Args:
        filepath: source PDF.
        decisions: the dict returned by `scoring.score.score()`.
        out_path: destination PDF. Must differ from `filepath`.
        flag_action: how to treat policy_action == "FLAG" — "REMOVE" (fail
            closed, the default), "MASK", or "SKIP". FLAG means a human has to
            look at it; defaulting to REMOVE means the leaked-PII failure mode
            requires someone to actively opt into it.
        mask_visible_tail: alphanumeric characters left readable under MASK.
        verify: re-extract the output text and confirm every redacted value is
            actually gone. Leave this on.

    Returns:
        A manifest dict (see `redacted` / `skipped` / `counts` keys). This is
        P4's own output contract — P5 consumes it.

    Raises:
        ValueError: on a contract violation in `decisions`.
        RedactionError: if a value survives into the output text layer.
    """
    if flag_action not in {"REMOVE", "MASK", "SKIP"}:
        raise ValueError(f"flag_action must be REMOVE, MASK or SKIP, got {flag_action!r}")
    if os.path.abspath(filepath) == os.path.abspath(out_path):
        raise ValueError("out_path must differ from filepath; in-place redaction is unsafe")

    detections = decisions.get("detections", [])
    if not isinstance(detections, list):
        raise ValueError(f"decisions['detections'] must be a list, got {type(detections).__name__}")

    manifest: dict[str, Any] = {
        "doc_id": decisions.get("doc_id"),
        "context_profile": decisions.get("context_profile"),
        "out_path": out_path,
        "redacted": [],
        "skipped": [],
        "counts": {"REMOVE": 0, "MASK": 0, "KEEP": 0, "FLAG": 0, "no_bbox": 0},
        "verified": False,
    }

    doc = pymupdf.open(filepath)
    try:
        # Phase 1: validate everything. No mutation until the whole payload is
        # known-good, so a bad detection at index 9 can't leave a half-redacted
        # document behind.
        for i, detection in enumerate(detections):
            _validate(detection, i, len(doc))

        # Phase 2: mutate.
        burned: list[str] = []
        for detection in detections:
            action = detection["policy_action"]
            manifest["counts"][action] += 1

            if action in PASSTHROUGH_ACTIONS:
                manifest["skipped"].append(_record(detection, "policy:KEEP"))
                continue

            effective = flag_action if action == "FLAG" else action
            if effective == "SKIP":
                manifest["skipped"].append(_record(detection, "policy:FLAG:deferred_to_review"))
                continue

            bbox = detection.get("bbox")
            if bbox is None:
                manifest["counts"]["no_bbox"] += 1
                manifest["skipped"].append(_record(detection, "no_bbox:coordinate_less_source"))
                continue

            page = doc[detection["page_num"]]
            rect = pymupdf.Rect(*bbox) & page.rect
            if rect.is_empty:
                manifest["skipped"].append(_record(detection, "bbox_outside_page_bounds"))
                continue

            if effective == "MASK":
                page.add_redact_annot(
                    rect,
                    text=mask_value(detection["value"], mask_visible_tail),
                    fontname="helv",
                    fontsize=min(11, rect.height * 0.7),
                    fill=(1, 1, 1),
                    text_color=(0, 0, 0),
                    cross_out=False,
                )
            else:  # REMOVE
                page.add_redact_annot(rect, fill=(0, 0, 0), cross_out=False)

            burned.append(detection["value"])
            manifest["redacted"].append(_record(detection, f"applied:{effective}"))

        for page in doc:
            # PDF_REDACT_IMAGE_PIXELS blanks pixels under the rect, which is
            # what the scanned/OCR path needs — a scanned Aadhaar is an image,
            # not text, and removing only the text layer would redact nothing.
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()

    if verify:
        surviving = _verify(out_path, burned)
        if surviving:
            raise RedactionError(
                f"{len(surviving)} value(s) still extractable from {out_path} after "
                f"redaction. Redaction did not do what it reported."
            )
        manifest["verified"] = True

    return manifest


def _verify(out_path: str, burned: list[str]) -> list[str]:
    doc = pymupdf.open(out_path)
    try:
        text = _normalize("".join(page.get_text() for page in doc))
    finally:
        doc.close()
    return [v for v in burned if _normalize(v) in text]
