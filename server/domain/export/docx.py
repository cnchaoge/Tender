"""Word 排版。封面公司名在函数内读取当前设置，不在导入时绑定。

阶段 5 才会把导出时的 COMPANY_NAME 抄进版本。这里仍每次导出读取当时的设置，
与拆分前 `_docx_from_markdown` 一致。
"""
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from server.config import GENERATED_DIR

def _set_run_font(run, font_name="宋体", size_pt=None, bold=False, color=None):
    """设置 run 字体属性"""
    run.font.name = font_name
    rpr = run._element.get_or_add_rPr()
    rFonts = rpr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), font_name)
    if size_pt:
        run.font.size = Pt(size_pt)
    if bold:
        run.font.bold = True
    if color:
        run.font.color.rgb = color


def _setup_styles(doc):
    """配置文档默认样式"""
    style = doc.styles['Normal']
    style.font.name = '宋体'
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    pf = style.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    for level, (size, bold) in {1: (22, True), 2: (16, True), 3: (14, True)}.items():
        hs = doc.styles[f'Heading {level}']
        hs.font.name = '黑体'
        hs.font.size = Pt(size)
        hs.font.bold = bold
        hs.font.color.rgb = RGBColor(0, 0, 0)
        hs.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        hs.paragraph_format.space_before = Pt(12)
        hs.paragraph_format.space_after = Pt(6)


def _add_cover_page(doc, title, company_name, date_str):
    """生成专业封面页（独立节，不显示页眉页脚）"""
    section = doc.sections[0]
    section.top_margin = Cm(3.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("投 标 文 件")
    _set_run_font(r, font_name="黑体", size_pt=26, bold=True)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("━" * 30)
    _set_run_font(r, color=RGBColor(0x99, 0x99, 0x99))
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("项目名称：")
    _set_run_font(r, size_pt=16)
    r2 = p.add_run(title)
    _set_run_font(r2, font_name="黑体", size_pt=16, bold=True)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("投标单位：")
    _set_run_font(r, size_pt=14)
    r2 = p.add_run(company_name)
    _set_run_font(r2, size_pt=14, bold=True)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(date_str)
    _set_run_font(r, size_pt=14)
    # 封面后的分节符
    doc.add_section()
    new_section = doc.sections[-1]
    new_section.top_margin = Cm(2.5)
    new_section.bottom_margin = Cm(2.5)
    new_section.left_margin = Cm(2.5)
    new_section.right_margin = Cm(2.5)
    new_section.header.is_linked_to_previous = False
    new_section.footer.is_linked_to_previous = False


def _add_toc(doc):
    """插入目录页（TOC 域代码）"""
    p = doc.add_paragraph()
    r = p.add_run("目  录")
    _set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    para = doc.add_paragraph()
    run1 = para.add_run()
    fld_char_begin = OxmlElement('w:fldChar')
    fld_char_begin.set(qn('w:fldCharType'), 'begin')
    run1._element.append(fld_char_begin)
    run2 = para.add_run()
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    run2._element.append(instr)
    run3 = para.add_run()
    fld_char_sep = OxmlElement('w:fldChar')
    fld_char_sep.set(qn('w:fldCharType'), 'separate')
    run3._element.append(fld_char_sep)
    run4 = para.add_run("（目录，请在 Word 中按 Ctrl+A → F9 刷新）")
    _set_run_font(run4, size_pt=12, color=RGBColor(0x99, 0x99, 0x99))
    run5 = para.add_run()
    fld_char_end = OxmlElement('w:fldChar')
    fld_char_end.set(qn('w:fldCharType'), 'end')
    run5._element.append(fld_char_end)
    doc.add_page_break()


def _setup_header_footer(doc, title):
    """设置正文节的页眉页脚"""
    section = doc.sections[-1]
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = hp.add_run(title)
    _set_run_font(r, size_pt=9, color=RGBColor(0x66, 0x66, 0x66))
    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = fp.add_run("第 ")
    _set_run_font(r1, size_pt=9, color=RGBColor(0x66, 0x66, 0x66))
    run_page = fp.add_run()
    fld_begin = OxmlElement('w:fldChar')
    fld_begin.set(qn('w:fldCharType'), 'begin')
    run_page._element.append(fld_begin)
    instr_page = OxmlElement('w:instrText')
    instr_page.set(qn('xml:space'), 'preserve')
    instr_page.text = ' PAGE '
    run_page._element.append(instr_page)
    fld_sep = OxmlElement('w:fldChar')
    fld_sep.set(qn('w:fldCharType'), 'separate')
    run_page._element.append(fld_sep)
    fld_end = OxmlElement('w:fldChar')
    fld_end.set(qn('w:fldCharType'), 'end')
    run_page._element.append(fld_end)
    r2 = fp.add_run(" 页 / 共 ")
    _set_run_font(r2, size_pt=9, color=RGBColor(0x66, 0x66, 0x66))
    run_total = fp.add_run()
    fld_begin2 = OxmlElement('w:fldChar')
    fld_begin2.set(qn('w:fldCharType'), 'begin')
    run_total._element.append(fld_begin2)
    instr_total = OxmlElement('w:instrText')
    instr_total.set(qn('xml:space'), 'preserve')
    instr_total.text = ' NUMPAGES '
    run_total._element.append(instr_total)
    fld_sep2 = OxmlElement('w:fldChar')
    fld_sep2.set(qn('w:fldCharType'), 'separate')
    run_total._element.append(fld_sep2)
    fld_end2 = OxmlElement('w:fldChar')
    fld_end2.set(qn('w:fldCharType'), 'end')
    run_total._element.append(fld_end2)
    r3 = fp.add_run(" 页")
    _set_run_font(r3, size_pt=9, color=RGBColor(0x66, 0x66, 0x66))


def _resolve_image_path(img_path: str) -> Optional[Path]:
    """解析 markdown 图片路径为实际文件路径"""
    from server.config import BASE_DIR, UPLOADS_DIR
    p = Path(img_path)
    if p.is_absolute() and p.exists():
        return p
    candidates = [
        BASE_DIR / p,
        UPLOADS_DIR / p.name,
        Path.cwd() / p,
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _render_markdown_to_docx(doc: DocxDocument, content: str):
    """将 markdown 内容渲染到 docx 文档（支持表格/标题/列表/段落/图片）"""
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].rstrip("\r").strip()

        # 空行
        if not line:
            i += 1
            continue

        # 标题
        if line.startswith("#"):
            m = re.match(r"^(#{1,4})\s+(.*)$", line)
            if m:
                level = len(m.group(1))
                heading = doc.add_heading(m.group(2), level=min(level, 3))
                heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
                for run in heading.runs:
                    _set_run_font(run, font_name="黑体")
                i += 1
                continue

        # 图片 ![alt](path)
        img_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line)
        if img_match:
            img_path = img_match.group(2).strip()
            abs_path = _resolve_image_path(img_path)
            if abs_path and abs_path.exists():
                try:
                    para = doc.add_paragraph()
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = para.add_run()
                    run.add_picture(str(abs_path), width=Inches(5.5))
                except Exception:
                    p = doc.add_paragraph()
                    r = p.add_run(f"[图片：{img_match.group(1)}]")
                    _set_run_font(r, color=RGBColor(0x99, 0x99, 0x99))
            else:
                p = doc.add_paragraph()
                r = p.add_run(f"[图片：{img_match.group(1)}]")
                _set_run_font(r, color=RGBColor(0x99, 0x99, 0x99))
            i += 1
            continue

        # 表格
        if "|" in line:
            rows = []
            while i < len(lines):
                stripped = lines[i].rstrip("\r").strip()
                if "|" not in stripped:
                    break
                # 跳过 markdown 表格分隔行（如 |---|---|）
                if re.match(r"^\|?[\s\-:]+\|", stripped):
                    i += 1
                    continue
                cells = [c.strip() for c in stripped.split("|") if c.strip() is not None]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)
                i += 1
            if rows and len(rows) >= 2:
                tbl = doc.add_table(rows=len(rows), cols=len(rows[0]))
                tbl.style = "Table Grid"
                for ri, row_data in enumerate(rows):
                    for ci, cell_text in enumerate(row_data):
                        cell = tbl.rows[ri].cells[ci]
                        cell.text = cell_text
                        for p in cell.paragraphs:
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            for run in p.runs:
                                _set_run_font(run, size_pt=10)
                    # 表头样式：加粗 + 灰底
                    if ri == 0:
                        for cell in tbl.rows[0].cells:
                            for p in cell.paragraphs:
                                for run in p.runs:
                                    run.font.bold = True
                            shading = OxmlElement('w:shd')
                            shading.set(qn('w:fill'), 'D9E2F3')
                            shading.set(qn('w:val'), 'clear')
                            cell._tc.get_or_add_tcPr().append(shading)
            continue

        # 列表
        if re.match(r"^[-*]\s", line) or re.match(r"^\d+\.\s", line):
            while i < len(lines):
                stripped = lines[i].rstrip("\r").strip()
                m_unordered = re.match(r"^[-*]\s+(.*)$", stripped)
                m_ordered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
                if m_unordered:
                    para = doc.add_paragraph(style="List Bullet")
                    run = para.add_run(m_unordered.group(1))
                    _set_run_font(run)
                    i += 1
                elif m_ordered:
                    para = doc.add_paragraph(style="List Number")
                    run = para.add_run(m_ordered.group(2))
                    _set_run_font(run)
                    i += 1
                else:
                    break
            continue

        # 段落：合并连续的非特殊行
        para_lines = []
        while i < len(lines):
            stripped = lines[i].rstrip("\r").strip()
            if (not stripped
                or stripped.startswith("#")
                or stripped.startswith("-")
                or stripped.startswith("*")
                or re.match(r"^\d+\.\s", stripped)
                or ("|" in stripped and re.match(r"^\|?", stripped))):
                break
            para_lines.append(stripped)
            i += 1
        if para_lines:
            text = " ".join(para_lines)
            para = doc.add_paragraph(text)
            for run in para.runs:
                _set_run_font(run)
            continue

        i += 1


def _docx_from_markdown(content: str, title: str = "投标标书") -> DocxDocument:
    """将 markdown 字符串转为专业排版的 docx Document 对象"""
    from server.config import get_settings as _get_settings
    _settings = _get_settings()
    company_name = _settings.COMPANY_NAME or "投标单位名称"
    date_str = datetime.now().strftime("%Y 年 %m 月 %d 日")
    doc = DocxDocument()
    _setup_styles(doc)
    _add_cover_page(doc, title, company_name, date_str)
    _add_toc(doc)
    _setup_header_footer(doc, title)
    _render_markdown_to_docx(doc, content)
    return doc


def _write_bid_docx(content: str, title: str) -> Path:
    """两条生成接口共用的 Word 落盘。"""
    doc = _docx_from_markdown(content, title)
    output_path = GENERATED_DIR / f"bid_{uuid.uuid4().hex[:8]}.docx"
    doc.save(str(output_path))
    return output_path
