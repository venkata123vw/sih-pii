"""
Dump word coordinates from a PDF, and optionally emit a ready-to-paste
detections payload for a phrase.

Two uses:

    python check_coordinates.py testdata/documents/test.pdf
    python check_coordinates.py testdata/documents/test.pdf "1234 5678 9012"

The second form is the one that matters: PII values span multiple words, and
the bbox in the contract is the *union* across joined tokens. Eyeballing four
separate word boxes and adding them up by hand is how stale bboxes get into
fixtures.
"""

import sys

import pymupdf


def dump_words(path: str) -> None:
    doc = pymupdf.open(path)
    try:
        for page_num, page in enumerate(doc):
            print(f"--- page {page_num}  rotation={page.rotation}  rect={page.rect}")
            for word in page.get_text("words"):
                x0, y0, x1, y1, text = word[:5]
                print(f"  {text!r:28} bbox=[{x0:.2f}, {y0:.2f}, {x1:.2f}, {y1:.2f}]")
    finally:
        doc.close()


def find_phrase(path: str, phrase: str) -> None:
    """Emit contract-shaped detections for every occurrence of `phrase`."""
    doc = pymupdf.open(path)
    try:
        found = False
        for page_num, page in enumerate(doc):
            # search_for returns one Rect per line the phrase occupies, already
            # unioned across the words it spans.
            for rect in page.search_for(phrase):
                found = True
                print(
                    "{\n"
                    f'    "pii_type": "TODO",\n'
                    f'    "value": {phrase!r},\n'
                    f'    "page_num": {page_num},\n'
                    f'    "bbox": [{rect.x0:.2f}, {rect.y0:.2f}, {rect.x1:.2f}, {rect.y1:.2f}],\n'
                    f'    "policy_action": "REMOVE",\n'
                    "},"
                )
        if not found:
            print(f"{phrase!r} not found in {path}")
            print("If the PDF is a scan, there is no text layer — the OCR track owns it.")
    finally:
        doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: check_coordinates.py <pdf> [phrase]")
    if len(sys.argv) == 2:
        dump_words(sys.argv[1])
    else:
        find_phrase(sys.argv[1], sys.argv[2])