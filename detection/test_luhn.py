from luhn import (luhn_validate, luhn_generate_check_digit,
                  identify_network, is_card_number, mask_card)

# Classic Luhn vector
assert luhn_validate('79927398713') is False    # 11 digits, below ISO minimum
assert luhn_generate_check_digit('7992739871') == '3'

# Published test cards — all Luhn-valid
assert luhn_validate('4242424242424242') is True
assert luhn_validate('4012888888881881') is True
assert luhn_validate('5555555555554444') is True
assert luhn_validate('2223003122003222') is True   # Mastercard 2-series
assert luhn_validate('378282246310005') is True    # Amex, 15 digits
assert luhn_validate('6011111111111117') is True
assert luhn_validate('30569309025904') is True     # Diners, 14 digits
assert luhn_validate('3530111333300000') is True   # JCB

# Failures
assert luhn_validate('4242424242424243') is False  # bad check digit
assert luhn_validate('1234567890123456') is False  # fails Luhn

# Network identification
assert identify_network('4242424242424242') == 'VISA'
assert identify_network('5555555555554444') == 'MASTERCARD'
assert identify_network('2223003122003222') == 'MASTERCARD'
assert identify_network('378282246310005') == 'AMEX'
assert identify_network('6011111111111117') == 'DISCOVER'
assert identify_network('3530111333300000') == 'JCB'
assert identify_network('30569309025904') == 'DINERS'

# Combined check
assert is_card_number('4242424242424242') is True
assert mask_card('4242424242424242') == '424242******4242'

print('All Luhn tests passed')