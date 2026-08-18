import pymupdf

# Create a new PDF
doc = pymupdf.open()

# Create a page
page = doc.new_page(width=600, height=800)

# Add fake PII
page.insert_text(
    (100, 200),
    "Aadhaar: 1234 5678 9012",
    fontsize=20
)

page.insert_text(
    (100, 250),
    "Name: Rithika",
    fontsize=20
)

page.insert_text(
    (100, 300),
    "Email: rithika@example.com",
    fontsize=20
)

# Save the PDF
doc.save("testdata/documents/test.pdf")

doc.close()

print("Test PDF created successfully!")