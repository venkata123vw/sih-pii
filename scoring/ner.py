"""
NAME/ADDRESS detection via spaCy en_core_web_sm (pretrained, no training).

SETUP: `pip install spacy` alone is not enough -- the model itself is a
separate download. After installing requirements, also run:
    python -m spacy download en_core_web_sm
Skipping this raises OSError: Can't find model 'en_core_web_sm' the first
time detect() runs, on any machine that hasn't run it before (a fresh
clone, a demo laptop).

spaCy has no dedicated ADDRESS label, so GPE/LOC/FAC (city, state, road,
landmark names) are mapped to ADDRESS as an approximation -- this catches
locality names but not house numbers or PIN codes (spotchecked: a PIN code
like "560001" gets misclassified as DATE by the English model, not
captured here at all). PERSON -> NAME handled Indian names fine in manual
spotchecks (e.g. "Ravi Kumar", "Priya Sharma"), but en_core_web_sm is an
English-general model with no Indian-name-specific training, so it also
frequently mislabels unfamiliar Indian locality names as PERSON (verified
directly against the model: "Shahdara Mandoli", "Whitefield Marathahalli",
and "Bangalore Karnataka" all come back PERSON, not GPE/LOC). Retraining
or swapping the model is out of scope here; instead, _reclassify_address()
below reclassifies a PERSON entity to ADDRESS when it sits soon after an
explicit "Address"/"पता" label in the same text -- the same
keyword-proximity idiom scoring/context.py already uses elsewhere in this
project, applied to a spaCy-label problem instead of a regex one. This is
a targeted patch, not a fix for the model's underlying blind spot: a
locality name with no address label nearby (e.g. mentioned in free text)
will still come through mislabeled.

Confidence for every NER detection is capped at 0.5 by confidence.py
(NER has no structural proof the way checksum-backed regex matches do).
"""

import spacy

from scoring import confidence, resolver

_ENTITY_TO_PII_TYPE = {
    "PERSON": "NAME",
    "GPE": "ADDRESS",
    "LOC": "ADDRESS",
    "FAC": "ADDRESS",
}

# How far back to look for an address label before reclassifying a
# PERSON-labeled entity to ADDRESS. Wider than context.py's VID_LABEL_GAP
# (15 chars) on purpose: an "Address"/"पता" label governs the whole
# following block (often several wrapped lines), not just the next word --
# spotchecked against a real card layout, the mislabeled locality name
# sat ~35 chars after the label. 150 covers a couple of wrapped lines
# without reaching into unrelated fields on the same page.
_ADDRESS_LABEL_GAP = 150
_ADDRESS_LABELS = ("address", "पता")  # "पता" -- Hindi for "address"

# Common Indian ID-document field-label abbreviations that spaCy
# sometimes classifies as PERSON when they appear as standalone
# capitalized tokens -- verified directly: "VID" scored as a NAME
# candidate at 0.50 confidence on a real Aadhaar card (the card's own
# "VID" label, not a name). Exact match only (case-insensitive) against
# the whole entity text, so a real name that merely contains one of
# these as a substring is untouched. These are never real names, so
# they're dropped outright rather than reclassified or down-weighted.
_NON_NAME_LABELS = frozenset({"vid", "pan", "dob", "dl", "epic", "poi", "poa", "uid", "uidai"})

_nlp = None


def _load_model():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def _token_spans(full_text: str, tokens: list[dict]) -> list[tuple[int, int, dict]]:
    """
    Locate each token's (start, end) char offset within full_text.

    Tokens carry no offset in the P2 contract (just text + bbox), so this
    reconstructs one via sequential search -- assumes tokens appear in
    full_text in the same order P2 emitted them, which holds for every
    page.tokens list seen so far.
    """
    spans = []
    cursor = 0
    for tok in tokens:
        idx = full_text.find(tok["text"], cursor)
        if idx == -1:
            continue
        spans.append((idx, idx + len(tok["text"]), tok))
        cursor = idx + len(tok["text"])
    return spans


def _bbox_for_span(spans: list[tuple[int, int, dict]], start: int, end: int) -> list | None:
    """
    Union bbox of every token overlapping [start, end).

    None if no token overlaps, or if none of the overlapping tokens carry
    a bbox at all -- pasted-text tokens are built as {"text": w} only (see
    pipeline.py's analyze_pasted_text()), with no bbox/ocr_conf keys.
    Coordinate-less is a legal state throughout this contract (detect.py
    emits bbox=None for CSV/text sources too), not an error case.
    """
    matching = [tok for (s, e, tok) in spans if s < end and start < e]
    usable = [t for t in matching if t.get("bbox") is not None]
    if not usable:
        return None
    return [
        min(t["bbox"][0] for t in usable),
        min(t["bbox"][1] for t in usable),
        max(t["bbox"][2] for t in usable),
        max(t["bbox"][3] for t in usable),
    ]


def _reclassify_address(full_text: str, start_char: int) -> bool:
    """True if an "Address"/"पता" label appears within _ADDRESS_LABEL_GAP
    chars before this entity -- see the module docstring for why this
    exists and its limits."""
    preceding = full_text[max(0, start_char - _ADDRESS_LABEL_GAP):start_char].lower()
    return any(label in preceding for label in _ADDRESS_LABELS)


def detect(page: dict, profile: str, policy_matrix: dict) -> list[dict]:
    full_text = page.get("full_text", "")
    if not full_text.strip():
        return []

    doc = _load_model()(full_text)
    spans = _token_spans(full_text, page.get("tokens", []))
    page_ctx = {"pages": [page]}

    detections = []
    for ent in doc.ents:
        pii_type = _ENTITY_TO_PII_TYPE.get(ent.label_)
        if pii_type is None:
            continue

        if pii_type == "NAME" and ent.text.strip().lower() in _NON_NAME_LABELS:
            continue  # a document field-label abbreviation, not a real name

        reclassified = pii_type == "NAME" and _reclassify_address(full_text, ent.start_char)
        if reclassified:
            pii_type = "ADDRESS"

        # bbox=None is reported, not dropped -- consistent with how regex
        # candidates from coordinate-less sources (pasted text, CSV) are
        # already handled everywhere else in this contract. Silently
        # skipping would under-report real PII that NER did find, just
        # because the source had no page coordinates to attach it to.
        bbox = _bbox_for_span(spans, ent.start_char, ent.end_char)

        candidate = {
            "pii_type": pii_type, "value": ent.text, "page_num": page["page_num"],
            "bbox": bbox, "checksum_valid": None, "match_source": "ner",
        }
        conf = confidence.score(candidate, page_ctx)
        reasons = confidence.signal_reasons(candidate, page_ctx)
        if reclassified:
            reasons = reasons + ["reclassified_address_context"]
        action, necessity, resolver_reasons = resolver.resolve(
            {**candidate, "confidence": conf}, profile, policy_matrix
        )
        detections.append({
            **candidate,
            "confidence": conf,
            "policy_action": action,
            "necessity": necessity,
            "reasons": reasons + resolver_reasons,
        })

    return detections
