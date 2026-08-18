import pytest

from detection.luhn import (
    luhn_validate,
    luhn_generate_check_digit,
    identify_network,
    is_card_number,
    mask_card,
)

def test_luhn_length_bounds():
    """ISO/IEC 7812 valid range is 12-19 digits."""
    assert luhn_validate('79927398713') is False   # 11 digits, below minimum
    assert luhn_generate_check_digit('7992739871') == '3'


def test_published_test_cards_pass_luhn():
    """Sandbox numbers from Stripe / network test suites. Never real cards."""
    assert luhn_validate('4242424242424242') is True
    assert luhn_validate('4012888888881881') is True
    assert luhn_validate('5555555555554444') is True
    assert luhn_validate('2223003122003222') is True   # Mastercard 2-series
    assert luhn_validate('378282246310005') is True    # Amex, 15 digits
    assert luhn_validate('6011111111111117') is True
    assert luhn_validate('30569309025904') is True     # Diners, 14 digits
    assert luhn_validate('3530111333300000') is True   # JCB


def test_luhn_rejects_bad_numbers():
    assert luhn_validate('4242424242424243') is False  # bad check digit
    assert luhn_validate('1234567890123456') is False  # fails Luhn


def test_network_identification():
    assert identify_network('4242424242424242') == 'VISA'
    assert identify_network('5555555555554444') == 'MASTERCARD'
    assert identify_network('2223003122003222') == 'MASTERCARD'
    assert identify_network('378282246310005') == 'AMEX'
    assert identify_network('6011111111111117') == 'DISCOVER'
    assert identify_network('3530111333300000') == 'JCB'
    assert identify_network('30569309025904') == 'DINERS'


def test_is_card_number_requires_prefix_and_luhn():
    """
    Luhn alone passes ~10% of random 16-digit strings. Requiring a valid
    network prefix AND length AND Luhn drops that to ~2.4%. This is the
    check the detector should call — never bare luhn_validate.
    """
    assert is_card_number('4242424242424242') is True
    assert is_card_number('1234567890123456') is False


def test_mask_card_pci_dss():
    """PCI-DSS: first 6 and last 4 are the maximum displayable."""
    assert mask_card('4242424242424242') == '424242******4242'

def test_mask_card_rejects_invalid_luhn():
    """mask_card() must never mask an invalid card as if it were valid."""
    with pytest.raises(ValueError):
        mask_card('4242424242424243')


def test_mask_card_rejects_unknown_network():
    """A Luhn-valid number without a recognized network must be rejected."""
    with pytest.raises(ValueError):
        mask_card('1234567890123456')


def test_mask_card_rejects_wrong_length():
    """mask_card() must enforce the ISO/IEC 7812 length bounds."""
    with pytest.raises(ValueError):
        mask_card('424242424242')


def test_mask_card_rejects_unsupported_characters():
    """Arbitrary characters must not be silently stripped before masking."""
    with pytest.raises(ValueError):
        mask_card('4242424242424242abc')


def test_mask_card_accepts_common_formatting():
    """Normal card formatting should still be accepted."""
    assert mask_card('4242-4242-4242-4242') == '424242******4242'
    assert mask_card('4242 4242 4242 4242') == '424242******4242'


def test_mask_card_never_returns_full_number():
    """The full card number must never appear in the masked result."""
    number = '4242424242424242'
    masked = mask_card(number)

    assert masked != number
    assert number not in masked
    assert masked == '424242******4242'