from scoring import resolver

matrix = resolver.load_policy_matrix()

# Every profile referenced in the contract must be present
for profile in ("PUBLIC_DISCLOSURE", "THIRD_PARTY_SERVICE", "REGULATED_KYC", "INTERNAL_REVIEW"):
    assert profile in matrix, profile

# Every candidate pii_type from the contract, plus NER's NAME/ADDRESS, must resolve
for profile in matrix:
    for pii_type in ("AADHAAR", "PAN", "DL", "CREDIT_CARD", "PHONE", "EMAIL", "NAME", "ADDRESS"):
        assert pii_type in matrix[profile], (profile, pii_type)

detection = {"pii_type": "AADHAAR", "confidence": 0.9}

action, necessity, reasons = resolver.resolve(detection, "PUBLIC_DISCLOSURE", matrix)
assert action == "REMOVE"
assert necessity == "EXCESS"
assert reasons == ["policy:PUBLIC_DISCLOSURE:AADHAAR:REMOVE"]

action, necessity, reasons = resolver.resolve(detection, "REGULATED_KYC", matrix)
assert action == "MASK"
assert necessity == "REQUIRED"

# Unknown pii_type/profile combos fail safe to FLAG + OPTIONAL rather than KeyError
action, necessity, reasons = resolver.resolve({"pii_type": "UNKNOWN_TYPE"}, "REGULATED_KYC", matrix)
assert action == "FLAG"
assert necessity == "OPTIONAL"

# --- Corrections against the workplan's canonical section 3b matrix ---

# THIRD_PARTY_SERVICE: PHONE/EMAIL kept ("the service legitimately needs
# them"), not masked -- and their necessity is REQUIRED, not OPTIONAL, for
# NAME/EMAIL specifically (PHONE is the one explicitly illustrated as
# OPTIONAL: "a phone number on a job application").
action, necessity, _ = resolver.resolve({"pii_type": "PHONE"}, "THIRD_PARTY_SERVICE", matrix)
assert action == "KEEP"
assert necessity == "OPTIONAL"

action, necessity, _ = resolver.resolve({"pii_type": "EMAIL"}, "THIRD_PARTY_SERVICE", matrix)
assert action == "KEEP"
assert necessity == "REQUIRED"

action, necessity, _ = resolver.resolve({"pii_type": "NAME"}, "THIRD_PARTY_SERVICE", matrix)
assert action == "KEEP"
assert necessity == "REQUIRED"

# THIRD_PARTY_SERVICE: PAN removed outright, not masked.
action, _, _ = resolver.resolve({"pii_type": "PAN"}, "THIRD_PARTY_SERVICE", matrix)
assert action == "REMOVE"

# REGULATED_KYC: PAN is the identifier the process actually needs -- kept, not masked.
action, necessity, _ = resolver.resolve({"pii_type": "PAN"}, "REGULATED_KYC", matrix)
assert action == "KEEP"
assert necessity == "REQUIRED"

# INTERNAL_REVIEW is alert-only -- every type FLAGs, nothing is silently KEPT.
for pii_type in ("AADHAAR", "PAN", "DL", "CREDIT_CARD", "PHONE", "EMAIL", "NAME", "ADDRESS"):
    action, _, _ = resolver.resolve({"pii_type": pii_type}, "INTERNAL_REVIEW", matrix)
    assert action == "FLAG", (pii_type, action)

print("All resolver tests passed")
