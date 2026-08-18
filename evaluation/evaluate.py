"""
P6 Evaluation Script

Compares detector predictions against synthetic ground truth
and calculates Precision, Recall and F1 score.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from detection.detect import detect


# ---------------------------------------------------------
# Synthetic evaluation inputs
# ---------------------------------------------------------

def tok(text, i):
    return {
        "text": text,
        "bbox": [10 * i, 100, 10 * i + 40, 120],
        "ocr_conf": 1.0,
    }


def page(words, page_num=0):
    return {
        "page_num": page_num,
        "width": 1240,
        "height": 1754,
        "tokens": [tok(word, i) for i, word in enumerate(words)],
        "full_text": " ".join(words),
    }


def extraction(*pages):
    return {
        "doc_id": "evaluation_doc",
        "source_type": "scanned_image",
        "pages": list(pages),
    }


# ---------------------------------------------------------
# Evaluation dataset
# ---------------------------------------------------------

DATASET = [
    {
        "name": "test_aadhaar_valid",
        "input": extraction(
            page(["Aadhaar", "2341", "2341", "2346"])
        ),
        "expected": [
            {
                "pii_type": "AADHAAR",
                "value": "2341 2341 2346"
            }
        ],
    },
    {
        "name": "test_pan",
        "input": extraction(
            page(["PAN", "ALWPG5809L"])
        ),
        "expected": [
            {
                "pii_type": "PAN",
                "value": "ALWPG5809L",
            }
        ],
    },
    {
        "name": "test_phone",
        "input": extraction(
            page(["Mobile:", "9876543210"])
        ),
        "expected": [
            {
                "pii_type": "PHONE",
                "value": "9876543210",
            }
        ],
    },
    {
        "name": "test_email",
        "input": extraction(
            page(["Email:", "test@example.com"])
        ),
        "expected": [
            {
                "pii_type": "EMAIL",
                "value": "test@example.com",
            }
        ],
    },
    {
        "name": "test_clean",
        "input": extraction(
            page(["Invoice", "Total", "4500", "Rupees"])
        ),
        "expected": [],
    },
]


# ---------------------------------------------------------
# Normalization
# ---------------------------------------------------------

def normalize(value):
    """Normalize values before comparison."""
    return "".join(str(value).lower().split())


def make_key(item):
    return (
        item["pii_type"],
        normalize(item["value"]),
    )


# ---------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------

def main():
    total_tp = 0
    total_fp = 0
    total_fn = 0

    results = []

    for case in DATASET:
        output = detect(case["input"])

        predictions = output.get("candidates", [])
        expected = case["expected"]

        predicted_keys = {
            make_key(item)
            for item in predictions
        }

        expected_keys = {
            make_key(item)
            for item in expected
        }

        tp = len(predicted_keys & expected_keys)
        fp = len(predicted_keys - expected_keys)
        fn = len(expected_keys - predicted_keys)

        total_tp += tp
        total_fp += fp
        total_fn += fn

        results.append(
            {
                "name": case["name"],
                "expected": expected,
                "predicted": predictions,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }
        )

        print(f"\n[{case['name']}]")
        print(f"  Expected : {len(expected_keys)}")
        print(f"  Predicted: {len(predicted_keys)}")
        print(f"  TP={tp}  FP={fp}  FN={fn}")

    # -----------------------------------------------------
    # Metrics
    # -----------------------------------------------------

    precision = (
        total_tp / (total_tp + total_fp)
        if total_tp + total_fp
        else 0.0
    )

    recall = (
        total_tp / (total_tp + total_fn)
        if total_tp + total_fn
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    print("\n" + "=" * 50)
    print("P6 EVALUATION RESULTS")
    print("=" * 50)

    print(f"True Positives : {total_tp}")
    print(f"False Positives: {total_fp}")
    print(f"False Negatives: {total_fn}")

    print(f"\nPrecision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------

    output_data = {
        "true_positives": total_tp,
        "false_positives": total_fp,
        "false_negatives": total_fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "cases": results,
    }

    result_path = Path("evaluation/results/evaluation_results.json")

    result_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with result_path.open("w", encoding="utf-8") as f:
        json.dump(
            output_data,
            f,
            indent=2,
        )

    print(f"\nResults saved to: {result_path}")


if __name__ == "__main__":
    main()