# P3 Evaluation Results

Owned by `scoring/`. Reproduce with:

```
python -m scripts.evaluate
```

## Result

**precision = 1.00, recall = 1.00, F1 = 1.00** (tp=6, fp=0, fn=0)

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
| test_06.txt | DL | DL | OK |
| test_07.csv | phone, email | phone, email | OK |
| test_08.txt | none | none | OK |
| test_09.json | phone, email | phone, email | OK |

All 9 files in `data/` now score, and all 9 match ground truth.

## What used to be excluded, and what fixed it

Two gaps existed as of the last evaluation run and have since been closed:

- **`test_06.txt`'s missing `DL` detection** — `detection/detect.py`'s pattern
  registry had no `DL` entry. Fixed: a `DL` entry (format `[A-Z]{5}\d{9}`,
  keyword-gated) now exists in the registry, and `contracts.md` was updated to
  list `DL` as a valid `pii_type`.
- **`test_07.csv`, `test_09.json` crashing `pipeline.analyze()`** — pymupdf has
  no document handler for `.csv`/`.json`; asking it to open one raised
  `FileDataError` and, on Windows, orphaned a file handle that broke the temp
  file's cleanup. Fixed in `ingestion/extract.py`: both extensions are now read
  as plain text (real `csv`/`json` parsing, not naive whitespace-splitting —
  needed because `detection/detect.py`'s patterns are anchored against the
  whole token) before pymupdf is ever invoked.

## What's excluded from the metric, and why

- **NAME/ADDRESS (NER) detections** — reported by the eval script but not scored.
  `ground_truth/labels.csv`'s taxonomy only covers government-ID-style types
  (aadhaar, pan, driving_licence, credit_card, phone, email); it has no NAME or
  ADDRESS category. Spotcheck: `test_02.pdf` contains a real name ("Student Name:
  Brenda Taylor") that NER correctly finds, but the file is labeled `none` because
  the ground truth simply has nowhere to record that. Scoring NAME/ADDRESS against
  this ground truth would produce a number that looks like NER accuracy but is
  really measuring a labeling gap.

## Honest limitations of this number

- **Small sample.** 9 files scored, 6 with a positive label. This is a sanity
  check that the pipeline is wired correctly end-to-end, not a statistically
  meaningful accuracy claim.
- **Doc-level ground truth, not per-field.** `labels.csv` says which pii_types
  appear somewhere in a file, not their exact location/count. A file with the
  right type detected in the wrong place would still read as correct here.
- **Perfect precision/recall on 9 files is a real, verified result** (the
  invoice-decoy document with a 12-digit number correctly produces no
  detections at all, and a negative-signal false positive from NER —
  "Wireless Keyboard" misread as a name — correctly scores confidence 0.2, not
  enough to be a policy concern) — but it's a small, synthetic set, not proof
  the detection/confidence design generalizes to real-world documents.

## What would raise confidence in this number further

Not more scoring logic — every file the pipeline is given a chance to see is
handled correctly right now. The remaining gap is dataset size: a larger,
per-field ground truth set from whoever owns `ground_truth/`, covering more
documents and more PII density per document than the current 9-file
sanity-check set.
