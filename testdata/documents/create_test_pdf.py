import pymupdf

# Create a new PDF
doc = pymupdf.open()

# Create one page
page = doc.new_page(width=600, height=800)

# Add test PII
page.insert_text(
    (100, 150),
    "Aadhaar: 2341 2341 2346",
    fontsize=20
)

page.insert_text(
    (100, 200),
    "Name: Rithika",
    fontsize=20
)

page.insert_text(
    (100, 250),
    "Email: rithika@example.com",
    fontsize=20
)

page.insert_text(
    (100, 300),
    "Order ID: 202508170008",
    fontsize=20
)

page.insert_text(
    (100, 350),
    "PAN: ALWPG5809L",
    fontsize=20
)

page.insert_text(
    (100, 400),
    "Card: 4242 4242 4242 4242",
    fontsize=20
)

# Save the PDF
doc.save("testdata/documents/test.pdf")

doc.close()

print("Test PDF created successfully!")
