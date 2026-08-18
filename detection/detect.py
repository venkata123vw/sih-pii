"""
P1 detection engine — turns extracted tokens into candidate PII spans.

The validators (verhoeff.py, luhn.py, pan.py) answer "is this string a
valid X?". This module answers the actual P1 question: "where in this
document is there an X?" — which needs token joining and union bboxes,
because OCR splits "2341 2341 2346" into three tokens.

Contract: consumes P2's extraction output, emits P1 -> P3 candidates.
"""
from detection.verhoeff import validate_aadhaar
from detection.luhn import is_card_number
import re

# ---------------------------------------------------------------------
# Pattern registry. Adding a PII type = adding a dict entry, no engine
# changes. This is the "extensible beyond the initial three" answer.
#
#   window:    max adjacent tokens to join before testing
#   pattern:   pre-filter on the joined+normalised string (cheap)
#   validator: None = format-only, so checksum_valid stays None
#   priority:  higher wins when two types claim overlapping spans
# ---------------------------------------------------------------------
REGISTRY = {
    'AADHAAR': dict(
        window=4, priority=90,
        pattern=re.compile(r'^[2-9]\d{11}$'),
        validator=validate_aadhaar,
        strip=' -'),
    'CREDIT_CARD': dict(
        window=5, priority=85,
        pattern=re.compile(r'^\d{12,19}$'),
        validator=is_card_number,
        strip=' -'),
    'PAN': dict(
        window=2, priority=88,
        pattern=re.compile(r'^[A-Z]{5}\d{4}[A-Z]$'),
        # PAN's check-digit algorithm is unpublished by ITD/NSDL/UTIITSL,
        # so there is no checksum to run: format only, checksum_valid=None.
        # detection.pan.pan_signals() exposes entity-code and serial
        # checks to P3 as confidence signals rather than gates.
        validator=None,
        strip=' -'),
    'VOTER_ID': dict(
        window=2, priority=60,
        pattern=re.compile(r'^[A-Z]{3}\d{7}$'),
        validator=None, strip=' -'),
    'PASSPORT': dict(
        window=2, priority=60,
        pattern=re.compile(r'^[A-PR-WY][1-9]\d{6}$'),
        validator=None, strip=' -'),
    'PHONE': dict(
        window=3, priority=40,
        pattern=re.compile(r'^(?:\+?91)?[6-9]\d{9}$'),
        validator=None, strip=' -()'),
    'EMAIL': dict(
        window=1, priority=50,
        pattern=re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$'),
        validator=None, strip=''),
}


def _union_bbox(tokens):
    """Union box across a token run. None-safe for CSV/field sources."""
    boxes = [t['bbox'] for t in tokens if t.get('bbox')]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _normalise(raw, strip_chars):
    for ch in strip_chars:
        raw = raw.replace(ch, '')
    return raw.upper()


def _scan_page(page, doc_id):
    tokens = page.get('tokens', [])
    hits = []
    for pii_type, spec in REGISTRY.items():
        for start in range(len(tokens)):
            for length in range(1, spec['window'] + 1):
                run = tokens[start:start + length]
                if len(run) < length:
                    break
                raw = ' '.join(t['text'] for t in run)
                norm = _normalise(raw, spec['strip'])
                if not spec['pattern'].match(norm):
                    continue
                validator = spec['validator']
                if validator is None:
                    checksum_valid = None
                else:
                    if not validator(norm):
                        continue          # pattern matched, checksum failed
                    checksum_valid = True
                confs = [t.get('ocr_conf', 1.0) for t in run]
                hits.append({
                    'pii_type': pii_type,
                    'value': raw,
                    'page_num': page['page_num'],
                    'bbox': _union_bbox(run),
                    'checksum_valid': checksum_valid,
                    'match_source': 'regex',
                    'ocr_conf': min(confs) if confs else 1.0,
                    '_span': (start, start + length),
                    '_priority': spec['priority'],
                })
    return hits


def _resolve_overlaps(hits):
    """
    Two types can claim the same tokens (a 16-digit RuPay also contains
    a 12-digit Verhoeff-valid run). Keep the longest span; break ties on
    priority. Drop anything fully contained in a survivor.
    """
    ordered = sorted(hits, key=lambda h: (-(h['_span'][1] - h['_span'][0]),
                                          -h['_priority']))
    kept = []
    for h in ordered:
        s, e = h['_span']
        if any(k['_span'][0] <= s and e <= k['_span'][1] for k in kept):
            continue
        kept.append(h)
    for h in kept:
        h.pop('_span'), h.pop('_priority')
    return kept


def detect(extraction) -> dict:
    """extraction = P2's output dict. Returns the P1 -> P3 contract."""
    doc_id = extraction['doc_id']
    candidates = []
    for page in extraction.get('pages', []):
        candidates.extend(_resolve_overlaps(_scan_page(page, doc_id)))
    return {'doc_id': doc_id, 'candidates': candidates}