from detection.pan import validate_pan, pan_signals, pan_entity_type, mask_pan

# ITD published example
assert validate_pan('ALWPG5809L') is True
assert pan_entity_type('ALWPG5809L') == 'Individual'

# Valid, well-known entity codes
for p in ['ABCCD1234E', 'ABCFD1234E', 'ABCTD1234E', 'ABCHD1234E']:
    assert validate_pan(p) is True
    assert pan_signals(p)['known_entity_code'] is True

# CHANGED: contested/unknown entity codes now DETECTED, flagged low-signal
for p in ['ABCED1234E', 'ABCKD1234E', 'ABCXD1234E']:
    assert validate_pan(p) is True, p
    assert pan_signals(p)['known_entity_code'] is False, p

# CHANGED: 0000 serial detected, flagged
assert validate_pan('ABCPD0000E') is True
assert pan_signals('ABCPD0000E')['serial_nonzero'] is False
assert pan_signals('ALWPG5809L')['serial_nonzero'] is True

# Format failures stay failures
for p in ['ABC1D1234E', 'ABCPD12345', 'ABCPD123E', 'ABCPD1234EX', '']:
    assert validate_pan(p) is False, p
    assert pan_signals(p)['format_ok'] is False, p

# Case tolerance
assert validate_pan('alwpg5809l') is True

# Masking
assert mask_pan('ALWPG5809L') == 'XXXXXX809L'
assert mask_pan('ALWPG5809L', reveal_last=0) == 'XXXXXXXXXX'
for bad in (5, 10, -1):
    try:
        mask_pan('ALWPG5809L', reveal_last=bad); raise AssertionError('no raise')
    except ValueError:
        pass
print('All PAN tests passed')
