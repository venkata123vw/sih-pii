from redact import apply_redactions


input_pdf = "testdata/documents/test.pdf"
output_pdf = "testdata/documents/redacted.pdf"


decisions = {
    "detections": [
        {
            "page_index": 0,
            "bbox": [186.0, 177.0, 332.0, 207.0],
            "text": "1234 5678 9012",
        },
        {
            "page_index": 0,
            "bbox": [164.46, 228.50, 225.58, 255.98],
            "text": "Rithika"
        }
    ]
}




result = apply_redactions(
    input_pdf,
    decisions,
    output_pdf
)


print("Redacted PDF created:")
print(result)

import pymupdf


doc = pymupdf.open(output_pdf)

text = ""

for page in doc:
    text += page.get_text()

doc.close()

for detection in decisions["detections"]:
    assert detection["text"] not in text

print("PASS: All detected PII was successfully redacted.")

