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
    tables = plumber_page.extract_tables()

    for block in fitz_page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        block_bbox = block["bbox"]

        if any(overlaps(block_bbox, tb) for tb in table_bboxes):
            continue

        for line in block["lines"]:
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text:
                output.append(f"[TEXT] {line_text}")

    for t_idx, table in enumerate(tables):
        output.append(f"\n[TABLE {t_idx+1}]")
        for row in table:
            output.append(str(row))

with open("merged.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Saved to merged.txt")