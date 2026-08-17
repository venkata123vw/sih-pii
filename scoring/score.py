def score(candidates: dict, profile: str = "THIRD_PARTY_SERVICE") -> dict:
    return {
        "doc_id": candidates["doc_id"],
        "context_profile": profile,
        "detections": candidates["candidates"],
        "excess_pii_alert": []
    }