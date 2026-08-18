"""Builds a fixture PDF resembling the SIH test doc, incl. a rotated page."""
import pymupdf, os

def build(path="testdata/documents/test.pdf"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 100), "KYC Verification Form", fontsize=16)
    p.insert_text((72, 140), "Name: Rithika", fontsize=12)
    p.insert_text((72, 170), "Aadhaar: 1234 5678 9012", fontsize=12)
    p.insert_text((72, 200), "Email: rithika@example.com", fontsize=12)
    p.insert_text((72, 230), "PAN: ABCDE1234F", fontsize=12)
    # page 2, rotated - to test rotation behaviour
    p2 = doc.new_page()
    p2.insert_text((72, 140), "Aadhaar: 4321 8765 2109", fontsize=12)
    p2.set_rotation(90)
    doc.save(path)
    doc.close()
    return path

if __name__ == "__main__":
    path = build()
    doc = pymupdf.open(path)
    for i, page in enumerate(doc):
        print(f"--- page {i} rotation={page.rotation} rect={page.rect}")
        for w in page.get_text("words"):
            print(f"  {w[4]!r:30} [{w[0]:.2f}, {w[1]:.2f}, {w[2]:.2f}, {w[3]:.2f}]")
    doc.close()
