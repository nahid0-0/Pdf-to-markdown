import fitz
import sys

if len(sys.argv) < 2:
    print("Usage: python test2.py <input.pdf> [output.txt]")
    sys.exit(1)

input_pdf = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else "result.txt"

doc = fitz.open(input_pdf)
pages = []

for i, page in enumerate(doc):
    pages.append(f"\n========== PAGE {i+1} ==========\n\n{page.get_text()}")

with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(pages))

print(f"Saved output to {output_file}")