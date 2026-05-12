"""
ClawOS X - 文档解析器
支持 PDF, Word, Excel, Markdown, TXT, 图片(OCR)
"""
import os
from pathlib import Path
from typing import Literal

# PDF
import pdfplumber

# Word
from docx import Document as DocxDocument

# Excel
import openpyxl

# PowerPoint
from pptx import Presentation


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


def parse_xlsx(file_path: str) -> tuple[str, list[dict]]:
    """解析 Excel，返回 (纯文本, [Sheet/行信息列表])"""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    full_text = []
    sheet_info = []

    for sheet_idx, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        sheet_lines = []
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            # 跳过空行
            cells = [str(c).strip() if c is not None else "" for c in row]
            line_text = " | ".join(cells)
            if any(cells):
                full_text.append(f"[Sheet:{sheet_name} 行{row_idx}] {line_text}")
                sheet_lines.append({"sheet": sheet_name, "row": row_idx, "text": line_text})
        sheet_info.extend(sheet_lines)

    return "\n".join(full_text), sheet_info


def parse_pptx(file_path: str) -> tuple[str, list[dict]]:
    """解析 PowerPoint，返回 (纯文本, [幻灯片/形状信息列表])"""
    prs = Presentation(file_path)
    full_text = []
    slide_info = []

    for slide_idx, slide in enumerate(prs.slides, 1):
        slide_lines = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                full_text.append(f"[幻灯片{slide_idx}] {shape.text.strip()}")
                slide_lines.append({"slide": slide_idx, "text": shape.text.strip()})
        slide_info.extend(slide_lines)

    return "\n".join(full_text), slide_info


def parse_markdown(file_path: str) -> tuple[str, list[dict]]:
    """解析 Markdown"""
    # 跳过二进制文件（SQLite 数据库、或其他非文本文件）
    with open(file_path, "rb") as f:
        header = f.read(32)
    # SQLite 数据库
    if header[:16] == b'SQLite format 3\x00':
        raise ValueError("skip: file is SQLite database")
    # 包含空字节的二进制文件
    if b'\x00' in header:
        raise ValueError("skip: file is binary")

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


def parse_image(file_path: str) -> tuple[str, list[dict]]:
    """解析图片（营业执照/身份证等），通过 OCR 提取文字"""
    try:
        # 优先用 rapidocr（无需 tesseract，跨平台，中英文都支持）
        try:
            from rapidocr import RapidOCR
            ocr = RapidOCR()
            result = ocr(file_path)
            # RapidOCR 3.7: result 是 RapidOCROutput 对象
            if result and result.txts:
                lines = [t for t in result.txts if t]
                text = "\n".join(lines)
                paragraphs = [{"line": i+1, "text": l} for i, l in enumerate(lines)]
                return text, paragraphs
            return "[OCR 未识别到文字]", []
        except Exception as e:
            pass

        # 降级：pytesseract（需要系统安装 tesseract + 中文语言包）
        try:
            import pytesseract
            from PIL import Image
            image = Image.open(file_path)
            if image.mode != "RGB":
                image = image.convert("RGB")
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            paragraphs = [{"line": i+1, "text": l} for i, l in enumerate(lines)]
            return "\n".join(lines), paragraphs
        except Exception:
            pass

        return "[OCR 识别失败：未找到可用的 OCR 引擎]", []
    except Exception as e:
        return f"[OCR 识别失败: {str(e)}]", []


def parse_file(file_path: str) -> tuple[str, list[dict]]:
    """根据文件类型自动选择解析器"""
    ext = Path(file_path).suffix.lower()

    # 检测 SQLite 数据库（有些文件扩展名是 pdf/docx 但实际是 SQLite）
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if header[:16] == b'SQLite format 3\x00':
            raise ValueError(f"skip: file is SQLite database, not {ext}")
    except (OSError, ValueError):
        pass

    parsers = {
        ".pdf": parse_pdf,
        ".docx": parse_docx,
        ".xlsx": parse_xlsx,
        ".xls": parse_xlsx,
        ".pptx": parse_pptx,
        ".md": parse_markdown,
        ".txt": parse_txt,
        ".jpg": parse_image,
        ".jpeg": parse_image,
        ".png": parse_image,
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
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".pptx": "pptx",
        ".md": "md",
        ".txt": "txt",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
    }.get(ext, "unknown")
