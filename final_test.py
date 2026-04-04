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

def is_mono_font(span):
    """Check if a span uses a monospace font."""
    font = span["font"].lower()
    return any(x in font for x in ["mono", "courier", "code"])

def format_span(span):
    text = span["text"]
    if not text.strip():
        return text
    
    flags = span["flags"]
    font = span["font"].lower()
    
    bold = "bold" in font or bool(flags & 2**4)
    italic = "italic" in font or bool(flags & 2**1)
    mono = is_mono_font(span)

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

def clean_cell(c):
    """Clean a table cell: stringify, remove newlines and null chars."""
    if c is None:
        return ""
    return str(c).replace("\n", " ").replace("\x00", "")

def table_to_md(table, is_continuation=False):
    """Convert a table to markdown. If is_continuation, skip the header row + separator."""
    if not table or not table[0]: 
        return ""
    lines = []
    if is_continuation:
        # All rows are data rows (table continues from a previous page)
        for row in table:
            cells = [clean_cell(c) for c in row]
            lines.append("| " + " | ".join(cells) + " |")
    else:
        header = [clean_cell(c) for c in table[0]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in table[1:]:
            cells = [clean_cell(c) for c in row]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)

def clean_markdown(text):
    # Merge adjacent identical markdown tags (e.g. "**Word** **Wrap**" -> "**Word Wrap**")
    text = re.sub(r"\*\*\s+\*\*", " ", text)
    text = re.sub(r"\*\s+\*", " ", text)
    # Merge adjacent backtick spans (e.g. "`word` `next`" -> "`word next`")
    text = re.sub(r"`\s+`", " ", text)
    return text

def detect_code_language(first_line):
    """Try to detect programming language from the first line of a code block."""
    line = first_line.strip()
    patterns = [
        (r'^#!.*/bash', 'bash'),
        (r'^#!.*/sh', 'sh'),
        (r'^#!.*/python', 'python'),
        (r'^#\s*[Pp]ython', 'python'),
        (r'^//\s*[Tt]ype[Ss]cript', 'typescript'),
        (r'^//\s*[Jj]ava[Ss]cript', 'javascript'),
        (r'^--\s*[Pp]ostgre[Ss]', 'sql'),
        (r'^--\s*[Ss][Qq][Ll]', 'sql'),
        (r'^--\s*[Mm]y[Ss][Qq][Ll]', 'sql'),
        (r'^#\s*docker-compose', 'yaml'),
        (r'^#\s*[Dd]ockerfile', 'dockerfile'),
        (r'^(set\s+-[euo]|IFS=)', 'bash'),
        (r'^(WITH|SELECT|INSERT|UPDATE|DELETE|CREATE)\s', 'sql'),
        (r'^(import |from .+ import )', 'python'),
        (r'^(const |let |var |interface |class .+ implements)', 'typescript'),
        (r'^(version:\s*["\'])', 'yaml'),
        (r'^(package |func |type .+ struct)', 'go'),
        (r'^(use |fn |pub |impl |struct |enum )', 'rust'),
    ]
    for pattern, lang in patterns:
        if re.search(pattern, line):
            return lang
    return ''

def is_full_code_line(line):
    """Check if a markdown line is entirely inline code (starts and ends with backtick)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Match lines that are entirely wrapped in backticks: `...`
    # or lines starting with `- ` followed by backtick content (list item with code)
    if stripped.startswith('`') and stripped.endswith('`') and len(stripped) > 2:
        return True
    return False

def merge_code_blocks(md_lines):
    """Post-process md_lines to group consecutive inline-code lines into fenced code blocks."""
    result = []
    i = 0
    while i < len(md_lines):
        # Check if this starts a run of code lines (need at least 2 consecutive)
        if is_full_code_line(md_lines[i]):
            code_run = [md_lines[i]]
            j = i + 1
            while j < len(md_lines) and is_full_code_line(md_lines[j]):
                code_run.append(md_lines[j])
                j += 1
            
            if len(code_run) >= 2:
                # Strip backticks from each line to get raw code
                raw_lines = []
                for cl in code_run:
                    stripped = cl.strip()
                    # Remove outer backticks
                    if stripped.startswith('`') and stripped.endswith('`'):
                        stripped = stripped[1:-1]
                    raw_lines.append(stripped)
                
                lang = detect_code_language(raw_lines[0])
                fenced = f"```{lang}\n" + "\n".join(raw_lines) + "\n```"
                result.append(fenced)
                i = j
            else:
                # Single inline code line — keep as-is
                result.append(md_lines[i])
                i += 1
        else:
            result.append(md_lines[i])
            i += 1
    return result

def detect_checkboxes(fitz_page):
    """Detect checkbox rectangles from vector drawings on the page.
    Returns a list of dicts with 'rect' and 'checked' keys."""
    drawings = fitz_page.get_drawings()
    checkboxes = []
    checkbox_rects = []
    
    # First pass: identify small square rectangles as potential checkboxes
    for d in drawings:
        if not d['items']:
            continue
        item_type = d['items'][0][0]
        rect = d['rect']
        w, h = rect.width, rect.height
        # Checkbox heuristic: small square-ish rectangle (8-16 pt)
        if item_type == 're' and 6 < w < 20 and 6 < h < 20 and abs(w - h) < 3:
            # Check fill color: white=(1,1,1) means unchecked, non-white means checked
            fill = d.get('fill')
            is_checked = False
            if fill and not all(c > 0.9 for c in fill):
                is_checked = True
            checkbox_rects.append(rect)
            checkboxes.append({'rect': rect, 'checked': is_checked})
    
    # Second pass: look for non-rect paths (checkmark lines) drawn inside checkbox rects
    for d in drawings:
        if not d['items']:
            continue
        item_type = d['items'][0][0]
        if item_type == 're':
            continue  # Skip the checkbox rects themselves
        # This is a line/curve — check if it falls inside any checkbox
        path_rect = d['rect']
        for cb in checkboxes:
            if (cb['rect'].x0 <= path_rect.x0 and path_rect.x1 <= cb['rect'].x1 and
                cb['rect'].y0 <= path_rect.y0 and path_rect.y1 <= cb['rect'].y1):
                cb['checked'] = True
    
    return checkboxes

def get_checkbox_for_line(line_bbox, checkboxes, tolerance=15):
    """Check if a checkbox aligns with a text line (same vertical position, to its left).
    Returns 'checked', 'unchecked', or None."""
    line_y_mid = (line_bbox[1] + line_bbox[3]) / 2
    for cb in checkboxes:
        cb_y_mid = (cb['rect'].y0 + cb['rect'].y1) / 2
        # Checkbox should be to the left of the text and vertically aligned
        if cb['rect'].x1 < line_bbox[0] + 5 and abs(cb_y_mid - line_y_mid) < tolerance:
            return 'checked' if cb['checked'] else 'unchecked'
    return None

def process_blocks(fitz_page, table_bboxes, rendered_tables, table_map, body_size, max_size,
                   pending_table_cols=None):
    """Process all blocks on a page. pending_table_cols indicates a table from the
    previous page that may continue on this page (column count to match)."""
    md_lines = []
    first_table_was_continuation = False
    page_height = fitz_page.rect.height
    checkboxes = detect_checkboxes(fitz_page)

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
                tbl_data = table_map[matched_bbox]
                # Check if this is the first table on the page and it continues from prev page
                is_cont = False
                if pending_table_cols is not None and not first_table_was_continuation:
                    if tbl_data and len(tbl_data[0]) == pending_table_cols:
                        is_cont = True
                        first_table_was_continuation = True
                md_lines.append(table_to_md(tbl_data, is_continuation=is_cont))
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
            # Check if all non-empty spans in this line are monospace
            non_empty_spans = [s for s in line["spans"] if s["text"].strip()]
            all_mono = all(is_mono_font(s) for s in non_empty_spans) if non_empty_spans else False
            lines_data.append({"raw": raw_text, "fmt": fmt_text, "size": size, "bbox": bbox, "is_code": all_mono})

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
        # Code lines should NOT be merged with adjacent lines
        final_items = []
        for line in merged_lines:
            # Matches markers like "1.", "1)", "•", "-"
            is_marker = bool(re.match(r"^(\d+[\.\)]?|[•‣◦·]|-)\s*", line["raw"]))
            if not final_items:
                line["is_list"] = is_marker
                final_items.append(line)
            else:
                prev = final_items[-1]
                # Never merge code lines with anything else
                if line.get("is_code") or prev.get("is_code"):
                    line["is_list"] = is_marker
                    final_items.append(line)
                # Join condition: similar size, and current line doesn't start a new list
                elif not is_marker and abs(line["size"] - prev["size"]) < 2:
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

            # Check if this item has an associated checkbox
            cb_state = get_checkbox_for_line(item["bbox"], checkboxes)
            
            if cb_state is not None:
                # Checklist item
                marker = "[x]" if cb_state == 'checked' else "[ ]"
                md_lines.append(f"- {marker} {fmt_text}")
            elif item["is_list"]:
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

    # Return the lines plus info about the last table on this page (for cross-page merging)
    last_table_col_count = None
    if rendered_tables:
        # Find the table bbox closest to the bottom of the page
        page_height = fitz_page.rect.height
        bottom_tables = sorted(rendered_tables, key=lambda b: b[3], reverse=True)
        bottom_bbox = bottom_tables[0]
        # If the table extends to near the bottom of the page, it may continue
        if bottom_bbox[3] > page_height * 0.85:
            last_table_col_count = len(table_map[bottom_bbox][0]) if table_map[bottom_bbox] and table_map[bottom_bbox][0] else None

    return md_lines, last_table_col_count, first_table_was_continuation

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
    pending_table_cols = None  # Track cross-page table continuation

    with pdfplumber.open(pdf_path) as plumber_doc:
        for i, (fitz_page, plumber_page) in enumerate(zip(doc, plumber_doc.pages)):
            
            table_bboxes = [t.bbox for t in plumber_page.find_tables()]
            tables = plumber_page.extract_tables()
            table_map = {t.bbox: tables[j] for j, t in enumerate(plumber_page.find_tables())}
            rendered_tables = set()

            md_lines, last_table_cols, had_continuation = process_blocks(
                fitz_page, table_bboxes, rendered_tables, table_map, 
                body_size, max_size, pending_table_cols=pending_table_cols
            )
            
            # If the first item is a continuation table, merge it with the last table
            if had_continuation and md_lines and all_md_lines:
                all_md_lines[-1] = all_md_lines[-1] + "\n" + md_lines[0]
                all_md_lines.extend(md_lines[1:])
            else:
                all_md_lines.extend(md_lines)
            
            # Track if a table at the bottom might continue on the next page
            pending_table_cols = last_table_cols

    # Post-process: merge consecutive inline-code lines into fenced code blocks
    all_md_lines = merge_code_blocks(all_md_lines)

    with open(output_path, "w", encoding="utf-8") as f:
        # Clean null characters from the final output
        output = "\n\n".join(all_md_lines)
        output = output.replace("\x00", "")
        f.write(output)

    print(f"Done: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python app.py input.pdf output.md")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])