"""
NAME/ADDRESS detection via spaCy en_core_web_sm (pretrained, no training).

spaCy has no dedicated ADDRESS label, so GPE/LOC/FAC (city, state, road,
landmark names) are mapped to ADDRESS as an approximation -- this catches
locality names but not house numbers or PIN codes (spotchecked: a PIN code
like "560001" gets misclassified as DATE by the English model, not
captured here at all). PERSON -> NAME handled Indian names fine in manual
spotchecks (e.g. "Ravi Kumar", "Priya Sharma"), but en_core_web_sm is an
English-general model with no Indian-name-specific training -- state this
limitation openly rather than overselling recall on Indian names.

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
    """Union bbox of every token overlapping [start, end). None if no token overlaps."""
    matching = [tok for (s, e, tok) in spans if s < end and start < e]
    if not matching:
        return None
    return [
        min(t["bbox"][0] for t in matching),
        min(t["bbox"][1] for t in matching),
        max(t["bbox"][2] for t in matching),
        max(t["bbox"][3] for t in matching),
    ]


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

        bbox = _bbox_for_span(spans, ent.start_char, ent.end_char)
        if bbox is None:
            continue  # no token overlaps this span, can't place it on the page

        candidate = {
            "pii_type": pii_type, "value": ent.text, "page_num": page["page_num"],
            "bbox": bbox, "checksum_valid": None, "match_source": "ner",
        }
        conf = confidence.score(candidate, page_ctx)
        reasons = confidence.signal_reasons(candidate, page_ctx)
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
