import fitz
import sys

doc = fitz.open(sys.argv[1])
output = []

for i, page in enumerate(doc):
    output.append(f"\n========== PAGE {i+1} ==========\n")
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                output.append(
                    f"text={repr(text)} | "
                    f"size={span['size']:.1f} | "
                    f"flags={span['flags']} | "
                    f"font={span['font']} | "
                    f"color={span['color']} | "
                    f"bbox={span['bbox']} | "
                    f"ascender={span['ascender']:.3f} | "
                    f"descender={span['descender']:.3f}"
                )

with open("pdfplumber.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Saved to pdfplumber.txt")