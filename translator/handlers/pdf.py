from pathlib import Path

from ..common import has_japanese, batch_translate


def _sample_bg(pix, bbox, scale):
    # sample pixels just outside the text bounding box to guess the background color
    points = [
        (bbox.x0 + 2,                   bbox.y0 - 4),
        ((bbox.x0 + bbox.x1) / 2,       bbox.y0 - 4),
        (bbox.x1 - 2,                   bbox.y0 - 4),
        (bbox.x0 + 2,                   bbox.y1 + 4),
        ((bbox.x0 + bbox.x1) / 2,       bbox.y1 + 4),
    ]
    samples = []
    for px, py in points:
        sx = min(max(int(px * scale), 0), pix.width  - 1)
        sy = min(max(int(py * scale), 0), pix.height - 1)
        p  = pix.pixel(sx, sy)
        samples.append((p[0], p[1], p[2]))
    r = sum(s[0] for s in samples) / len(samples)
    g = sum(s[1] for s in samples) / len(samples)
    b = sum(s[2] for s in samples) / len(samples)
    return (r / 255, g / 255, b / 255)


def translate_pdf(src: Path, dst: Path, context: str, max_pages: int = None):
    import fitz

    try:
        fitz.Font("notos")
        _font = "notos"
    except Exception:
        _font = "helv"

    doc              = fitz.open(str(src))
    total_pages      = len(doc)
    pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
    print(f"  PDF: {total_pages} pages total, translating {pages_to_process} (font: {_font})")

    for page_num in range(pages_to_process):
        page   = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        spans  = []

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
                    "text":  line_text,
                    "bbox":  line["bbox"],
                    "size":  dominant_size,
                    "color": line_spans[0].get("color", 0),
                })

        if not spans:
            continue

        print(f"  Page {page_num + 1}/{pages_to_process}...")

        # collect JP texts for this page and batch translate
        jp_texts = [s["text"] for s in spans if has_japanese(s["text"])]
        tmap = batch_translate(jp_texts, f"{context} (page {page_num + 1})") if jp_texts else {}

        pix   = page.get_pixmap(dpi=150)
        scale = pix.width / page.rect.width

        # redact original text
        for span in spans:
            bg = _sample_bg(pix, fitz.Rect(span["bbox"]), scale)
            page.add_redact_annot(fitz.Rect(span["bbox"]), fill=bg)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # insert translated text
        for span_idx, span in enumerate(spans):
            translated = tmap.get(span["text"], span["text"])
            bbox       = fitz.Rect(span["bbox"])
            font_size  = max(span["size"] - 1, 6)
            color_int  = span["color"]
            text_color = "#{:02x}{:02x}{:02x}".format(
                (color_int >> 16) & 0xFF,
                (color_int >>  8) & 0xFF,
                 color_int        & 0xFF,
            )
            html = (
                f'<p style="font-family: sans-serif; font-size: {font_size}pt; '
                f'color: {text_color}; margin: 0; padding: 0;">{translated}</p>'
            )
            rc             = page.insert_htmlbox(bbox, html, scale_low=0.5)
            overflow, scale_used = rc if isinstance(rc, tuple) else (rc, 1.0)
            if overflow > 0 or scale_used < 0.75:
                print(f"    [warn] Page {page_num+1} span {span_idx+1}: overflow={overflow} scale={scale_used:.2f}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()
    doc.ez_save(str(dst))
    doc.close()
