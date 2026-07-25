"""
doc-translator: Translate a Japanese folder (names + contents) to English.

Output is always created next to the input folder (same parent), named <folder>_english.
The source folder name can be in Japanese characters.

    Windows:  python translate.py "D:/Projects/日本語文書"
              → output: D:/Projects/日本語文書_english

    macOS:    python translate.py "/Users/rayhan/Desktop/日本語文書"
              → output: /Users/rayhan/Desktop/日本語文書_english

Optional flags:
    --pages N   Only translate first N pages of each PDF (useful for testing)

Setup:
    Copy .env.example to .env and fill in your AWS credentials before running.

Note: On Windows, run with: python -X utf8 translate.py ...
  or set PYTHONUTF8=1 in your environment if paths contain Japanese characters.
"""

import sys
import os
import shutil
import csv
from pathlib import Path
from charset_normalizer import from_path

# Ensure stdout/stderr handle Unicode on all platforms (especially Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# On Windows, force UTF-8 mode so Japanese characters in argv are preserved
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)

from translator import translate, translate_name


# ── File handlers ──────────────────────────────────────────────────────────────

def translate_txt(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding = detection.encoding if detection else "utf-8"
    text = src.read_text(encoding=encoding, errors="replace")
    translated = translate(text, context=context)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translated, encoding="utf-8")


def translate_csv(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding = detection.encoding if detection else "utf-8"

    with open(src, encoding=encoding, errors="replace", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    translated_rows = []
    for row in rows:
        translated_row = []
        for cell in row:
            if cell.strip():
                translated_row.append(translate(cell, context=context))
            else:
                translated_row.append(cell)
        translated_rows.append(translated_row)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(translated_rows)


def translate_docx(src: Path, dst: Path, context: str):
    from docx2python import docx2python
    from docx import Document

    # Extract full text structure for context
    extracted = docx2python(str(src))

    # Open original to preserve formatting
    doc = Document(str(src))

    # Translate paragraphs at run level to preserve bold/italic/fonts
    for para in doc.paragraphs:
        if para.text.strip():
            # Collect all run text, translate as one block, redistribute
            full_text = para.text
            translated = translate(full_text, context=context)
            # Replace text in first run, clear the rest
            if para.runs:
                para.runs[0].text = translated
                for run in para.runs[1:]:
                    run.text = ""

    # Translate tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        full_text = para.text
                        translated = translate(full_text, context=context)
                        if para.runs:
                            para.runs[0].text = translated
                            for run in para.runs[1:]:
                                run.text = ""

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))


def translate_xlsx(src: Path, dst: Path, context: str):
    import openpyxl

    wb = openpyxl.load_workbook(str(src))

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.strip():
                    cell.value = translate(cell.value, context=context)

    dst.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(dst))


def _sample_bg(pix, bbox, scale):
    """Sample background color from 5 points around the bbox edges."""
    points = [
        (bbox.x0 + 2, bbox.y0 - 4),
        ((bbox.x0 + bbox.x1) / 2, bbox.y0 - 4),
        (bbox.x1 - 2, bbox.y0 - 4),
        (bbox.x0 + 2, bbox.y1 + 4),
        ((bbox.x0 + bbox.x1) / 2, bbox.y1 + 4),
    ]
    samples = []
    for px, py in points:
        sx = min(max(int(px * scale), 0), pix.width - 1)
        sy = min(max(int(py * scale), 0), pix.height - 1)
        p = pix.pixel(sx, sy)
        samples.append((p[0], p[1], p[2]))
    r = sum(s[0] for s in samples) / len(samples)
    g = sum(s[1] for s in samples) / len(samples)
    b = sum(s[2] for s in samples) / len(samples)
    return (r / 255, g / 255, b / 255)


def translate_pdf(src: Path, dst: Path, context: str, max_pages: int = None):
    import fitz  # pymupdf

    # Register pymupdf-fonts so "notos" (Noto Sans) is available for full Unicode coverage
    try:
        import fitz.utils
        fitz.Font("notos")  # will raise if not installed — falls back to helv
        _font = "notos"
    except Exception:
        _font = "helv"

    doc = fitz.open(str(src))
    total_pages = len(doc)
    pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
    print(f"  PDF: {total_pages} pages total, translating {pages_to_process} (font: {_font})")

    for page_num in range(pages_to_process):
        page = doc[page_num]
        print(f"  Page {page_num + 1}/{pages_to_process}...")

        # LINE-level extraction: join all spans in a line → one bbox + one text unit
        blocks = page.get_text("dict")["blocks"]
        spans = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_spans = line.get("spans", [])
                if not line_spans:
                    continue
                line_text = "".join(s.get("text", "") for s in line_spans).strip()
                if not line_text:
                    continue
                dominant_size = max(
                    set(s.get("size", 10) for s in line_spans),
                    key=lambda sz: sum(1 for s in line_spans if s.get("size", 10) == sz),
                )
                spans.append({
                    "text": line_text,
                    "bbox": line["bbox"],
                    "size": dominant_size,
                    "color": line_spans[0].get("color", 0),
                })

        if not spans:
            continue

        # One batched API call per page
        numbered = "\n".join(f"[{i+1}] {s['text']}" for i, s in enumerate(spans))
        batch_prompt = (
            f"Translate the Japanese portions of each numbered text segment to English.\n"
            f"Return ONLY the translations, one per line, keeping the same [N] numbering.\n"
            f"Rules:\n"
            f"- Translate ONLY Japanese text. Leave English, numbers, code, and symbols unchanged.\n"
            f"- Preserve all symbols exactly as-is: →, ←, ≦, ≧, ×, ÷, •, ·, °, ±, ©\n"
            f"- Preserve numbers and percentages exactly\n"
            f"- Do NOT add notes, explanations, or parenthetical comments\n"
            f"- Do NOT add any text that wasn't in the original\n"
            f"- Return a clean natural translation only\n\n"
            f"Context: {context} (page {page_num + 1})\n\n"
            f"{numbered}"
        )
        raw = translate(batch_prompt, context="")

        translations = {}
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln.startswith("[") and "]" in ln:
                try:
                    idx = int(ln[1:ln.index("]")])
                    val = ln[ln.index("]") + 1:].strip()
                    translations[idx] = val
                except ValueError:
                    pass

        # Render: redact original text, then insert_htmlbox for full Unicode + auto-scale
        pix = page.get_pixmap(dpi=150)
        scale = pix.width / page.rect.width

        for i, span in enumerate(spans):
            translated = translations.get(i + 1, span["text"])
            bbox = fitz.Rect(span["bbox"])
            font_size = max(span["size"] - 1, 6)

            # Decode original text color from packed int
            color_int = span["color"]
            tr = ((color_int >> 16) & 0xFF) / 255
            tg = ((color_int >> 8) & 0xFF) / 255
            tb = (color_int & 0xFF) / 255
            text_color_hex = "#{:02x}{:02x}{:02x}".format(
                int(tr * 255), int(tg * 255), int(tb * 255)
            )

            bg = _sample_bg(pix, bbox, scale)
            bg_hex = "#{:02x}{:02x}{:02x}".format(
                int(bg[0] * 255), int(bg[1] * 255), int(bg[2] * 255)
            )

            # Redact (erase) original text with background fill
            page.add_redact_annot(bbox, fill=bg)

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # Now insert translated text using insert_htmlbox (auto font + auto scale)
        for i, span in enumerate(spans):
            translated = translations.get(i + 1, span["text"])
            bbox = fitz.Rect(span["bbox"])
            font_size = max(span["size"] - 1, 6)

            color_int = span["color"]
            tr = ((color_int >> 16) & 0xFF) / 255
            tg = ((color_int >> 8) & 0xFF) / 255
            tb = (color_int & 0xFF) / 255
            text_color_hex = "#{:02x}{:02x}{:02x}".format(
                int(tr * 255), int(tg * 255), int(tb * 255)
            )

            html = (
                f'<p style="font-family: sans-serif; font-size: {font_size}pt; '
                f'color: {text_color_hex}; margin: 0; padding: 0;">'
                f'{translated}</p>'
            )
            # scale_low=0.5 allows text to shrink up to 50% before truncating
            # Returns (overflow_lines, scale_used) tuple
            rc = page.insert_htmlbox(bbox, html, scale_low=0.5)
            overflow, scale_used = rc if isinstance(rc, tuple) else (rc, 1.0)
            if overflow > 0 or scale_used < 0.75:
                print(f"    [warn] Page {page_num+1} span {i+1}: overflow={overflow} scale={scale_used:.2f}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()
    doc.ez_save(str(dst))
    doc.close()


# ── Router ─────────────────────────────────────────────────────────────────────

HANDLERS = {
    ".txt": translate_txt,
    ".md":  translate_txt,
    ".csv": translate_csv,
    ".docx": translate_docx,
    ".xlsx": translate_xlsx,
    ".pdf": translate_pdf,
}


def process_file(src: Path, dst: Path, context: str, max_pages: int = None):
    ext = src.suffix.lower()
    handler = HANDLERS.get(ext)
    if handler:
        print(f"  Translating content: {src.name}")
        if ext == ".pdf":
            translate_pdf(src, dst, context, max_pages=max_pages)
        else:
            handler(src, dst, context)
    else:
        # Unsupported format — copy as-is
        print(f"  Copying (unsupported format): {src.name}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


# ── Main pipeline ──────────────────────────────────────────────────────────────

def translate_folder(src_root: Path, dst_root: Path, max_pages: int = None):
    """
    Walk src_root recursively.
    Translate folder names and file names to English.
    Translate file contents for supported formats.
    Write everything to dst_root mirroring the structure.
    """

    # Step 1: Build a translation map for all folder names first
    # This gives us the full English path context before processing files
    print("\n── Phase 1: Translating folder names ──")
    folder_name_map: dict[Path, str] = {}  # original path -> translated name

    for dirpath, dirnames, _ in os.walk(src_root):
        for dirname in dirnames:
            original = Path(dirpath) / dirname
            print(f"  Folder: {dirname}")
            translated = translate_name(dirname, context=f"subfolder of {Path(dirpath).name}")
            folder_name_map[original] = translated
            print(f"    → {translated}")

    # Step 2: Walk and process all files
    print("\n── Phase 2: Translating files ──")

    skipped = []
    errors = []

    for dirpath, dirnames, filenames in os.walk(src_root):
        src_dir = Path(dirpath)

        # Build the translated output path for this directory
        rel_parts = src_dir.relative_to(src_root).parts
        translated_parts = []
        current = src_root
        for part in rel_parts:
            original_sub = current / part
            translated_part = folder_name_map.get(original_sub, part)
            translated_parts.append(translated_part)
            current = original_sub

        dst_dir = dst_root / Path(*translated_parts) if translated_parts else dst_root
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Build context string from the folder path for better translation
        folder_context = " > ".join(translated_parts) if translated_parts else src_root.name

        for filename in filenames:
            src_file = src_dir / filename
            stem = Path(filename).stem
            ext = Path(filename).suffix

            print(f"\nFile: {src_dir.relative_to(src_root) / filename}")

            # Translate file name
            translated_stem = translate_name(stem, context=f"file in folder: {folder_context}")
            translated_filename = translated_stem + ext
            print(f"  Name → {translated_filename}")

            dst_file = dst_dir / translated_filename
            context = f"Document '{translated_filename}' in folder '{folder_context}'"

            try:
                process_file(src_file, dst_file, context, max_pages=max_pages)
            except Exception as e:
                print(f"  ERROR: {e}")
                errors.append((str(src_file), str(e)))
                # Copy original as fallback
                try:
                    shutil.copy2(src_file, dst_dir / filename)
                    print(f"  Fallback: copied original file as {filename}")
                except Exception:
                    pass

    # Summary
    print("\n── Done ──")
    print(f"Output: {dst_root}")
    if errors:
        print(f"\n{len(errors)} file(s) had errors:")
        for path, err in errors:
            print(f"  {path}: {err}")
    else:
        print("All files translated successfully.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python translate.py <input_folder> [--pages N]")
        print()
        print("Output is always created next to the input folder (same parent directory).")
        print("The output folder is named '<input_folder_name>_english'.")
        print()
        print("Examples (source folder name can be in Japanese):")
        print('  Windows:  python translate.py "D:\\Projects\\日本語文書"')
        print('  macOS:    python translate.py "/Users/rayhan/Desktop/日本語文書"')
        print()
        print("Tip: On Windows use  python -X utf8 translate.py ...  for Japanese folder names.")
        sys.exit(1)

    src = Path(os.fsdecode(sys.argv[1].strip('"').strip("'"))).resolve()

    # Output is always a sibling of the input folder, named <folder>_english
    dst = src.parent / (src.name + "_english")

    max_pages = None
    if "--pages" in sys.argv:
        idx = sys.argv.index("--pages")
        max_pages = int(sys.argv[idx + 1])
        print(f"PDF page limit: {max_pages}")

    if not src.exists():
        print(f"Error: input folder not found: {src}")
        sys.exit(1)

    if not src.is_dir():
        print(f"Error: input path is not a folder: {src}")
        sys.exit(1)

    if dst.exists():
        print(f"Warning: output folder already exists: {dst}")
        answer = input("Continue and overwrite? (y/n): ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    dst.mkdir(parents=True, exist_ok=True)

    print(f"Source:  {src}")
    print(f"Output:  {dst}")

    translate_folder(src, dst, max_pages=max_pages)
