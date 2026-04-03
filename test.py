import pdfplumber

with pdfplumber.open("BSC transcript.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text and text.strip():
            print(f"Page {i+1}: Has text ✓")
        else:
            print(f"Page {i+1}: Likely scanned image ✗")