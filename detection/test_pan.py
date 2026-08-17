from pan import validate_pan, pan_entity_type, mask_pan

# ITD's own published example
assert validate_pan('ALWPG5809L') is True
assert pan_entity_type('ALWPG5809L') == 'Individual'

# Valid entity codes
assert validate_pan('ABCCD1234E') is True      # C = Company
assert validate_pan('ABCFD1234E') is True      # F = Firm/LLP
assert validate_pan('ABCTD1234E') is True      # T = Trust
assert validate_pan('ABCHD1234E') is True      # H = HUF

# Invalid entity codes — these are the common wrong ones
assert validate_pan('ABCED1234E') is False     # E is NOT valid (LLP uses F)
assert validate_pan('ABCKD1234E') is False     # K is NOT valid (Trust uses T)
assert validate_pan('ABCXD1234E') is False     # X not an entity code

# Format failures
assert validate_pan('ABC1D1234E') is False     # digit in letter zone
assert validate_pan('ABCPD12345') is False     # digit in final position
assert validate_pan('ABCPD123E') is False      # too short
assert validate_pan('ABCPD00001') is False     # wait - check this one

# Serial check
assert validate_pan('ABCPD0000E') is False     # serial 0000 invalid

# Case tolerance
assert validate_pan('alwpg5809l') is True

assert mask_pan('ALWPG5809L') == 'XXXXXX809L'

print('All PAN tests passed')