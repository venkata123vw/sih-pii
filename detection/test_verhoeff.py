import random
from verhoeff import (
    generate_check_digit, verhoeff_validate,
    validate_aadhaar, format_aadhaar,
)

# --- Standard Verhoeff vectors (published, reproducible) ---
assert generate_check_digit('236') == '3'
assert verhoeff_validate('2363') is True
assert verhoeff_validate('2369') is False        # bad check digit
assert verhoeff_validate('2633') is False        # transposition caught

assert generate_check_digit('12345') == '1'
assert verhoeff_validate('123451') is True

assert generate_check_digit('123456789012') == '0'
assert verhoeff_validate('1234567890120') is True

# --- Aadhaar-format vectors (SYNTHETIC — not issued to anyone) ---
assert validate_aadhaar('234123412346') is True      # stdnum's documented example
assert validate_aadhaar('2341 2341 2346') is True    # separator tolerance
assert validate_aadhaar('2341-2341-2346') is True
assert validate_aadhaar('234123412347') is False     # bad checksum
assert validate_aadhaar('123412341234') is False     # starts with 1
assert validate_aadhaar('034123412346') is False     # starts with 0
assert validate_aadhaar('23412341234') is False      # 11 digits
assert validate_aadhaar('2341234123466') is False    # 13 digits

# UIDAI's own documented test/sandbox number
assert validate_aadhaar('999999990019') is True

assert format_aadhaar('234123412346') == '2341 2341 2346'

# --- Round trip: 1000 random prefixes ---
for _ in range(1000):
    prefix = str(random.randint(2, 9)) + ''.join(
        random.choice('0123456789') for _ in range(10))
    assert validate_aadhaar(prefix + generate_check_digit(prefix))

print('All Verhoeff / Aadhaar tests passed')