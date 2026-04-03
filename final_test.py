import fitz
import pdfplumber
import sys

def overlaps(b1, b2):
    return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

def get_sizes(pdf_path):
    doc = fitz.open(pdf_path)
    sizes = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(span["size"])
    return sizes

def classify(line_text, size, flags, font, left, body_size, max_size, base_left):
    bold = "Bold" in font or "bold" in font or (flags & 2**4)
    italic = "Italic" in font or "italic" in font or (flags & 2**1)
    mono = "Mono" in font or "Courier" in font or "Code" in font or "mono" in font

    if mono:
        return f"`{line_text}`"

    if size >= max_size * 0.95:
        return f"# {line_text}"
    elif size >= body_size * 1.4:
        return f"## {line_text}"
    elif size >= body_size * 1.15:
        return f"### {line_text}"

    is_list_number = line_text.strip().isdigit() and left <= base_left + 5
    is_list_item = left >= base_left + 10

    if is_list_number:
        return None

    if is_list_item:
        if bold and italic:
            return f"- ***{line_text}***"
        elif bold:
            return f"- **{line_text}**"
        elif italic:
            return f"- *{line_text}*"
        return f"- {line_text}"

    if bold and italic:
        return f"***{line_text}***"
    elif bold:
        return f"**{line_text}**"
    elif italic:
        return f"*{line_text}*"

    return line_text

def table_to_md(table):
    if not table or not table[0]:
        return ""
    lines = []
    header = [c.replace("\n", " ") if c else "" for c in table[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in table[1:]:
        cells = [c.replace("\n", " ") if c else "" for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)

def is_footer(line_text, size, left, page_width, body_size):
    if size < body_size * 0.85 and (left < 40 or left > page_width - 40):
        return True
    if line_text.strip().isdigit() and size < body_size:
        return True
    return False

def convert(pdf_path, output_path):
    sizes = get_sizes(pdf_path)
    if not sizes:
        print("No text found.")
        return

    body_size = sorted(sizes)[len(sizes) // 2]
    max_size = max(sizes)

    doc = fitz.open(pdf_path)
    md_lines = []

    with pdfplumber.open(pdf_path) as plumber_doc:
        for i, (fitz_page, plumber_page) in enumerate(zip(doc, plumber_doc.pages)):
            page_width = fitz_page.rect.width
            lefts = []
            for block in fitz_page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    if line["spans"]:
                        lefts.append(line["spans"][0]["bbox"][0])
            base_left = sorted(lefts)[len(lefts) // 10] if lefts else 72

            table_bboxes = [t.bbox for t in plumber_page.find_tables()]
            tables = plumber_page.extract_tables()
            table_map = {t.bbox: tables[j] for j, t in enumerate(plumber_page.find_tables())}

            rendered_tables = set()

            for block in fitz_page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue

                matched_bbox = None
                for tb in table_bboxes:
                    if overlaps(block["bbox"], tb):
                        matched_bbox = tb
                        break

                if matched_bbox:
                    if matched_bbox not in rendered_tables:
                        md_lines.append(table_to_md(table_map[matched_bbox]))
                        rendered_tables.add(matched_bbox)
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

                    if is_footer(line_text, size, left, page_width, body_size):
                        continue

                    result = classify(line_text, size, flags, font, left, body_size, max_size, base_left)
                    if result:
                        md_lines.append(result)

            md_lines.append("\n---\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(md_lines))

    print(f"Done: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python app.py input.pdf output.md")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])