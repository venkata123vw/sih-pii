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
#   window:           max adjacent tokens to join before testing
#   pattern:          pre-filter on the joined+normalised string (cheap)
#   validator:        None = format-only, so checksum_valid stays None
#   priority:         higher wins when two types claim overlapping spans
#   corroboration:    optional. For types whose bare form is genuinely
#                     ambiguous with ordinary document noise.
#                     The candidate is kept if ANY listed signal fires:
#                       self_evident — regex on the normalised string that
#                                      only a real identifier would match
#                                      (e.g. an explicit +91 / 0 prefix)
#                       raw_grouped  — regex on the UNSTRIPPED run, i.e. the
#                                      value arrived punctuated or grouped
#                       keywords     — one of these appears in the page text
#                     If none fire, the candidate is dropped.
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

    # -----------------------------------------------------------------
    # Driving Licence
    #
    # The project fixture uses the synthetic format:
    #
    #     DL-SYN-2026-45821
    #
    # After normalization:
    #
    #     DLSYN202645821
    #
    # This is 5 letters followed by 9 digits.
    #
    # The format alone is deliberately not enough to classify a value
    # as a driving licence because identifiers with similar structure
    # can occur in ordinary documents. Require driving-licence context.
    #
    # There is no checksum to validate for this synthetic project
    # format, so checksum_valid remains None.
    # -----------------------------------------------------------------
    'DL': dict(
        window=4,
        priority=70,
        pattern=re.compile(r'^[A-Z]{5}\d{9}$'),
        corroboration=dict(
            keywords=(
                'dl no',
                'driving licence',
                'driving license',
                'licence number',
                'license number',
            ),
        ),
        validator=None,
        strip=' -'),

    # EPIC really is AAA9999999 — identical in shape to courier tracking
    # and reference codes (measured: 20% FP). The string alone cannot
    # distinguish them, so require a keyword in the page text.
    'VOTER_ID': dict(
        window=2, priority=60,
        pattern=re.compile(r'^[A-Z]{3}\d{7}$'),
        # Only the keyword path exists, so this is effectively a hard gate.
        corroboration=dict(
            keywords=('voter', 'epic', 'election', 'elector'),
        ),
        validator=None,
        strip=' -'),

    'PASSPORT': dict(
        window=2, priority=60,
        pattern=re.compile(r'^[A-PR-WY][1-9]\d{6}$'),
        validator=None,
        strip=' -'),

    # A bare 10-digit run starting 6-9 is a rupee amount as often as a
    # phone number (measured: 10% FP on realistic invoice strings). So a
    # bare form needs corroboration; a prefixed or grouped one does not.
    'PHONE': dict(
        window=3,
        priority=40,
        pattern=re.compile(r'^(?:(?:\+?91)|0)?[6-9]\d{9}$'),
        corroboration=dict(
            # 11+ chars means a real +91 / 91 / 0 prefix is present.
            # Length is the test, NOT leading digits: '9198765432' is a
            # bare 10-digit number that merely starts 9,1 — not a +91 prefix.
            self_evident=re.compile(r'^(?:\+?91|0)[6-9]\d{9}$'),
            keywords=(
                'phone',
                'mobile',
                'mob',
                'contact',
                'tel',
                'cell',
                'whatsapp',
                'landline',
                # OCR-garbled variants of 'mobile', observed directly on
                # real scanned Aadhaar cards: EasyOCR dropped vowels
                # ('Mbl 9494999500 Tt', 'moblla nurber ...') badly enough
                # that none of the correctly-spelled keywords above
                # matched anywhere on the page, so a real phone number
                # got silently dropped here -- never emitted as a
                # candidate at all, not even a low-confidence one. This
                # is a narrow, evidence-based patch (only the specific
                # garbled forms actually observed), not general fuzzy
                # matching -- a real phone number with a keyword garbled
                # some other way is still exposed to the same problem.
                'mbl',
                'moblla',
            ),
        ),
        validator=None,
        strip=' -()'),

    'EMAIL': dict(
        window=1,
        priority=50,
        pattern=re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$'),
        validator=None,
        strip=''),
}


def _union_bbox(tokens):
    """Union box across a token run. None-safe for CSV/field sources."""
    boxes = [t['bbox'] for t in tokens if t.get('bbox')]

    if not boxes:
        return None

    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _corroborated(spec, raw, norm, page_text):
    """
    True if this candidate may be kept.

    Types with no `corroboration` key are unconditionally kept —
    their checksum or format is sufficient.
    """
    rules = spec.get('corroboration')

    if not rules:
        return True

    self_evident = rules.get('self_evident')

    if self_evident and self_evident.match(norm):
        return True

    keywords = rules.get('keywords')

    if keywords and any(
        re.search(r'\b' + re.escape(k) + r'\b', page_text)
        for k in keywords
    ):
        return True

    return False


def _normalise(raw, strip_chars):
    """Remove configured separators and normalize to uppercase."""
    for ch in strip_chars:
        raw = raw.replace(ch, '')

    return raw.upper()


def _scan_page(page, doc_id):
    """Scan one extracted page for all registered PII types."""
    tokens = page.get('tokens', [])
    page_text = (page.get('full_text') or '').lower()
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

                if not _corroborated(spec, raw, norm, page_text):
                    continue

                validator = spec['validator']

                if validator is None:
                    checksum_valid = None
                else:
                    if not validator(norm):
                        continue

                    checksum_valid = True

                confs = [
                    t.get('ocr_conf', 1.0)
                    for t in run
                ]

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
    Resolve competing detections that share OCR tokens.

    Stronger candidates are preferred in this order:
      1. Longer token span
      2. Higher registry priority
      3. Earlier starting position

    Once a candidate is kept, ANY candidate sharing even one token
    with it is rejected.

    Example:
        candidate A -> tokens 1-4
        candidate B -> tokens 4-5

    These overlap on token 4, so only the stronger candidate survives.
    """
    ordered = sorted(
        hits,
        key=lambda h: (
            -(h['_span'][1] - h['_span'][0]),
            -h['_priority'],
            h['_span'][0],
        ),
    )

    kept = []

    for h in ordered:
        s, e = h['_span']

        overlaps = any(
            not (
                e <= k['_span'][0]
                or s >= k['_span'][1]
            )
            for k in kept
        )

        if overlaps:
            continue

        kept.append(h)

    for h in kept:
        h.pop('_span')
        h.pop('_priority')

    return kept


def detect(extraction) -> dict:
    """extraction = P2's output dict. Returns the P1 -> P3 contract."""
    doc_id = extraction['doc_id']
    candidates = []

    for page in extraction.get('pages', []):
        candidates.extend(
            _resolve_overlaps(
                _scan_page(page, doc_id)
            )
        )

    return {
        'doc_id': doc_id,
        'candidates': candidates,
    }