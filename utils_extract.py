
# utils_extract.py
# -*- coding: utf-8 -*-
import io, os, re, tempfile
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None
try:
    import docx2txt
except Exception:
    docx2txt = None

def sanitize(text: str) -> str:
    text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()

def read_txt(file: io.BytesIO) -> str:
    try:
        content = file.read().decode("utf-8", errors="ignore")
    except Exception:
        file.seek(0)
        content = file.read().decode("cp949", errors="ignore")
    return sanitize(content)

def extract_text_from_pdf(file: io.BytesIO) -> str:
    if fitz is None:
        return "[PyMuPDF 미설치] pip install pymupdf"
    text_parts = []
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return sanitize("\\n".join(text_parts))

def extract_text_from_docx(file: io.BytesIO) -> str:
    if docx2txt is None:
        return "[docx2txt 미설치] pip install docx2txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(file.read()); path = tmp.name
    try:
        from docx2txt import process
        text = process(path) or ""
    finally:
        try: os.remove(path)
        except Exception: pass
    return sanitize(text)
