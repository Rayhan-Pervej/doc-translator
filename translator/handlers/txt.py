from pathlib import Path
from charset_normalizer import from_path
import csv

from ..client import translate


def translate_txt(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding  = detection.encoding if detection else "utf-8"
    text      = src.read_text(encoding=encoding, errors="replace")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translate(text, context=context), encoding="utf-8")


def translate_csv(src: Path, dst: Path, context: str):
    detection = from_path(src).best()
    encoding  = detection.encoding if detection else "utf-8"

    with open(src, encoding=encoding, errors="replace", newline="") as f:
        rows = list(csv.reader(f))

    translated_rows = []
    for row in rows:
        translated_rows.append([
            translate(cell, context=context) if cell.strip() else cell
            for cell in row
        ])

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(translated_rows)
