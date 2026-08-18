"""
Top-level entry point for P3. Wires confidence scoring + policy
resolution + NER together into the detections contract P4/P5 consume.

confidence and policy_action are computed by separate functions
(confidence.score / resolver.resolve) and never merged into one --
that separation is what keeps redaction decisions auditable.
"""

from scoring import confidence, ner, resolver


def aggregate_excess(detections: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for d in detections:
        if d.get("necessity") == "EXCESS":
            counts[d["pii_type"]] = counts.get(d["pii_type"], 0) + 1
    return [{"pii_type": pii_type, "count": count} for pii_type, count in counts.items()]


def score(
    candidates_payload: dict,
    profile: str = "THIRD_PARTY_SERVICE",
    page_ctx: dict | None = None,
    policy_matrix: dict | None = None,
) -> dict:
    # page_ctx is optional and keyword-only in practice so the existing
    # pipeline.py call site (candidates, profile) keeps working untouched.
    # Without it, confidence falls back to checksum/match_source signals
    # only -- no keyword proximity, negative-signal, or OCR damping.
    if page_ctx is None:
        page_ctx = {"pages": []}
    if policy_matrix is None:
        policy_matrix = resolver.load_policy_matrix()

    detections = []

    for candidate in candidates_payload["candidates"]:
        conf = confidence.score(candidate, page_ctx)
        reasons = confidence.signal_reasons(candidate, page_ctx)
        action, necessity, resolver_reasons = resolver.resolve(
            {**candidate, "confidence": conf}, profile, policy_matrix
        )
        detections.append({
            **candidate,
            "confidence": conf,
            "policy_action": action,
            "necessity": necessity,
            "reasons": reasons + resolver_reasons,
        })

    for page in page_ctx.get("pages", []):
        detections.extend(ner.detect(page, profile, policy_matrix))

    return {
        "doc_id": candidates_payload["doc_id"],
        "context_profile": profile,
        "detections": detections,
        "excess_pii_alert": aggregate_excess(detections),
    }
