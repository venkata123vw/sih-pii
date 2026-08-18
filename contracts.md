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
- NER-derived detections (`ner.py`, real spaCy `en_core_web_sm` NER, not a
  stub) land in the same `detections` list with `pii_type: "NAME"` or
  `"ADDRESS"`, `checksum_valid: None`, `match_source: "ner"`, same added
  fields. Confidence is capped at 0.5 (see `confidence.py`) since NER has
  no structural proof the way checksum-backed regex matches do.

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
                              # | PASSPORT | PHONE | EMAIL | DL
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
- Overlapping spans are resolved before emission. Any candidate that
  overlaps a stronger candidate is rejected. Strength is determined by
  span length, then priority, then earlier start position. A 16-digit
  card will not also appear as a 12-digit AADHAAR.
- PAN validation is format-only and deliberately permissive. Entity code
  and serial checks are available via `detection.pan.pan_signals()` as
  confidence signals, not gates.

## Extraction output (`ingestion.extract.extract()`) — owned by ingestion/

Feeds `detection.detect.detect()` as `extraction`, and is passed straight
through as `page_ctx` to `scoring.score.score()`.

```python
def extract(filepath: str, reader=None) -> dict
```

Return shape:

```python
{
  "doc_id": "abc123",                            # sha256(file bytes)[:12]
  "source_type": "text_pdf" | "scanned_image" | "plain_text",
  "pages": [
    {
      "page_num": 0,                             # zero-indexed
      "width": 595.0, "height": 842.0,           # PDF points, not pixels
      "tokens": [
        {"text": "1234", "bbox": [x0, y0, x1, y1], "ocr_conf": 0.94}
      ],
      "full_text": "....",
    }
  ],
}
```

Rules:
- `doc_id` is a stable hash of the file's raw bytes, so re-running against
  the same file gives the same `doc_id` every time.
- Coordinates are PDF points, top-left origin, identically on both the
  native-text and OCR extraction paths. Do not convert to pixels — this
  is load-bearing for `redaction.redact`'s `pymupdf.Rect(*bbox) & page.rect`
  intersection, since `page.rect` is always real PDF points.
- `source_type` is `"scanned_image"` only if **no page anywhere** in the
  document had a native text layer; a mixed document (some scanned pages,
  some native) still reports `"text_pdf"` if at least one page had native
  text. `"plain_text"` is for `.csv`/`.json` inputs, which have no
  pymupdf document handler and are read directly instead — one page,
  `width`/`height` are `0`.
- For `"plain_text"` sources (and pasted-text input built outside this
  function by `pipeline.py`), tokens carry no coordinates at all —
  `bbox`/`ocr_conf` keys are **omitted**, not set to `None`. Every
  downstream consumer (`detection.detect`, `scoring.context`,
  `scoring.ner`, `redaction.redact`) is `None`-safe/`.get()`-safe for
  this, by design — coordinate-less is a legal state throughout this
  contract, not an error case.

### Metadata output (`ingestion.metadata.scan_metadata()`) — proposed, not yet ratified

Scans a file for identity-revealing metadata that never appears in the
visible page content (PDF doc-info/embedded files/hidden layers, DOCX
core/extended properties, image EXIF including GPS). Currently attached
additively as `analysis["metadata"]` by `pipeline.analyze()` for direct
display only — **not** wired into `detection.detect()`, `scoring.score()`,
or `policy/profiles.yaml`. Documented here as a proposal so P1/P3 can
weigh in before (if ever) treating it as part of the scored-detections
contract above.

```python
def scan_metadata(filepath: str) -> dict
```

Return shape:

```python
{
  "source_type": "pdf" | "docx" | "image" | "unsupported",
  "findings": [
    {"field": "author", "value": "...", "category": "identity"},
  ],
}
```

`category` is one of `identity | organization | device | location |
timestamp | tooling | content | hidden_layer | embedded_file | form`.
Only non-empty findings are emitted — an absent field means "not present
in this document," not "checked and blank."

## Redaction output (`redaction.redact.apply_redactions()`) — owned by redaction/

Consumes `scoring.score.score()`'s return value verbatim as `decisions`.

```python
def apply_redactions(
    filepath: str,
    decisions: dict,
    out_path: str,
    *,
    flag_action: str = "REMOVE",   # REMOVE | MASK | SKIP — how FLAG is treated
    mask_visible_tail: int = 4,
    verify: bool = True,
) -> dict
```

Return shape (the manifest — P5's `pipeline.apply()` consumes this):

```python
{
  "doc_id": "abc123",
  "context_profile": "THIRD_PARTY_SERVICE",
  "out_path": "...",
  "redacted": [
    {"pii_type": "AADHAAR", "page_num": 0, "policy_action": "REMOVE",
     "confidence": 0.75, "necessity": "EXCESS", "reason": "applied:REMOVE"}
  ],
  "skipped": [
    # same shape as "redacted", reason is one of:
    #   policy:KEEP | policy:FLAG:deferred_to_review
    #   | no_bbox:coordinate_less_source | bbox_outside_page_bounds
  ],
  "counts": {"REMOVE": 0, "MASK": 0, "KEEP": 0, "FLAG": 0, "no_bbox": 0},
  "verified": True,
}
```

Rules:
- `policy_action` gates everything and is not advisory: `KEEP` must come
  out of this function untouched; `REMOVE`/`MASK` are mutated; `FLAG` is
  resolved to whatever `flag_action` says (defaults to `REMOVE` — fails
  closed, so a flagged item requires actively opting into `SKIP`/`MASK`).
- `bbox: None` (coordinate-less source — CSV, pasted text) cannot be
  redacted geometrically. Counted under `counts["no_bbox"]` and reported
  in `skipped`, never crashed on.
- Coordinates are top-left origin, zero-indexed pages — unchanged from
  ingestion's contract, and pass straight through to `pymupdf.Rect`.
- The whole `decisions["detections"]` payload is validated before any
  mutation happens, so one bad detection can't leave a half-redacted
  document on disk.
- `verify=True` (the default) re-extracts the output's text layer and
  raises `RedactionError` if any redacted value is still present — fails
  loudly rather than silently reporting success on a redaction that
  didn't actually take.
