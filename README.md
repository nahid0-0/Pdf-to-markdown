# Pdf-to-markdown
# pdf-to-markdown

A command-line tool that converts PDF files to clean, structured Markdown. Handles both native text PDFs and scanned image PDFs via OCR fallback. Supports tables, headings, bold/italic/monospace formatting, checkboxes, code blocks, and cross-page table continuation.

---

## Table of contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Limitations](#limitations)

---

## Requirements

- Python 3.9+
- Tesseract OCR binary installed on your system
- The following Python packages:
  - `pymupdf` (imported as `fitz`)
  - `pdfplumber`
  - `pytesseract`
  - `Pillow`
- Optional, for LLM polish:
  - `google-generativeai`
  - A valid `GEMINI_API_KEY` environment variable

### Install Tesseract

**Ubuntu / Debian**
```
sudo apt install tesseract-ocr
```

**macOS**
```
brew install tesseract
```

**Windows**

Download the installer from the [UB Mannheim Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki) and add the install directory to your `PATH`.

---

## Installation

```
pip install pymupdf pdfplumber pytesseract Pillow
```

For LLM polish support:

```
pip install google-generativeai
```

No package setup or virtual environment is strictly required, though one is recommended.

---

## Usage

### Basic conversion

```
python app.py input.pdf output.md
```

### With LLM polish

Runs an additional Gemini API pass to fix OCR artifacts, broken tables, and formatting issues.

```
python app.py input.pdf output.md --polish
```

Requires `GEMINI_API_KEY` to be set:

```
export GEMINI_API_KEY=your_key_here
python app.py input.pdf output.md --polish
```

If the key is missing, the polish step is silently skipped and the raw conversion output is written instead.

---

## How it works

The converter processes each page of the PDF independently, then merges results into a single Markdown file.

### Page routing

For each page, the tool checks whether extractable text exists using PyMuPDF's `get_text()`. If the result is fewer than 20 characters, the page is treated as a scanned image and routed to the OCR path. Otherwise, the standard text extraction path is used.

### Text extraction path

Uses PyMuPDF to read text as a structured dictionary of blocks, lines, and spans. Each span carries font metadata (size, flags, font name) used for formatting decisions.

**Pass 1 — orphan merging**

List markers that appear on their own line (a lone `•`, `-`, or digit) are merged with the line that follows them.

**Pass 2 — paragraph merging and list detection**

Lines of similar font size are merged into paragraphs unless the current line starts with a list marker. Code lines are never merged with adjacent lines.

**Pass 3 — classification and formatting**

Each merged item is classified as one of:

- Heading (H1, H2, H3) based on font size relative to the median body size
- Checkbox item, detected from vector drawings on the page
- Numbered list item
- Bullet list item
- Body text
- Footer — lines in the bottom 10% of the page with small font are silently dropped

Tables are detected separately using pdfplumber and rendered as Markdown pipe tables. Any text block that overlaps a detected table bounding box is skipped to avoid duplication.

### OCR path

Used for scanned or image-only pages.

1. The page is rendered at 300 DPI using PyMuPDF and preprocessed with Pillow (grayscale, contrast boost, binarization).
2. Tesseract extracts word-level bounding boxes.
3. Words are grouped into rows by vertical proximity (15px tolerance).
4. Rows with 3+ word clusters separated by 100px+ gaps are identified as table rows.
5. Table rows are rendered as Markdown pipe tables; remaining rows are treated as prose.
6. `ocr_cleanup()` applies rule-based fixes: checkbox normalization, heading detection from numbered patterns, common OCR artifact correction, and broken-line merging.

### Post-processing

Applied to all pages regardless of path:

- **Deduplication** — repeated blocks (common with headers/footers repeated across pages) are removed using a seen-set.
- **Code block merging** — consecutive lines that are predominantly inline code (backtick-wrapped) are collapsed into a fenced code block. Language detection is attempted from the first line.
- **Cross-page table continuation** — if a table at the bottom of one page matches the column count of the first table on the next page, the continuation rows are merged in without repeating the header row.

### LLM polish (optional)

If `--polish` is passed, the full Markdown output is sent to Gemini 2.5 Flash with a prompt instructing it to fix table reconstruction, code block indentation, OCR misreads, and checkbox formatting without altering content. Large documents are chunked at ~15,000 characters on double-newline boundaries.

---

## Configuration

All configuration is currently hardcoded in the source. The relevant values and their defaults:

| Parameter | Value | Location | Effect |
|---|---|---|---|
| Text threshold | 20 chars | `convert()` | Pages below this trigger OCR fallback |
| OCR DPI | 300 | `ocr_page()` | Render resolution for scanned pages |
| Contrast enhancement | 2.0× | `ocr_page()` | Pillow contrast boost before binarization |
| Binarization threshold | 140 | `ocr_page()` | Pixel cutoff for black/white conversion |
| Footer Y threshold | 90% page height | `is_footer()` | Lines below this are candidates for dropping |
| Footer size threshold | body_size × 0.95 | `is_footer()` | Small text near the bottom is dropped |
| Table min rows (OCR) | 3 | `ocr_page()` | Fewer rows → not classified as a table |
| OCR word row gap | 15px | `ocr_page()` | Max vertical distance to be on the same row |
| OCR column gap | 100px | `ocr_page()` | Min horizontal gap between table columns |
| LLM chunk size | 15,000 chars | `llm_polish()` | Max characters per Gemini API call |
| Gemini model | `gemini-2.5-flash` | `llm_polish()` | Model used for the polish pass |

---

## Limitations

### General

- **Multi-column layouts are not supported.** Text in a two-column magazine or academic paper layout will be extracted in reading order as determined by PyMuPDF, which often means columns are interleaved rather than read left-to-right per column.

- **Figures and diagrams are ignored.** Image content embedded in the PDF (charts, photos, illustrations) is not extracted or described. Only vector drawings used for checkboxes are inspected.

- **Footnotes and endnotes are dropped.** The footer filter removes small text at the bottom of the page. Legitimate footnote content will be lost.

- **Mathematical formulas are not rendered.** Equations may extract as a garbled sequence of characters depending on how the PDF encodes them. LaTeX or MathML output is not supported.

- **Right-to-left text is not supported.** Arabic, Hebrew, and other RTL scripts may extract in the wrong order.

### Text extraction path

- **Font detection for bold/italic is heuristic.** It relies on the font name string containing words like `bold` or `italic`, and on PDF font flags. PDFs that embed fonts under non-standard names may fail to detect formatting.

- **Heading size detection is relative.** The heading thresholds (1.15×, 1.4×, 0.95× of body size) are fixed multipliers. Documents with unusual font size distributions (e.g. everything in one size) will produce no headings or too many headings.

- **Code detection is based on font name.** A span is treated as monospace if its font name contains `mono`, `courier`, or `code`. PDFs using a custom monospace font under an unrelated name will not be detected.

- **Cross-page table merging is based on column count only.** Two unrelated tables on successive pages with the same number of columns will be incorrectly merged.

### OCR path

- **OCR accuracy depends on scan quality.** Low-resolution, skewed, stained, or handwritten content will degrade output quality significantly. The 300 DPI render and binarization help but cannot compensate for poor source material.

- **Table detection in OCR mode is approximate.** The column cluster heuristic works on horizontal word spacing. Tables with narrow columns, merged cells, or irregular spacing may be misclassified or rendered incorrectly.

- **OCR does not detect bold, italic, or heading size.** All OCR-extracted text is treated as plain body text or headings detected by numbered prefix patterns only. Formatting present in the original scanned document is not recovered.

- **The LLM polish pass can introduce errors.** Gemini is instructed not to change content, but hallucination is possible especially on damaged or ambiguous OCR output. Review the output for correctness when using `--polish` on critical documents.

### Performance

- **Large documents are slow.** OCR at 300 DPI is CPU-intensive. A 100-page scanned document can take several minutes. The LLM polish pass adds additional latency and API cost proportional to document length.

- **Memory usage scales with page count.** All Markdown lines are accumulated in memory before writing. Very large PDFs may require significant RAM.