# Contracts

## Scoring output (`scoring.score.score()`) — owned by scoring/

This is what `score()` returns to whoever calls it (currently `pipeline.py`,
eventually P4/P5). Input contracts (candidates from detection/, page_context
from ingestion/, profile string from the runtime) are each owned by their
respective track and aren't documented here yet — confirm with whoever owns
that piece before relying on a shape for those.

```python
def score(
    candidates_payload: dict,          # {"doc_id": str, "candidates": [...]}
    profile: str = "THIRD_PARTY_SERVICE",
    page_ctx: dict | None = None,      # optional: {"pages": [...]}; omitting it
                                        # degrades confidence to checksum-only signals
    policy_matrix: dict | None = None, # optional: defaults to policy/profiles.yaml
) -> dict
```

Return shape:

```python
{
  "doc_id": "abc123",
  "context_profile": "THIRD_PARTY_SERVICE",
  "detections": [
    {
      # carried through unchanged from the input candidate:
      "pii_type": "AADHAAR", "value": "1234 5678 9012", "page_num": 0,
      "bbox": [x0, y0, x1, y1], "checksum_valid": True, "match_source": "regex",
      # added by scoring:
      "confidence": 0.75,                 # float in [0, 1], scoring/confidence.py
      "policy_action": "REMOVE",          # REMOVE | MASK | KEEP | FLAG, scoring/resolver.py
      "necessity": "EXCESS",              # REQUIRED | OPTIONAL | EXCESS
      "reasons": ["checksum_pass", "keyword_nearby:aadhaar", "policy:THIRD_PARTY_SERVICE:AADHAAR:REMOVE"],
    }
  ],
  "excess_pii_alert": [{"pii_type": "AADHAAR", "count": 1}],
}
```

Rules:
- `confidence` and `policy_action` are computed by separate functions
  (`confidence.score()` / `resolver.resolve()`) and never merged.
- Coordinates are top-left origin, pages are zero-indexed — unchanged from
  what's passed in.
- `policy_action`/`necessity` come from `policy/profiles.yaml`, a first-draft
  policy matrix (not reviewed by a policy owner yet — see that file).
- NER-derived detections (`ner.py`, currently a stub returning `[]`) will
  land in the same `detections` list with `pii_type: "NAME"` or `"ADDRESS"`,
  `checksum_valid: None`, `match_source: "ner"`, same added fields.
