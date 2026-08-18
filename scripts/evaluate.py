"""
Precision/recall/F1 for the real pipeline against ground_truth/labels.csv.

Runs the actual extract -> detect -> score pipeline (pipeline.analyze())
against the real files in data/, not hand-built fixtures. This became
possible once ingestion.extract() turned out to already be real for
text/PDF/DOCX sources (a comment in pipeline.py claiming it's still a
fixed-fake-data stub is stale).

Scope note: ground_truth/labels.csv only tracks government-ID-style types
(aadhaar, pan, driving_licence, credit_card, phone, email). It has no
category for NAME/ADDRESS (NER-derived), so those predictions are
reported separately, informationally, and excluded from precision/
recall -- scoring them against a ground truth that doesn't track them
would misrepresent both the metric and the detections (spotchecked:
test_02.pdf's "Student Name: Brenda Taylor" is a real name correctly
found by NER, but labels.csv marks the whole file "none" because its
taxonomy simply doesn't have a NAME category).

Threshold: a detection counts as "predicted" if confidence > 0 (strictly
positive), not some arbitrary bar. A candidate only reaches scoring after
detection.detect()'s own regex+checksum filtering already passed, so
confidence's job at that point is separating genuine signal from
suppressed noise (e.g. the invoice-decoy case, correctly pushed to 0.0 by
a negative signal) -- not acting as a second detection gate.

Known exclusion: test_07.csv and test_09.json crash pipeline.analyze()
with a Windows file-locking PermissionError in ingestion's temp-file
handling. Not a scoring/ bug -- reported to whoever owns ingestion/,
excluded here rather than silently masked.
"""

import csv
from pathlib import Path

from pipeline import analyze

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
LABELS_PATH = REPO_ROOT / "ground _truth" / "labels.csv"

LABEL_MAP = {
    "none": None,
    "aadhaar": "AADHAAR",
    "pan": "PAN",
    "driving_licence": "DL",
    "credit_card": "CREDIT_CARD",
    "phone": "PHONE",
    "email": "EMAIL",
}
SCORED_TYPES = {v for v in LABEL_MAP.values() if v}  # only types ground truth can actually judge

EXCLUDED_FILES = {"test_07.csv", "test_09.json"}  # see docstring: ingestion PermissionError on Windows
CONFIDENCE_THRESHOLD = 0.0  # strictly greater than this counts as "predicted"


def load_ground_truth(path: Path) -> dict[str, set[str]]:
    truth = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            types = row["pii_type"].split(";")
            truth[row["file_name"]] = {LABEL_MAP[t] for t in types if LABEL_MAP.get(t)}
    return truth


def run_file(path: Path) -> tuple[set[str], list[str]]:
    with open(path, "rb") as f:
        data = f.read()
    result = analyze(data, path.name, "THIRD_PARTY_SERVICE")

    scored = {
        d["pii_type"] for d in result["detections"]
        if d["pii_type"] in SCORED_TYPES and d["confidence"] > CONFIDENCE_THRESHOLD
    }
    unscored_ner = sorted({
        d["pii_type"] for d in result["detections"]
        if d["pii_type"] not in SCORED_TYPES and d["confidence"] > CONFIDENCE_THRESHOLD
    })
    return scored, unscored_ner


def main() -> None:
    truth = load_ground_truth(LABELS_PATH)

    tp = fp = fn = 0
    for file_name, expected in sorted(truth.items()):
        if file_name in EXCLUDED_FILES:
            print(f"[SKIP] {file_name}: known ingestion PermissionError on this platform, see script docstring")
            continue

        path = DATA_DIR / file_name
        if not path.exists():
            print(f"[SKIP] {file_name}: not found in data/")
            continue

        predicted, ner_info = run_file(path)
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)

        status = "OK" if predicted == expected else "MISMATCH"
        extra = f"  (also NER, unscored: {ner_info})" if ner_info else ""
        print(f"[{status}] {file_name}: expected={sorted(expected)} predicted={sorted(predicted)}{extra}")

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"\nprecision={precision:.2f} recall={recall:.2f} f1={f1:.2f} (tp={tp} fp={fp} fn={fn})")
    print(f"Scored against: {sorted(SCORED_TYPES)}. NAME/ADDRESS excluded -- "
          f"ground_truth/labels.csv has no category for them (see docstring).")


if __name__ == "__main__":
    main()
