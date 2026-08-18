"""
Luhn checksum (ISO/IEC 7812-1 Annex B) + card network identification.

Luhn alone is weak: ~1 in 10 random digit strings pass, because exactly
one of the ten possible last digits validates any prefix. Always require
prefix + length + Luhn together before flagging.

Test card numbers below are published sandbox numbers (Stripe/network
test suites). Never put a real card number in this repo.
"""


def clean(number: str) -> str:
    return ''.join(ch for ch in str(number) if ch.isdigit())


def luhn_checksum(number: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(clean(number))):
        n = int(ch)
        if i % 2 == 1:                 # every 2nd digit from the right
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10


def luhn_validate(number: str) -> bool:
    """True if the full number (including check digit) passes Luhn."""
    s = clean(number)
    if not 12 <= len(s) <= 19:         # ISO/IEC 7812 valid range
        return False
    return luhn_checksum(s) == 0


def luhn_generate_check_digit(partial: str) -> str:
    """Given a payload WITHOUT check digit, return the digit to append."""
    total = 0
    for i, ch in enumerate(reversed(clean(partial))):
        n = int(ch)
        if i % 2 == 0:                 # parity flips vs validation
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - (total % 10)) % 10)


def identify_network(number: str) -> str | None:
    """
    Network from IIN prefix + length. None if no match.

    Ordered most-specific prefix first. RuPay and Discover share MII 6
    (they co-brand), so some ranges genuinely overlap — 6011 is Discover,
    6521-6543 is RuPay, and bare 60 is RuPay. Full resolution needs a
    licensed BIN table. For PII detection this doesn't matter much:
    use is_card_number() rather than trusting the network label.
    """
    s = clean(number)
    n = len(s)

    def pref(k):
        return int(s[:k]) if n >= k else -1

    d1, d2, d3, d4, d6 = pref(1), pref(2), pref(3), pref(4), pref(6)

    # Unambiguous networks first
    if d1 == 4 and n in (13, 16, 19):
        return 'VISA'
    if n == 15 and d2 in (34, 37):
        return 'AMEX'
    if n == 14 and (300 <= d3 <= 305 or d2 in (36, 38, 39)):
        return 'DINERS'
    if n == 16 and (51 <= d2 <= 55 or 2221 <= d4 <= 2720):
        return 'MASTERCARD'
    if n in (16, 19) and 3528 <= d4 <= 3589:
        return 'JCB'
    if 16 <= n <= 19 and d2 == 62:
        return 'UNIONPAY'

    # MII 6 — contested space. Most specific prefixes first.
    if n in (16, 19) and (d4 == 6011 or 622126 <= d6 <= 622925
                          or 644 <= d3 <= 649):
        return 'DISCOVER'
    if n == 16 and (652100 <= d6 <= 654399
                    or 606000 <= d6 <= 608999
                    or 508500 <= d6 <= 508999
                    or d2 == 60):
        return 'RUPAY'
    if n in (16, 19) and d2 == 65:          # remaining 65 space
        return 'DISCOVER'

    return None

def is_card_number(number: str) -> bool:
    """Strongest single check: valid network prefix AND Luhn."""
    return identify_network(number) is not None and luhn_validate(number)


def mask_card(number: str) -> str:
    """
    Safely mask a validated payment-card number.

    PCI-DSS display rule used here:
    - first 6 digits remain visible
    - last 4 digits remain visible
    - everything in between is masked

    Safety requirements:
    - accepts digits with common visual separators only
    - requires 12-19 cleaned digits
    - requires a recognized card network
    - requires a valid Luhn checksum

    Raises:
        ValueError: if the input is not a valid card number.
    """
    raw = str(number)

    # Do not silently discard arbitrary characters. Spaces, hyphens,
    # and parentheses are allowed as normal card-number formatting.
    if any(ch not in '0123456789 -()' for ch in raw):
        raise ValueError("card number contains unsupported characters")

    s = clean(raw)

    if not 12 <= len(s) <= 19:
        raise ValueError("card number must contain 12-19 digits")

    if not is_card_number(s):
        raise ValueError("card number failed network or Luhn validation")

    return s[:6] + '*' * (len(s) - 10) + s[-4:]