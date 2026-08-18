import random

import pytest

from detection.verhoeff import (
    generate_check_digit,
    verhoeff_validate,
    validate_aadhaar,
    format_aadhaar,
    mask_aadhaar,
)


def test_verhoeff_published_vectors():
    """Standard Verhoeff vectors — published and reproducible."""
    assert generate_check_digit('236') == '3'
    assert verhoeff_validate('2363') is True
    assert verhoeff_validate('2369') is False        # bad check digit
    assert verhoeff_validate('2633') is False        # transposition caught
    assert generate_check_digit('12345') == '1'
    assert verhoeff_validate('123451') is True
    assert generate_check_digit('123456789012') == '0'
    assert verhoeff_validate('1234567890120') is True


def test_aadhaar_structural_validation():
    """SYNTHETIC Aadhaar-format vectors — not issued to anyone."""
    assert validate_aadhaar('234123412346') is True      # stdnum's example
    assert validate_aadhaar('2341 2341 2346') is True    # separator tolerance
    assert validate_aadhaar('2341-2341-2346') is True
    assert validate_aadhaar('234123412347') is False     # bad checksum
    assert validate_aadhaar('123412341234') is False     # starts with 1
    assert validate_aadhaar('034123412346') is False     # starts with 0
    assert validate_aadhaar('23412341234') is False      # 11 digits
    assert validate_aadhaar('2341234123466') is False    # 13 digits
    assert validate_aadhaar('999999990019') is True      # UIDAI sandbox number


def test_format_aadhaar():
    assert format_aadhaar('234123412346') == '2341 2341 2346'


def test_mask_aadhaar_depths():
    """P4's dropdown drives reveal_last, so every offered depth is tested."""
    assert mask_aadhaar('234123412346') == 'XXXX XXXX 2346'
    assert mask_aadhaar('234123412346', reveal_last=4) == 'XXXX XXXX 2346'
    assert mask_aadhaar('234123412346', reveal_last=2) == 'XXXX XXXX XX46'
    assert mask_aadhaar('234123412346', reveal_last=1) == 'XXXX XXXX XXX6'
    assert mask_aadhaar('234123412346', reveal_last=0) == 'XXXX XXXX XXXX'


def test_mask_aadhaar_cannot_leak_full_number():
    """The cap is a safety gate: no argument may return all 12 digits."""
    for bad in (5, 8, 12, 13, -1):
        with pytest.raises(ValueError):
            mask_aadhaar('234123412346', reveal_last=bad)


def test_mask_aadhaar_rejects_bad_input():
    """P4 may re-run the pipeline over already-masked text — fail loud."""
    for bad in ('2341 2341 234', '2341234123466', 'XXXX XXXX 2346', ''):
        with pytest.raises(ValueError):
            mask_aadhaar(bad)


def test_aadhaar_round_trip():
    """1000 random prefixes: generated check digit must always validate."""
    random.seed(1668)
    for _ in range(1000):
        prefix = str(random.randint(2, 9)) + ''.join(
            random.choice('0123456789') for _ in range(10)
        )
        assert validate_aadhaar(prefix + generate_check_digit(prefix))