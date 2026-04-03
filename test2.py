import fitz  # pymupdf
import sys

def is_bold(flags):
    return bool(flags & 2**4)

def is_italic(flags):
    return bool(flags & 2**1)

def extract_blocks(pdf_path):
    doc = fitz.open(pdf_path)
    blocks = []

    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:  # skip images
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    blocks.append({
                        "text": span["text"].strip(),
                        "size": span["size"],
                        "bold": is_bold(span["flags"]),
                        "italic": is_italic(span["flags"]),
                        "origin": span["origin"]
                    })

    return blocks

def classify_block(block, max_size, body_size):
    text = block["text"]
    size = block["size"]
    ratio = size / max_size

    if not text:
        return None

    if ratio > 0.85:
        return f"# {text}"
    elif ratio > 0.7:
        return f"## {text}"
    elif ratio > 0.55 or (block["bold"] and size > body_size):
        return f"### {text}"
    elif text.startswith(("- ", "* ", "• ")):
        return f"- {text.lstrip('-*• ')}"
    elif len(text) < 4 and text[0].isdigit():
        return f"- {text}"  # numbered list item
    else:
        if block["bold"] and block["italic"]:
            return f"***{text}***"
        elif block["bold"]:
            return f"**{text}**"
        elif block["italic"]:
            return f"*{text}*"
        return text

def pdf_to_md(pdf_path, output_path):
    blocks = extract_blocks(pdf_path)

    if not blocks:
        print("No text found, falling back to OCR...")
        ocr_fallback(pdf_path, output_path)
        return

    sizes = [b["size"] for b in blocks]
    max_size = max(sizes)
    body_size = sorted(sizes)[len(sizes) // 2]  # median = body text

    lines = []
    for block in blocks:
        md = classify_block(block, max_size, body_size)
        if md:
            lines.append(md)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(lines))

    print(f"Done: {output_path}")

def ocr_fallback(pdf_path, output_path):
    import pytesseract
    from PIL import Image

    doc = fitz.open(pdf_path)
    text = []

    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            # Tesseract uses ISO 639-2 language codes (English = "eng").
            text.append(pytesseract.image_to_string(img, lang="eng"))
        except pytesseract.TesseractError as e:
            raise RuntimeError(
                "OCR failed. Ensure Tesseract is installed and has English language data (eng)."
            ) from e

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(text))

if __name__ == "__main__":
    pdf_to_md(sys.argv[1], sys.argv[2])