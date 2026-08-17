import pymupdf


pdf_path = "testdata/documents/test.pdf"

doc = pymupdf.open(pdf_path)

page = doc[0]

words = page.get_text("words")

for word in words:
    x0, y0, x1, y1, text = word[:5]

    print(
        f"Text: {text!r} "
        f"BBox: [{x0:.2f}, {y0:.2f}, {x1:.2f}, {y1:.2f}]"
    )

doc.close()