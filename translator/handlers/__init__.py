from .txt  import translate_txt, translate_csv
from .docx import translate_docx
from .xlsx import translate_xlsx
from .pdf  import translate_pdf

# maps file extension to its handler function — add new formats here
HANDLERS = {
    ".txt":  translate_txt,
    ".md":   translate_txt,  
    ".csv":  translate_csv,
    ".docx": translate_docx,
    ".xlsx": translate_xlsx,
    ".pdf":  translate_pdf,
}
