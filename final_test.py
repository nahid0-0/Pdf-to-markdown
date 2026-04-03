import fitz
import pdfplumber
import sys
import re

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

def format_span(span):
    text = span["text"]
    if not text.strip():
        return text
    
    flags = span["flags"]
    font = span["font"].lower()
    
    bold = "bold" in font or bool(flags & 2**4)
    italic = "italic" in font or bool(flags & 2**1)
    mono = any(x in font for x in ["mono", "courier", "code"])

    if mono: 
        return f"`{text}`"

    # Preserve leading/trailing spaces for concatenation
    l_space = len(text) - len(text.lstrip())
    r_space = len(text) - len(text.rstrip())
    core = text.strip()

    if bold and italic: 
        core = f"***{core}***"
    elif bold: 
        core = f"**{core}**"
    elif italic: 
        core = f"*{core}*"

    return (" " * l_space) + core + (" " * r_space)

def is_footer(text, size, bbox, page_height, body_size):
    y1 = bbox[3]
    is_bottom = y1 > page_height * 0.90
    
    # Filter if it's small text at the bottom, or just a standalone number at the bottom
    if is_bottom and size < body_size * 0.95: 
        return True
    if is_bottom and text.strip().isdigit(): 
        return True
    return False

def table_to_md(table):
    if not table or not table[0]: 
        return ""
    lines = []
    header = [str(c).replace("\n", " ") if c else "" for c in table[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in table[1:]:
        cells = [str(c).replace("\n", " ") if c else "" for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)

def clean_markdown(text):
    # Merge adjacent identical markdown tags (e.g. "**Word** **Wrap**" -> "**Word Wrap**")
    text = re.sub(r"\*\*\s+\*\*", " ", text)
    text = re.sub(r"\*\s+\*", " ", text)
    return text

def process_blocks(fitz_page, table_bboxes, rendered_tables, table_map, body_size, max_size):
    md_lines = []
    page_height = fitz_page.rect.height

    for block in fitz_page.get_text("dict")["blocks"]:
        if block["type"] != 0: 
            continue

        # Check for table overlap
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

        # Process raw lines and format spans
        lines_data = []
        for line in block["lines"]:
            raw_text = "".join(s["text"] for s in line["spans"]).strip()
            if not raw_text: 
                continue
            
            fmt_text = "".join(format_span(s) for s in line["spans"]).strip()
            size = max(s["size"] for s in line["spans"])
            bbox = (line["bbox"][0], line["bbox"][1], line["bbox"][2], line["bbox"][3])
            lines_data.append({"raw": raw_text, "fmt": fmt_text, "size": size, "bbox": bbox})

        if not lines_data: 
            continue

        # Pass 1: Merge orphaned list markers (e.g. a "1." or "•" on its own line)
        merged_lines = []
        i = 0
        while i < len(lines_data):
            curr = lines_data[i]
            if (curr["raw"].isdigit() or curr["raw"] in "•-*‣◦·") and i + 1 < len(lines_data):
                nxt = lines_data[i+1]
                curr["raw"] += " " + nxt["raw"]
                curr["fmt"] += " " + nxt["fmt"]
                curr["size"] = max(curr["size"], nxt["size"])
                curr["bbox"] = (min(curr["bbox"][0], nxt["bbox"][0]), 
                                min(curr["bbox"][1], nxt["bbox"][1]), 
                                max(curr["bbox"][2], nxt["bbox"][2]), 
                                max(curr["bbox"][3], nxt["bbox"][3]))
                merged_lines.append(curr)
                i += 2
            else:
                merged_lines.append(curr)
                i += 1

        # Pass 2: Merge paragraph continuations & identify lists
        final_items = []
        for line in merged_lines:
            # Matches markers like "1.", "1)", "•", "-"
            is_marker = bool(re.match(r"^(\d+[\.\)]?|[•‣◦·]|-)\s*", line["raw"]))
            if not final_items:
                line["is_list"] = is_marker
                final_items.append(line)
            else:
                prev = final_items[-1]
                # Join condition: similar size, and current line doesn't start a new list
                if not is_marker and abs(line["size"] - prev["size"]) < 2:
                    prev["raw"] += " " + line["raw"]
                    prev["fmt"] += " " + line["fmt"]
                    prev["bbox"] = (min(prev["bbox"][0], line["bbox"][0]), 
                                    min(prev["bbox"][1], line["bbox"][1]), 
                                    max(prev["bbox"][2], line["bbox"][2]), 
                                    max(prev["bbox"][3], line["bbox"][3]))
                else:
                    line["is_list"] = is_marker
                    final_items.append(line)

        # Pass 3: Classify and format the final blocks
        for item in final_items:
            if is_footer(item["raw"], item["size"], item["bbox"], page_height, body_size):
                continue

            fmt_text = clean_markdown(item["fmt"])
            raw_text = item["raw"]

            # Headings
            if not item["is_list"]:
                # Strip inline formatting if it's going to be a header to avoid "## **Heading**"
                plain = re.sub(r"[*_`]", "", fmt_text)
                if item["size"] >= max_size * 0.95:
                    md_lines.append(f"# {plain}")
                    continue
                elif item["size"] >= body_size * 1.4:
                    md_lines.append(f"## {plain}")
                    continue
                elif item["size"] >= body_size * 1.15:
                    md_lines.append(f"### {plain}")
                    continue

            # Lists
            if item["is_list"]:
                num_match = re.match(r"^(\d+)[\.\)]?\s*", raw_text)
                if num_match:
                    # Strip original numbers from the formatted text so we can inject a clean one
                    fmt_text = re.sub(r"^([*`_]*)\d+[\.\)]?([*`_]*)\s*", r"\1\2", fmt_text)
                    md_lines.append(f"{num_match.group(1)}. {fmt_text.strip()}")
                else:
                    # Strip messy bullet characters from formatted text
                    fmt_text = re.sub(r"^([*`_]*)[•\-*‣◦·]([*`_]*)\s*", r"\1\2", fmt_text)
                    md_lines.append(f"- {fmt_text.strip()}")
            else:
                md_lines.append(fmt_text)

    return md_lines

def convert(pdf_path, output_path):
    sizes = get_sizes(pdf_path)
    if not sizes:
        print("No text found.")
        return

    sizes.sort()
    body_size = sizes[len(sizes) // 2]
    max_size = sizes[-1]

    doc = fitz.open(pdf_path)
    all_md_lines = []

    with pdfplumber.open(pdf_path) as plumber_doc:
        for i, (fitz_page, plumber_page) in enumerate(zip(doc, plumber_doc.pages)):
            
            table_bboxes = [t.bbox for t in plumber_page.find_tables()]
            tables = plumber_page.extract_tables()
            table_map = {t.bbox: tables[j] for j, t in enumerate(plumber_page.find_tables())}
            rendered_tables = set()

            md_lines = process_blocks(fitz_page, table_bboxes, rendered_tables, table_map, body_size, max_size)
            all_md_lines.extend(md_lines)
            
            # Page separator
            all_md_lines.append("---")

    with open(output_path, "w", encoding="utf-8") as f:
        # Double newline makes for clean, spaced Markdown rendering
        f.write("\n\n".join(all_md_lines))

    print(f"Done: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python app.py input.pdf output.md")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])