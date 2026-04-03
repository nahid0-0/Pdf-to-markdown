import fitz
import pdfplumber
import sys

def overlaps(b1, b2):
    return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

fitz_doc = fitz.open(sys.argv[1])
plumber_doc = pdfplumber.open(sys.argv[1])

output = []

for i, (fitz_page, plumber_page) in enumerate(zip(fitz_doc, plumber_doc.pages)):
    output.append(f"\n========== PAGE {i+1} ==========\n")

    table_bboxes = [t.bbox for t in plumber_page.find_tables()]

    for block in fitz_page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        if any(overlaps(block["bbox"], tb) for tb in table_bboxes):
            continue

        for line in block["lines"]:
            spans = line["spans"]
            line_text = "".join(span["text"] for span in spans).strip()
            if not line_text:
                continue
            size = max(span["size"] for span in spans)
            bold = any(bool(span["flags"] & 2**4) for span in spans)
            italic = any(bool(span["flags"] & 2**1) for span in spans)
            left = spans[0]["origin"][0]
            output.append(f"[TEXT] size={size:.1f} bold={bold} italic={italic} left={left:.1f} | {line_text}")

with open("text_extraction.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

