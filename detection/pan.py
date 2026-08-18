"""
Indian PAN structural validation.
Format: AAAAA9999A — 5 letters, 4 digits, 1 letter. s.139A, Income-tax Act 1961.

PAN has NO usable checksum. The 10th character is a check digit by design
but the algorithm is not published by ITD, NSDL, or UTIITSL.

DESIGN NOTE: validate_pan() is FORMAT ONLY, deliberately permissive.
The entity code at position 4 and the non-zero serial are returned as
SIGNALS via pan_signals(), not enforced as gates. Reason: this is a
detection engine. A false negative is unredacted PII in a shipped
document. A false positive is a checkbox the user unticks in review.
Those costs are not symmetric, so we bias toward recall and let the
confidence layer (P3) weigh the signals.
"""
import re

# Widely-documented ITD entity codes (position 4). Treated as a
# confidence signal, not a whitelist — sources disagree on whether
# 'E' (LLP) and 'K' are issued.
ENTITY_TYPES = {
    'A': 'Association of Persons (AOP)',
    'B': 'Body of Individuals (BOI)',
    'C': 'Company',
    'F': 'Firm / LLP',
    'G': 'Government',
    'H': 'Hindu Undivided Family (HUF)',
    'J': 'Artificial Juridical Person',
    'L': 'Local Authority',
    'P': 'Individual',
    'T': 'Trust',
}

_PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')


def validate_pan(pan: str) -> bool:
    """Format only. Permissive by design — see module docstring."""
    return bool(_PAN_RE.match(str(pan).strip().upper()))


def pan_signals(pan: str) -> dict:
    """Signals for P3's confidence function. All False if format fails."""
    p = str(pan).strip().upper()
    if not validate_pan(p):
        return {'format_ok': False, 'known_entity_code': False,
                'serial_nonzero': False, 'entity_type': None}
    return {
        'format_ok': True,
        'known_entity_code': p[3] in ENTITY_TYPES,
        'serial_nonzero': p[5:9] != '0000',
        'entity_type': ENTITY_TYPES.get(p[3]),
    }


def pan_entity_type(pan: str):
    return pan_signals(pan)['entity_type']


def mask_pan(pan: str, reveal_last: int = 4) -> str:
    p = str(pan).strip().upper()
    if not _PAN_RE.match(p):
        raise ValueError('PAN must match AAAAA9999A')
    if not 0 <= reveal_last <= 4:
        raise ValueError('reveal_last must be between 0 and 4')
    return 'X' * (10 - reveal_last) + (p[-reveal_last:] if reveal_last else '')