"""
Combines checksum, keyword, doc-type, negative-signal and OCR signals
into a single confidence float, clamped to [0, 1].

Weighted linear sum -- see reference weight table. No decision trees.
"""

from detection.pan import pan_signals

from scoring import context

WEIGHT_CHECKSUM_VALID = 0.4
WEIGHT_CHECKSUM_INVALID = -0.5
WEIGHT_KEYWORD_MATCH = 0.25
WEIGHT_DOC_TYPE_BOOST = 0.1
WEIGHT_NEGATIVE_SIGNAL = -0.3
# Stronger than a generic negative signal: "vid" directly labeling this
# specific match is close to structural proof it's the VID field, not a
# real AADHAAR/PHONE/CREDIT_CARD value -- see context.vid_adjacent()
# and context.VID_VULNERABLE_TYPES.
WEIGHT_VID_ADJACENT = -0.4
OCR_CONF_DAMPEN_THRESHOLD = 0.7
NER_CONFIDENCE_CEILING = 0.5

# PAN has no published checksum (checksum_valid stays None -- see
# detection/pan.py). validate_pan() is format-only there by design;
# entity-code and serial-number plausibility are exposed as signals via
# pan_signals() instead of being a hard gate, so they're weighed here.
WEIGHT_PAN_UNKNOWN_ENTITY_CODE = -0.15
WEIGHT_PAN_ZERO_SERIAL = -0.25


def _pan_signals_for(candidate: dict) -> dict | None:
    if candidate.get("pii_type") != "PAN":
        return None
    return pan_signals(candidate["value"])


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

    if signals["vid_adjacent"]:
        total += WEIGHT_VID_ADJACENT

    pan = _pan_signals_for(candidate)
    if pan is not None:
        if not pan["known_entity_code"]:
            total += WEIGHT_PAN_UNKNOWN_ENTITY_CODE
        if not pan["serial_nonzero"]:
            total += WEIGHT_PAN_ZERO_SERIAL

    is_ner = candidate.get("match_source") == "ner"
    if is_ner:
        # NER itself is a signal, not a neutral default -- a bare NER hit
        # with nothing else should land at the ceiling, not at 0. Other
        # signals (negative_match especially) can still pull it back down.
        total += NER_CONFIDENCE_CEILING

    ocr_conf = signals["ocr_conf"]
    if ocr_conf is not None and ocr_conf < OCR_CONF_DAMPEN_THRESHOLD:
        total *= ocr_conf

    if is_ner:
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

    if signals["vid_adjacent"]:
        reasons.append("vid_adjacent")

    pan = _pan_signals_for(candidate)
    if pan is not None:
        if not pan["known_entity_code"]:
            reasons.append("pan_unknown_entity_code")
        if not pan["serial_nonzero"]:
            reasons.append("pan_zero_serial")

    if candidate.get("match_source") == "ner":
        reasons.append("ner_match")

    ocr_conf = signals["ocr_conf"]
    if ocr_conf is not None and ocr_conf < OCR_CONF_DAMPEN_THRESHOLD:
        reasons.append(f"ocr_conf_dampened:{ocr_conf:.2f}")

    return reasons
