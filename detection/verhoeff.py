"""
Verhoeff checksum + Aadhaar structural validation.

UIDAI uses Verhoeff for the 12th digit of every Aadhaar number
(confirmed by NPCI Circular No. 9, 2013-14, and NPCI's AEPS spec).

Tables verified identical across python-stdnum, Apache Commons
Validator, Wikibooks, and Rosetta Code.

SYNTHETIC TEST DATA ONLY. Never put a real Aadhaar number in this
repo — Aadhaar Act 2016 s.29(4) prohibits publishing them.
"""

import re

# d: multiplication table (Cayley table of dihedral group D5).
# NOT commutative — d[j][k] != d[k][j]. Argument order matters.
_d = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

# p: permutation table. 8 rows — index with (position % 8).
_p = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

# inv: multiplicative inverse table
_inv = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

# Aadhaar: 12 digits, first digit 2-9 (0 and 1 are reserved)
_AADHAAR_RE = re.compile(r'^[2-9][0-9]{11}$')


def clean(number: str) -> str:
    """Strip everything that isn't a digit."""
    return ''.join(ch for ch in str(number) if ch.isdigit())


def checksum(digits: str) -> int:
    """Core Verhoeff loop. Returns 0 for a valid full number."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _d[c][_p[i % 8][int(ch)]]
    return c


def verhoeff_validate(number: str) -> bool:
    """Raw Verhoeff check on any length number, including check digit."""
    digits = clean(number)
    return bool(digits) and checksum(digits) == 0


def generate_check_digit(prefix: str) -> str:
    """
    prefix = the number WITHOUT its check digit.
    Appends a placeholder 0, computes checksum, inverts it.
    """
    return str(_inv[checksum(clean(prefix) + '0')])


def validate_aadhaar(number: str, reject_palindromes: bool = False) -> bool:
    """
    Full Aadhaar structural validation:
      1. strip separators
      2. 12 digits, first digit 2-9
      3. Verhoeff checksum

    reject_palindromes is a python-stdnum heuristic, NOT a documented
    UIDAI rule. Off by default — a real Aadhaar could in principle be
    a palindrome, and rejecting one would be a false negative.

    NOTE: passing this proves STRUCTURAL validity only. It does not
    mean the number was ever issued. Never claim otherwise.
    """
    n = clean(number)
    if not _AADHAAR_RE.match(n):
        return False
    if reject_palindromes and n == n[::-1]:
        return False
    return checksum(n) == 0


def format_aadhaar(number: str) -> str:
    """Display format: XXXX XXXX XXXX"""
    n = clean(number)
    return f'{n[0:4]} {n[4:8]} {n[8:12]}'


def mask_aadhaar(number: str, reveal_last: int = 4) -> str:
    """UIDAI/RBI convention: mask the first 8 digits."""
    n = clean(number)
    keep = n[-reveal_last:] if reveal_last else ''
    return format_aadhaar('X' * (12 - reveal_last) + keep).replace('X', 'X')