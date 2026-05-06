"""
ClawOS X - 文档解析器
支持 PDF, Word, Markdown, TXT
"""
import os
from pathlib import Path
from typing import Literal

# PDF
import pdfplumber

# Word
from docx import Document as DocxDocument


def parse_pdf(file_path: str) -> tuple[str, list[dict]]:
    """解析 PDF，返回 (纯文本, [页面文本列表])"""
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n\n".join(pages), [{"page": i+1, "text": t} for i, t in enumerate(pages)]


def parse_docx(file_path: str) -> tuple[str, list[dict]]:
    """解析 Word，返回 (纯文本, [段落列表])"""
    doc = DocxDocument(file_path)
    paragraphs = []
    full_text = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if text:
            full_text.append(text)
            paragraphs.append({"para_index": i, "text": text})

    # 提取表格
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                full_text.append(f"[表格] {row_text}")

    return "\n".join(full_text), paragraphs


def parse_markdown(file_path: str) -> tuple[str, list[dict]]:
    """解析 Markdown"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    paragraphs = [{"line": i+1, "text": line} for i, line in enumerate(lines) if line.strip()]
    return content, paragraphs


def parse_txt(file_path: str) -> tuple[str, list[dict]]:
    """解析 TXT"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    paragraphs = [{"line": i+1, "text": line} for i, line in enumerate(lines) if line.strip()]
    return content, paragraphs


def parse_file(file_path: str) -> tuple[str, list[dict]]:
    """根据文件类型自动选择解析器"""
    ext = Path(file_path).suffix.lower()

    parsers = {
        ".pdf": parse_pdf,
        ".docx": parse_docx,
        ".md": parse_markdown,
        ".txt": parse_txt,
    }

    parser = parsers.get(ext)
    if not parser:
        raise ValueError(f"不支持的文件类型: {ext}")

    return parser(file_path)


def get_file_type(filename: str) -> str:
    """从文件名返回文件类型"""
    ext = Path(filename).suffix.lower()
    return {
        ".pdf": "pdf",
        ".docx": "docx",
        ".md": "md",
        ".txt": "txt",
    }.get(ext, "unknown")
