from pathlib import Path
from ..client import translate


def translate_docx(src: Path, dst: Path, context: str):
    from docx import Document

    doc = Document(str(src))

    for para in doc.paragraphs:
        if para.text.strip():
            translated = translate(para.text, context=context)
            if para.runs:
                para.runs[0].text = translated
                for run in para.runs[1:]:
                    run.text = ""

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        translated = translate(para.text, context=context)
                        if para.runs:
                            para.runs[0].text = translated
                            for run in para.runs[1:]:
                                run.text = ""

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))
