import fitz
import pdfplumber
import sys

def overlaps(b1, b2):
    return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

doc = fitz.open(sys.argv[1])
output = []

with pdfplumber.open(sys.argv[1]) as plumber_doc:
    for i, (fitz_page, plumber_page) in enumerate(zip(doc, plumber_doc.pages)):
        output.append(f"\n========== PAGE {i+1} ==========\n")

        table_bboxes = [t.bbox for t in plumber_page.find_tables()]
        tables = plumber_page.extract_tables()

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
                flags = max(span["flags"] for span in spans)
                font = spans[0]["font"]
                left = spans[0]["bbox"][0]
                output.append(f"text={repr(line_text)} | size={size:.1f} | flags={flags} | font={font} | left={left:.1f}")

        for t_idx, table in enumerate(tables):
            output.append(f"\n[TABLE {t_idx+1}]")
            for row in table:
                output.append(str(row))

with open("pdfplumber_runner.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Saved to pdfplumber_runner.txt")