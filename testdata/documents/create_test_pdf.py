import pymupdf

doc = pymupdf.open()

# -------------------------
# PAGE 1: Normal page
# -------------------------
page = doc.new_page(width=600, height=800)

page.insert_text((100, 150), "Aadhaar: 2341 2341 2346", fontsize=20)
page.insert_text((100, 200), "Name: Rithika", fontsize=20)
page.insert_text((100, 250), "Email: rithika@example.com", fontsize=20)
page.insert_text((100, 300), "Order ID: 202508170008", fontsize=20)
page.insert_text((100, 350), "PAN: ALWPG5809L", fontsize=20)
page.insert_text((100, 400), "Card: 4242 4242 4242 4242", fontsize=20)

# -------------------------
# PAGE 2: Rotated page
# -------------------------
page2 = doc.new_page(width=600, height=800)

page2.insert_text(
    (100, 200),
    "Rotated page test content",
    fontsize=20
)

page2.insert_text(
    (100, 250),
    "Email: rotated@example.com",
    fontsize=20
)

# Rotate second page
page2.set_rotation(90)

doc.save("testdata/documents/test.pdf")
doc.close()

print("Final 2-page test PDF created successfully!")
