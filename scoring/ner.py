"""
NAME/ADDRESS detection via spaCy en_core_web_sm.

Stub for now -- spaCy isn't installed (Python 3.14 on this machine has
uncertain wheel support), so this returns no detections until that's
sorted out. Kept as a separate module + this signature so score.py
doesn't need to change when real NER lands.
"""


def detect(page: dict, profile: str, policy_matrix: dict) -> list[dict]:
    return []
