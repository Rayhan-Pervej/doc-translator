from pathlib import Path
from charset_normalizer import from_path
import csv

from ..common import has_japanese, batch_translate


def translate_txt(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding  = detection.encoding if detection else "utf-8"
    text      = src.read_text(encoding=encoding, errors="replace")

    # split into lines, batch translate JP lines, rejoin preserving original line endings
    lines    = text.splitlines(keepends=True)
    jp_lines = [l.rstrip("\r\n") for l in lines if l.strip() and has_japanese(l)]
    tmap     = batch_translate(jp_lines, context) if jp_lines else {}

    translated_lines = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        ending   = line[len(stripped):]
        if stripped.strip() and has_japanese(stripped) and stripped in tmap:
            translated_lines.append(tmap[stripped] + ending)
        else:
            translated_lines.append(line)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(translated_lines), encoding="utf-8")


def translate_csv(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding  = detection.encoding if detection else "utf-8"

    with open(src, encoding=encoding, errors="replace", newline="") as f:
        rows = list(csv.reader(f))

    # collect all unique JP cells and batch translate
    texts = [cell for row in rows for cell in row if cell.strip() and has_japanese(cell)]
    tmap  = batch_translate(texts, context) if texts else {}

    translated_rows = []
    for row in rows:
        translated_rows.append([
            tmap.get(cell, cell) if cell.strip() and has_japanese(cell) else cell
            for cell in row
        ])

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(translated_rows)
