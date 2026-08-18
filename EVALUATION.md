# P3 Evaluation Results

Owned by `scoring/`. Reproduce with:

```
python -m scripts.evaluate
```

## Result

**precision = 1.00, recall = 0.50, F1 = 0.67** (tp=1, fp=0, fn=1)

Measured by running the real pipeline (`pipeline.analyze()` — `ingestion.extract`
→ `detection.detect` → `scoring.score`, no hand-built fixtures) against the
actual files in `data/` and comparing against `ground_truth/labels.csv`.

| File | Expected | Predicted | Result |
|---|---|---|---|
| test_01.txt | none | none | OK |
| test_02.pdf | none | none | OK |
| test_03.docx | none | none | OK |
| test_04.txt | PAN | PAN | OK |
| test_05.txt | none | none | OK |
| test_06.txt | DL | none | **MISS** |
| test_08.txt | none | none | OK |
| test_07.csv | phone, email | — | excluded (see below) |
| test_09.json | phone, email | — | excluded (see below) |

## The one miss, explained

`test_06.txt` is a synthetic driving licence document. It isn't detected because
`detection/detect.py`'s pattern registry has no `DL` entry at all — there is no
regex for a driving licence number, so it never becomes a candidate in the first
place. This is a gap in another track's file, not in scoring — confidence and
policy resolution never get a chance to run on something that was never detected.
Flagged to whoever owns `detection/detect.py`.

## What's excluded from the metric, and why

- **`test_07.csv`, `test_09.json`** — both crash `pipeline.analyze()` with a
  Windows-specific `PermissionError` in `ingestion.extract`'s temp-file handling.
  Not a scoring bug; excluded rather than silently skipped or faked.
- **NAME/ADDRESS (NER) detections** — reported by the eval script but not scored.
  `ground_truth/labels.csv`'s taxonomy only covers government-ID-style types
  (aadhaar, pan, driving_licence, credit_card, phone, email); it has no NAME or
  ADDRESS category. Spotcheck: `test_02.pdf` contains a real name ("Student Name:
  Brenda Taylor") that NER correctly finds, but the file is labeled `none` because
  the ground truth simply has nowhere to record that. Scoring NAME/ADDRESS against
  this ground truth would produce a number that looks like NER accuracy but is
  really measuring a labeling gap.

## Honest limitations of this number

- **Small sample.** 6 files actually scored. This is a sanity check that the
  scoring pipeline is wired correctly end-to-end, not a statistically meaningful
  accuracy claim.
- **Doc-level ground truth, not per-field.** `labels.csv` says which pii_types
  appear somewhere in a file, not their exact location/count. A file with the
  right type detected in the wrong place would still read as correct here.
- **Zero false positives so far** is a real, verified result (the invoice-decoy
  document with a 12-digit number correctly produces no detections at all, and
  a negative-signal false positive from NER — "Wireless Keyboard" misread as a
  name — correctly scores confidence 0.2, not enough to be a policy concern) —
  but it's one data point, not proof the negative-signal design generalizes.

## What would raise this number

Not more scoring logic — the confidence/policy layer is doing what it's supposed
to on every file it's actually given a chance to see. The gap is upstream: a `DL`
pattern in `detection/detect.py`'s registry, a fix to `ingestion.extract`'s
Windows temp-file handling, and eventually a larger, per-field ground truth set
from whoever owns `ground_truth/`.
