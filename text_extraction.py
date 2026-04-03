import fitz
import sys

def extract_blocks(pdf_path):
    doc = fitz.open(pdf_path)
    pages_blocks = []

    for page in doc:
        blocks = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = ""
                line_size = 0
                line_bold = False
                line_italic = False
                line_left = None

                for span in line["spans"]:
                    line_text += span["text"]
                    line_size = max(line_size, span["size"])
                    line_bold = line_bold or bool(span["flags"] & 2**4)
                    line_italic = line_italic or bool(span["flags"] & 2**1)
                    if line_left is None:
                        line_left = span["origin"][0]

                if line_text.strip():
                    blocks.append({
                        "text": line_text.strip(),
                        "size": line_size,
                        "bold": line_bold,
                        "italic": line_italic,
                        "left": line_left
                    })
        pages_blocks.append(blocks)

    return pages_blocks

def classify_line(block, body_size, max_size, base_left):
    text = block["text"]
    size = block["size"]
    bold = block["bold"]
    italic = block["italic"]
    left = block["left"]

    # headings by font size
    if size >= max_size * 0.95:
        return f"# {text}"
    elif size >= body_size * 1.4:
        return f"## {text}"
    elif size >= body_size * 1.15:
        return f"### {text}"

    # list detection by indentation
    is_indented = left > base_left + 10
    if text.startswith(("- ", "* ", "• ")):
        return f"- {text.lstrip('-*• ').strip()}"
    elif is_indented and (text[0].isdigit() or text.startswith(("-", "•"))):
        return f"- {text}"

    # inline formatting
    if bold and italic:
        return f"***{text}***"
    elif bold:
        return f"**{text}**"
    elif italic:
        return f"*{text}*"

    return text

def pdf_to_md(pdf_path, output_path):
    pages_blocks = extract_blocks(pdf_path)

    all_blocks = [b for page in pages_blocks for b in page]
    if not all_blocks:
        print("No text found. Is this a scanned PDF?")
        return

    sizes = [b["size"] for b in all_blocks]
    lefts = [b["left"] for b in all_blocks]
    body_size = sorted(sizes)[len(sizes) // 2]   # median font size = body
    max_size = max(sizes)
    base_left = sorted(lefts)[len(lefts) // 10]  # ~leftmost margin

    md_lines = []
    for page_blocks in pages_blocks:
        for block in page_blocks:
            md_lines.append(classify_line(block, body_size, max_size, base_left))
        md_lines.append("\n---\n")  # page separator

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(md_lines))

    print(f"Done: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python text_extraction.py input.pdf [output.txt]")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else "text_extraction.txt"
    pdf_to_md(input_pdf, output_path)