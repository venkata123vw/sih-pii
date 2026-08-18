"""
Combines checksum, keyword, doc-type, negative-signal and OCR signals
into a single confidence float, clamped to [0, 1].

Weighted linear sum -- see reference weight table. No decision trees.
"""

from scoring import context

WEIGHT_CHECKSUM_VALID = 0.4
WEIGHT_CHECKSUM_INVALID = -0.5
WEIGHT_KEYWORD_MATCH = 0.25
WEIGHT_DOC_TYPE_BOOST = 0.1
WEIGHT_NEGATIVE_SIGNAL = -0.3
OCR_CONF_DAMPEN_THRESHOLD = 0.7
NER_CONFIDENCE_CEILING = 0.5


def score(candidate: dict, page_context: dict) -> float:
    signals = context.get_signals(candidate, page_context)

    total = 0.0

    checksum_valid = candidate.get("checksum_valid")
    if checksum_valid is True:
        total += WEIGHT_CHECKSUM_VALID
    elif checksum_valid is False:
        total += WEIGHT_CHECKSUM_INVALID
    # checksum_valid is None -> neutral, no adjustment

    if signals["keyword_match"]:
        total += WEIGHT_KEYWORD_MATCH

    if signals["doc_type_boost"]:
        total += WEIGHT_DOC_TYPE_BOOST

    if signals["negative_match"]:
        total += WEIGHT_NEGATIVE_SIGNAL

    ocr_conf = signals["ocr_conf"]
    if ocr_conf is not None and ocr_conf < OCR_CONF_DAMPEN_THRESHOLD:
        total *= ocr_conf

    if candidate.get("match_source") == "ner":
        total = min(total, NER_CONFIDENCE_CEILING)

    return max(0.0, min(1.0, total))


def signal_reasons(candidate: dict, page_context: dict) -> list[str]:
    """Human-readable reasons for the signals that fed the score above."""
    signals = context.get_signals(candidate, page_context)
    reasons = []

    checksum_valid = candidate.get("checksum_valid")
    if checksum_valid is True:
        reasons.append("checksum_pass")
    elif checksum_valid is False:
        reasons.append("checksum_fail")

    if signals["keyword_match"]:
        reasons.append(f"keyword_nearby:{signals['keyword']}")

    if signals["doc_type_boost"]:
        reasons.append("doc_type_boost")

    if signals["negative_match"]:
        reasons.append(f"negative_signal:{signals['negative_keyword']}")

    ocr_conf = signals["ocr_conf"]
    if ocr_conf is not None and ocr_conf < OCR_CONF_DAMPEN_THRESHOLD:
        reasons.append(f"ocr_conf_dampened:{ocr_conf:.2f}")

    if candidate.get("match_source") == "ner":
        reasons.append("ner_ceiling_applied")

    return reasons
