import re

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
_inv = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)
_AADHAAR_RE = re.compile(r'^[2-9][0-9]{11}$')


def clean(number: str) -> str:
    return ''.join(ch for ch in str(number) if ch.isdigit())


def checksum(digits: str) -> int:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _d[c][_p[i % 8][int(ch)]]
    return c


def verhoeff_validate(number: str) -> bool:
    digits = clean(number)
    return bool(digits) and checksum(digits) == 0


def generate_check_digit(prefix: str) -> str:
    return str(_inv[checksum(clean(prefix) + '0')])


def validate_aadhaar(number: str, reject_palindromes: bool = False) -> bool:
    n = clean(number)
    if not _AADHAAR_RE.match(n):
        return False
    if reject_palindromes and n == n[::-1]:
        return False
    return checksum(n) == 0


def format_aadhaar(number: str) -> str:
    n = clean(number)
    return f'{n[0:4]} {n[4:8]} {n[8:12]}'


def mask_aadhaar(number: str, reveal_last: int = 4) -> str:
    """
    Mask an Aadhaar for display: XXXX XXXX 2346.
    reveal_last is capped at 4 (UIDAI/RBI convention). The cap is a
    safety gate, not a style choice: this is a redaction tool, so a
    mask call must never be able to return the full number.
    """
    n = clean(number)
    if len(n) != 12:
        raise ValueError('Aadhaar number must contain exactly 12 digits')
    if not 0 <= reveal_last <= 4:
        raise ValueError('reveal_last must be between 0 and 4')
    if reveal_last == 0:
        masked = 'X' * 12
    else:
        masked = 'X' * (12 - reveal_last) + n[-reveal_last:]
    return f'{masked[0:4]} {masked[4:8]} {masked[8:12]}'