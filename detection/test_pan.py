import pytest

from detection.pan import (
    validate_pan,
    pan_signals,
    pan_entity_type,
    mask_pan,
)


def test_itd_published_example():
    assert validate_pan('ALWPG5809L') is True
    assert pan_entity_type('ALWPG5809L') == 'Individual'


def test_known_entity_codes():
    for p in ('ABCCD1234E', 'ABCFD1234E', 'ABCTD1234E', 'ABCHD1234E'):
        assert validate_pan(p) is True
        assert pan_signals(p)['known_entity_code'] is True


def test_unknown_entity_codes_are_detected_not_rejected():
    """
    Deliberate recall bias. E and K are contested in public sources, and
    a detection engine that rejects them ships unredacted PII. They are
    detected and flagged low-signal for the scoring layer instead.
    """
    for p in ('ABCED1234E', 'ABCKD1234E', 'ABCXD1234E'):
        assert validate_pan(p) is True
        assert pan_signals(p)['known_entity_code'] is False


def test_zero_serial_is_a_signal_not_a_gate():
    assert validate_pan('ABCPD0000E') is True
    assert pan_signals('ABCPD0000E')['serial_nonzero'] is False
    assert pan_signals('ALWPG5809L')['serial_nonzero'] is True


def test_format_failures_still_fail():
    for p in ('ABC1D1234E', 'ABCPD12345', 'ABCPD123E', 'ABCPD1234EX', ''):
        assert validate_pan(p) is False
        assert pan_signals(p)['format_ok'] is False


def test_case_tolerance():
    assert validate_pan('alwpg5809l') is True


def test_mask_pan():
    assert mask_pan('ALWPG5809L') == 'XXXXXX809L'
    assert mask_pan('ALWPG5809L', reveal_last=0) == 'XXXXXXXXXX'


def test_mask_pan_cannot_leak_full_number():
    for bad in (5, 10, -1):
        with pytest.raises(ValueError):
            mask_pan('ALWPG5809L', reveal_last=bad)