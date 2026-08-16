from redact import apply_redactions


input_pdf = "testdata/documents/test.pdf"
output_pdf = "testdata/documents/redacted.pdf"


decisions = {
    "detections": [
        {
            "page_num": 0,
            "bbox": [100, 180, 300, 205]
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