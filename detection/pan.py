"""
Indian PAN (Permanent Account Number) structural validation.

Format: AAAAA9999A  — 5 letters, 4 digits, 1 letter.
Issued under s.139A of the Income-tax Act, 1961.

IMPORTANT: PAN has NO usable checksum. The 10th character is a check
digit by design, but the algorithm is not published by ITD, NSDL, or
UTIITSL. Validation is format + entity code only. Do not claim
checksum validation for PAN.
"""

import re

# Official Income Tax Department entity codes (position 4). Exactly 10.
# Note: 'E' (LLP) and 'K' (Trust) are NOT valid — LLPs use F, Trusts use T.
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
    p = str(pan).strip().upper()
    if not _PAN_RE.match(p):
        return False
    if p[3] not in ENTITY_TYPES:
        return False
    if p[5:9] == '0000':            # serial 0000 is never issued
        return False
    return True


def pan_entity_type(pan: str) -> str | None:
    p = str(pan).strip().upper()
    return ENTITY_TYPES.get(p[3]) if validate_pan(p) else None


def mask_pan(pan: str, reveal_last: int = 4) -> str:
    p = str(pan).strip().upper()
    return 'X' * (10 - reveal_last) + p[-reveal_last:]