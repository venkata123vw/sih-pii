from redact import apply_redactions
import pymupdf


INPUT_PDF = "testdata/documents/test.pdf"
OUTPUT_PDF = "testdata/documents/integration_redacted.pdf"


def test_p4_to_p2_contract():

    # Simulated P4 output
    p4_output = {
        "detections": [
            {
                "page_index": 0,
                "bbox": [186.0, 177.0, 332.0, 207.0],
                "text": "1234 5678 9012",
            }
        ]
    }

    # P2 consumes P4 output
    result = apply_redactions(
        INPUT_PDF,
        p4_output,
        OUTPUT_PDF,
    )

    assert result == OUTPUT_PDF

    # Verify the PII is gone
    doc = pymupdf.open(OUTPUT_PDF)

    text = ""
    for page in doc:
        text += page.get_text()

    doc.close()

    assert "1234 5678 9012" not in text

    # Non-PII should remain
    assert "Rithika" in text
    assert "rithika@example.com" in text

    print("PASS: P4 -> P2 contract integration works.")