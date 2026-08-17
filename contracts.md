## Detection output (`detection.detect.detect()`) — owned by detection/

Consumed by `scoring.score.score()` as `candidates_payload`.

```python
def detect(extraction: dict) -> dict
```

Return shape:

```python
{
  "doc_id": "abc123",
  "candidates": [
    {
      "pii_type": "AADHAAR",        # AADHAAR | CREDIT_CARD | PAN | VOTER_ID
                                    # | PASSPORT | PHONE | EMAIL
      "value": "2341 2341 2346",    # as it appeared, separators preserved
      "page_num": 0,                # zero-indexed
      "bbox": [x0, y0, x1, y1],     # union across joined tokens; None for
                                    # sources without coordinates (CSV, text)
      "checksum_valid": True,       # True = passed; None = type has no
                                    # checksum. Never False — failures are
                                    # dropped, not emitted.
      "match_source": "regex",
      "ocr_conf": 0.95,             # min across joined tokens
    }
  ]
}
```

Rules:
- A candidate is only emitted if pattern AND checksum both pass. A checksum
  failure is a non-detection, so `checksum_valid` is never `False`.
- `checksum_valid: None` means the type has no published checksum (PAN's
  check digit algorithm is unpublished; phone/email/voter have none). P3
  should weigh "no checksum exists" differently from a pass.
- Overlapping spans are resolved before emission — longest span wins, then
  priority. A 16-digit card will not also appear as a 12-digit AADHAAR.
- PAN validation is format-only and deliberately permissive. Entity code
  and serial checks are available via `detection.pan.pan_signals()` as
  confidence signals, not gates.