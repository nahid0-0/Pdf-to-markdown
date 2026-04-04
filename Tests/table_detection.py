import pdfplumber
import sys

if len(sys.argv) < 2:
    print("Usage: python table_detection.py <input.pdf> [output.txt]")
    sys.exit(1)

input_pdf = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else "table_detection.txt"

lines = []
with pdfplumber.open(input_pdf) as pdf:
    for i, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        # lines.append(f"\n========== PAGE {i} ==========\n")
        # lines.append(f"Tables found: {len(tables)}")
        for t in tables:
            for row in t:
                lines.append(str(row))

with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Saved output to {output_file}")