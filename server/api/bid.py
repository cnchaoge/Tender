"""
ClawOS X - 标书生成 API
"""
import re
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
from docx import Document as DocxDocument
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn


def _set_run_font(run):
    """设置 run 为宋体"""
    run.font.name = "宋体"
    rpr = run._element.get_or_add_rPr()
    rFonts = rpr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "宋体")


def _render_markdown_to_docx(doc: DocxDocument, content: str):
    """将 markdown 内容渲染到 docx 文档（支持表格/标题/列表/段落）"""
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
                    _set_run_font(run)
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
                cells = [c for c in cells if c]  # 过滤空单元格
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
                            for run in p.runs:
                                _set_run_font(run)
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
    """将 markdown 字符串转为 docx Document 对象"""
    doc = DocxDocument()
    doc.add_heading(title, 0)
    _render_markdown_to_docx(doc, content)
    return doc

from server.config import GENERATED_DIR, get_settings
from server.db.sqlite import get_db
from server.core.retriever.retriever import retrieve
from server.core.generator.llm import get_generator
from server.core.reviewer import review_bid
from server.tools.violation_checker import get_violation_checker
from server.tools.plagiarism_checker import get_plagiarism_checker
from server.models import BidParseReq, BidParseResp, BidGenerateReq, BidMatchCheckReq, BidPlanReq, BidPlanResp, Resp

router = APIRouter(prefix="/api/bid", tags=["标书生成"])
settings = get_settings()

SYSTEM_PROMPT = """你是一个专业的招投标文档专家，擅长分析招标文件并生成投标标书。"""

 
def _json_clean(raw: str) -> str:
    """去掉 markdown json 包装（```json ... ```）"""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        # 去掉第一行 ```json 或 ``` 等标记
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉最后一行 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw.strip()


def _validate_and_fill(result: dict, raw_text: str) -> dict:
    """校验关键字段，缺失时从 raw_text 正则降级提取，注入 warnings"""
    warnings = []

    # project_name：缺失时从 raw_text 前200字尝试提取
    if not result.get("project_name") or result["project_name"] == "解析失败":
        m = re.search(r"项目名称[：:]\s*(.+?)(?:\n|$)", raw_text)
        if m:
            result["project_name"] = m.group(1).strip()
            warnings.append("project_name 从原文正则提取")
        else:
            result["project_name"] = "未识别到项目名称"

    # deadline：缺失时尝试正则
    if not result.get("deadline"):
        patterns = [
            r"工期[：:]\s*(.+?)(?:\n|$)",
            r"交付时间[：:]\s*(.+?)(?:\n|$)",
            r"计划.*?(\d+年\d+月|\d+月\d+日|\d+日)",
        ]
        for pat in patterns:
            m = re.search(pat, raw_text)
            if m:
                result["deadline"] = m.group(1).strip()
                warnings.append("deadline 从原文正则提取")
                break
        if not result.get("deadline"):
            result["deadline"] = ""

    # requirements：确保是列表
    if not isinstance(result.get("requirements"), list):
        result["requirements"] = []
    if not result["requirements"]:
        result["requirements"] = ["未识别到资格要求"]

    # qualification：确保是列表
    if not isinstance(result.get("qualification"), list):
        result["qualification"] = []
    if not result["qualification"]:
        result["qualification"] = ["未识别到资质要求"]

    # scoring：新 dict 结构
    if not isinstance(result.get("scoring"), dict):
        result["scoring"] = {}
    # 如果 LLM 仍返回旧列表结构（向后兼容），包装成新结构
    if "sections" not in result["scoring"] and isinstance(result.get("_raw_scoring_list"), list):
        result["scoring"] = {
            "method": "综合评分法",
            "total_score": 100,
            "sections": [{"name": "评分项", "weight": 100, "items": result.get("_raw_scoring_list", [])}],
            "disqualify_conditions": [],
            "price_method": "average",
        }

    # 计算置信度
    scoring_ok = isinstance(result.get("scoring"), dict) and bool(result["scoring"].get("sections"))
    field_ok = (
        result.get("project_name")
        and result["project_name"] not in ("未识别到项目名称", "解析失败")
        and isinstance(result["requirements"], list)
        and bool(result["requirements"])  # requirements 非空才算成功
        and isinstance(result["qualification"], list)
        and scoring_ok
    )
    if field_ok and not warnings:
        confidence = 0.95
    elif warnings and len(warnings) <= 2:
        confidence = 0.6
    elif warnings:
        confidence = 0.3
    else:
        confidence = 0.5

    result["parse_meta"] = {
        "confidence": confidence,
        "warnings": warnings,
        "health_check": {},  # 由 parse_bid_file 注入
    }
    return result


def _health_check(text: str, file_path: str) -> dict:
    """招标文件体检：轻量版"""
    import os
    checks = []

    # 1. 文件可读性：文字量检测
    char_count = len(text.strip())
    if char_count < 200:
        checks.append({"item": "文件可读性", "result": "fail", "detail": "文字量极少（< 200字），可能为扫描件或图片型PDF，建议使用文字版文件"})
    elif char_count < 500:
        checks.append({"item": "文件可读性", "result": "warning", "detail": f"文字量偏少（{char_count}字），可能是扫描件，建议核实"})
    else:
        checks.append({"item": "文件可读性", "result": "pass", "detail": f"文字量正常（{char_count}字）"})

    # 2. 关键章节检测（正则）
    chapter_keywords = ["招标公告", "投标人须知", "技术标准", "评分办法", "合同条款"]
    found = [kw for kw in chapter_keywords if kw in text]
    missing = [kw for kw in chapter_keywords if kw not in text]
    if missing:
        checks.append({"item": "关键章节", "result": "warning", "detail": f"缺少章节：{'、'.join(missing)}"})
    else:
        checks.append({"item": "关键章节", "result": "pass", "detail": "主要章节齐全"})

    # 3. 关键字段存在性检测
    deadline_found = bool(re.search(r"工期|交付时间|计划.*?\d+月", text))
    project_found = bool(re.search(r"项目名称|项目名称[：:]", text))
    scoring_found = bool(re.search(r"评分|评标|得分", text))

    if not project_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到项目名称相关内容"})
    if not deadline_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到工期/交付时间"})
    if not scoring_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到评分标准相关内容"})
    if project_found and deadline_found and scoring_found:
        checks.append({"item": "关键字段", "result": "pass", "detail": "关键字段均已识别"})

    # 整体状态
    fail_count = sum(1 for c in checks if c["result"] == "fail")
    warn_count = sum(1 for c in checks if c["result"] == "warning")
    if fail_count > 0:
        status = "fail"
    elif warn_count >= 2:
        status = "warning"
    elif warn_count == 1:
        status = "warning"
    else:
        status = "pass"

    return {"status": status, "checks": checks}


@router.post("/parse", response_model=BidParseResp)
def parse_bid_file(req: BidParseReq):
    """解析招标文件，提取关键信息"""
    import os
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    from server.core.parser.document import parse_file
    text, _ = parse_file(req.file_path)

    # 招标文件体检（轻量版）
    health = _health_check(text, req.file_path)

    generator = get_generator()
    prompt = f"""请从以下招标文件中提取关键信息，以JSON格式返回：

招标文件内容：
{text[:8000]}

请提取并返回以下JSON格式（只返回JSON，不要其他内容）：
{{
    "project_name": "项目名称",
    "deadline": "工期/交付时间",
    "requirements": ["资格要求1", "资格要求2"],
    "qualification": ["资质要求1", "资质要求2"],
    "scoring": {{
        "method": "综合评分法|最低价法|经评审的最低价法|性价比法",
        "total_score": 100,
        "sections": [
            {{
                "name": "技术标",
                "weight": 60,
                "items": [
                    {{
                        "name": "评分项名称",
                        "score": 20,
                        "max_score": 20,
                        "type": "expert|formula|qualified",
                        "formula": "(最低报价/投标报价)*20  # type=formula 时填写",
                        "bidirectional": false,
                        "disqualify_if_fail": false,
                        "requirements": ["评委逐项打分"]
                    }}
                ]
            }}
        ],
        "disqualify_conditions": ["资格条件不满足则废标", "工期承诺偏离则废标"],
        "price_method": "lowest|average|formula"
    }}
}}"""

    try:
        raw_llm = generator.generate(prompt, system="你是一个招投标专家，擅长提取招标文件关键信息。")
        import json
        cleaned = _json_clean(raw_llm)
        result = json.loads(cleaned)

        # 字段校验 + 降级提取
        result = _validate_and_fill(result, text[:2000])
        # 注入体检结果
        result["parse_meta"]["health_check"] = health

        # RAG 素材预关联：用 project_name + requirements[0] 检索相关素材
        recommended_materials = []
        project_name = result.get("project_name", "")
        requirements = result.get("requirements", [])
        req0 = requirements[0] if requirements else ""

        if project_name and req0:
            query = f"{project_name} {req0}"
            chunks = retrieve(query, top_k=3)
            doc_ids_seen = set()
            for chunk in chunks:
                doc_id = chunk.get("doc_id")
                if doc_id and doc_id not in doc_ids_seen:
                    doc_ids_seen.add(doc_id)
                    recommended_materials.append({
                        "id": doc_id,
                        "filename": chunk.get("filename", ""),
                        "relevance_score": round(chunk.get("score", 0.0), 2)
                    })

        return BidParseResp(
            raw_text=text[:2000],
            recommended_materials=recommended_materials,
            **{k: v for k, v in result.items()}
        )
    except json.JSONDecodeError as e:
        # JSON 解析失败，尝试正则降级
        result = {
            "project_name": "未识别到项目名称",
            "deadline": "",
            "requirements": ["解析失败，请检查文件格式"],
            "qualification": [],
            "scoring": [],
        }
        result = _validate_and_fill(result, text[:2000])
        result["parse_meta"]["health_check"] = health
        return BidParseResp(raw_text=text[:2000], parse_meta=result["parse_meta"], **{k: v for k, v in result.items() if k != "parse_meta"})
    except Exception as e:
        return BidParseResp(
            project_name="解析失败",
            deadline="",
            requirements=[f"解析错误: {str(e)}"],
            qualification=[],
            scoring={},
            raw_text=text[:2000],
            parse_meta={"confidence": 0, "warnings": [str(e)], "health_check": health},
        )


def _format_scoring(scoring: dict) -> str:
    """把 scoring dict 格式化为 prompt 友好文本"""
    if not scoring:
        return "未提供评分标准"
    method = scoring.get("method", "未知")
    sections = scoring.get("sections", [])
    disqualify = scoring.get("disqualify_conditions", [])

    lines = [f"评标办法：{method}"]
    for section in sections:
        lines.append(f"  {section.get('name', '评分项')}（权重{section.get('weight', 0)}%）：")
        for item in section.get("items", []):
            item_name = item.get("name", "")
            score = item.get("score", 0)
            max_score = item.get("max_score", 0)
            item_type = item.get("type", "expert")
            formula = item.get("formula", "")
            disqualify_if_fail = item.get("disqualify_if_fail", False)
            item_req = "；".join(item.get("requirements", []))

            type_desc = {"expert": "专家打分", "formula": "公式计算", "qualified": "满足即得分"}.get(item_type, item_type)
            disqualify_str = "（不满足则废标）" if disqualify_if_fail else ""
            formula_str = f"，公式：{formula}" if formula else ""
            req_str = f"，{item_req}" if item_req else ""

            lines.append(f"    - {item_name}：{score}/{max_score}分，{type_desc}{formula_str}{disqualify_str}{req_str}")

    if disqualify:
        lines.append(f"  废标条件：{'；'.join(disqualify)}")

    return "\n".join(lines)


@router.post("/plan", response_model=BidPlanResp)
def plan_bid(req: BidPlanReq):
    """生成标书目录大纲（规划阶段）"""
    generator = get_generator()

    # 检索相关素材摘要
    materials_text = ""
    if req.materials:
        conn = get_db()
        for doc_id in req.materials:
            cur = conn.cursor()
            cur.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if row:
                chunks = retrieve(
                    f"招标文件：{req.parse_result.get('project_name', '')} {req.parse_result.get('deadline', '')}",
                    top_k=2, doc_ids=[doc_id]
                )
                for chunk in chunks:
                    materials_text += f"[{row['filename']}]\n{chunk['text'][:500]}\n\n"
        conn.close()

    scoring_text = _format_scoring(req.parse_result.get("scoring", {}))

    prompt = f"""你是一个专业的招投标文档专家。根据以下招标文件要求，规划投标标书的章节结构。

招标文件信息：
- 项目名称：{req.parse_result.get('project_name', '未知')}
- 工期：{req.parse_result.get('deadline', '未知')}
- 资格要求：{', '.join(req.parse_result.get('requirements', [])) or '未知'}
- 资质要求：{', '.join(req.parse_result.get('qualification', [])) or '未知'}
- 评分标准：
{scoring_text}

可用素材摘要：
{materials_text[:2000] if materials_text else '无'}

请规划投标标书的章节结构，以JSON格式返回：
{{
    "chapters": [
        {{"name": "第一章 投标函", "description": "投标函正文，包含投标报价、工期承诺等"}},
        {{"name": "第二章 资格审查文件", "description": "企业资质、业绩证明等"}},
        ...
    ]
}}

要求：
1. 章节要覆盖招标文件所有资格要求和资质要求
2. 章节顺序要符合投标标书惯例（投标函 → 资格审查 → 技术标 → 商务标）
3. 每个章节给一句简短描述，说明该章节包含什么内容
4. 只返回JSON，不要其他内容"""

    try:
        raw_llm = generator.generate(prompt, system="你是一个招投标专家，擅长规划投标标书结构。")
        import json
        cleaned = _json_clean(raw_llm)
        result = json.loads(cleaned)
        chapters = result.get("chapters", [])
        if not chapters:
            raise ValueError("LLM 返回的章节列表为空")
        return BidPlanResp(chapters=chapters)
    except Exception as e:
        # 失败时返回默认结构
        return BidPlanResp(chapters=[
            {"name": "第一章 投标函", "description": "投标函正文，包含投标报价、工期承诺等"},
            {"name": "第二章 资格审查文件", "description": "企业资质证明、业绩材料等"},
            {"name": "第三章 技术标", "description": "施工方案、技术路线、进度计划等"},
            {"name": "第四章 商务标", "description": "报价明细表、投标保证金等"},
        ])


@router.post("/generate", response_model=dict)
def generate_bid(req: BidGenerateReq):
    """根据招标文件生成标书（带 AI 质检，非流式）"""
    generator = get_generator()

    # 检索相关素材
    materials_text = ""
    if req.materials:
        conn = get_db()
        cur = conn.cursor()
        for doc_id in req.materials:
            cur.execute("SELECT filename, id FROM documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if row:
                # 注意：parse_result 是 dict，直接 stringify 传入 retrieve
                query_for_retrieve = f"招标文件：{req.parse_result.get('project_name', '')} {req.parse_result.get('deadline', '')}"
                chunks = retrieve(query_for_retrieve, top_k=3, doc_ids=[doc_id])
                for chunk in chunks:
                    materials_text += f"[{row['filename']}]\n{chunk['text']}\n\n"
        conn.close()

    # 检查是否需要 raw_text 降级
    raw_text = req.parse_result.get("raw_text", "")
    project_name = req.parse_result.get("project_name", "")
    confidence = req.parse_result.get("parse_meta", {}).get("confidence", 1.0)
    use_raw_fallback = (
        "未识别" in project_name
        or "解析失败" in project_name
        or confidence < 0.5
    )

    bid_info = f"""招标文件：
- 项目名称：{project_name}
- 工期：{req.parse_result.get("deadline", "")}
- 资格要求：{", ".join(req.parse_result.get("requirements", []))}
- 资质要求：{", ".join(req.parse_result.get("qualification", []))}
- {_format_scoring(req.parse_result.get("scoring", {}))}"""

    # 降级：confidence 低于阈值时，把 raw_text 直接附在后面让 LLM 再读
    if use_raw_fallback and raw_text:
        bid_info += f"\n\n【原文内容】（解析结果不可信，请直接阅读原文提取关键信息）：\n{raw_text[:3000]}"

    prompt = f"""根据以下招标文件要求和素材，生成一份投标标书。

{bid_info}

可用素材：
{materials_text[:5000] if materials_text else "无"}

请生成完整的投标标书，包含：
1. 投标函
2. 资格审查文件
3. 技术标
4. 商务标

输出格式：Markdown"""

    # 第一轮生成
    content = generator.generate(prompt, system=SYSTEM_PROMPT)

    # AI 质检
    review = review_bid(content, req.parse_result)

    # 质检未通过，根据建议重新生成一轮
    if not review["passed"]:
        review_note = "\n\n[审核意见] " + "；".join(review.get("suggestions", []))
        retry_prompt = prompt + review_note
        content = generator.generate(retry_prompt, system=SYSTEM_PROMPT)

    # 转为 Word
    doc = _docx_from_markdown(content, req.parse_result.get("project_name", "投标标书"))

    output_path = GENERATED_DIR / f"bid_{uuid.uuid4().hex[:8]}.docx"
    doc.save(str(output_path))

    return {
        "file_path": str(output_path),
        "filename": output_path.name,
        "review": {
            "passed": review["passed"],
            "score": review.get("score", 0),
            "issues": review.get("issues", []),
        }
    }


def _sse_event(data: dict, event: str = "message") -> bytes:
    import json
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


@router.post("/generate/stream")
async def generate_bid_stream(req: BidGenerateReq):
    """SSE 流式生成标书，逐步推送进度"""
    generator = get_generator()

    # 检索相关素材
    materials_text = ""
    if req.materials:
        conn = get_db()
        cur = conn.cursor()
        for doc_id in req.materials:
            cur.execute("SELECT filename, id FROM documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if row:
                query_for_retrieve = f"招标文件：{req.parse_result.get('project_name', '')} {req.parse_result.get('deadline', '')}"
                chunks = retrieve(query_for_retrieve, top_k=3, doc_ids=[doc_id])
                for chunk in chunks:
                    materials_text += f"[{row['filename']}]\n{chunk['text']}\n\n"
        conn.close()

    # 检查是否需要 raw_text 降级
    raw_text = req.parse_result.get("raw_text", "")
    project_name = req.parse_result.get("project_name", "")
    confidence = req.parse_result.get("parse_meta", {}).get("confidence", 1.0)
    use_raw_fallback = (
        "未识别" in project_name
        or "解析失败" in project_name
        or confidence < 0.5
    )

    bid_info = f"""招标文件：
- 项目名称：{project_name}
- 工期：{req.parse_result.get("deadline", "")}
- 资格要求：{", ".join(req.parse_result.get("requirements", []))}
- 资质要求：{", ".join(req.parse_result.get("qualification", []))}
- {_format_scoring(req.parse_result.get("scoring", {}))}"""

    # 降级：confidence 低于阈值时，把 raw_text 直接附在后面让 LLM 再读
    if use_raw_fallback and raw_text:
        bid_info += f"\n\n【原文内容】（解析结果不可信，请直接阅读原文提取关键信息）：\n{raw_text[:3000]}"

    prompt = f"""根据以下招标文件要求和素材，生成一份投标标书。

{bid_info}

可用素材：
{materials_text[:5000] if materials_text else "无"}

请生成完整的投标标书，包含：
1. 投标函
2. 资格审查文件
3. 技术标
4. 商务标

输出格式：Markdown"""

    async def stream_response():
        # 阶段0：生成前废标项预检
        yield _sse_event({"stage": "violation_check", "progress": 5, "message": "正在检测废标项风险..."})
        
        # 废标项检查（generate 阶段：检测标书正文是否满足招标文件要求）
        violation_checker = get_violation_checker()
        violation_result = None
        if req.parse_result:
            violation_result = violation_checker.check_bid_content(
                "",  # 还没生成，先用 parse_result 做生成前检查
                req.parse_result
            )
            # 如果有必废标项，中断生成流程
            if not violation_result["passed"]:
                yield _sse_event({
                    "stage": "violation_fail",
                    "progress": 0,
                    "message": "检测到废标风险，生成已中止",
                    "violation_result": {
                        "passed": False,
                        "violations": violation_result["violations"],
                        "summary": violation_result["summary"],
                    }
                })
                return

        # 阶段1：生成中
        yield _sse_event({"stage": "generating", "progress": 10, "message": "正在生成标书正文..."})

        content_parts = []
        for delta in generator.generate_stream(prompt, system=SYSTEM_PROMPT):
            content_parts.append(delta)
            # 估算进度 10-60%
            yield _sse_event({"stage": "generating", "progress": 30, "message": "生成中...", "delta": delta})

        content = "".join(content_parts)
        content = "".join(content_parts)
        
        # ── 阶段2：废标项检测（基于生成的标书正文）───────────────────────
        yield _sse_event({"stage": "violation_check", "progress": 65, "message": "废标项合规性检测..."})
        if req.parse_result:
            violation_result = violation_checker.check_bid_content(content, req.parse_result)
            if not violation_result["passed"]:
                yield _sse_event({
                    "stage": "violation_warn",
                    "progress": 65,
                    "message": "存在废标风险项，请留意",
                    "violation_result": violation_result,
                })
        
        # 阶段3：质检
        yield _sse_event({"stage": "reviewing", "progress": 70, "message": "AI 质检审核中..."})

        # 阶段2：质检
        review = review_bid(content, req.parse_result)

        # 质检未通过则重生成一轮
        if not review["passed"]:
            yield _sse_event({"stage": "retry", "progress": 75, "message": "质检未通过，重新生成中..."})
            review_note = "\n\n[审核意见] " + "；".join(review.get("suggestions", []))
            retry_prompt = prompt + review_note
            content_parts = []
            for delta in generator.generate_stream(retry_prompt, system=SYSTEM_PROMPT):
                content_parts.append(delta)
                yield _sse_event({"stage": "retry", "progress": 85, "message": "重新生成中...", "delta": delta})
            content = "".join(content_parts)
            # 重新质检
            review = review_bid(content, req.parse_result)
            yield _sse_event({"stage": "reviewing", "progress": 90, "message": "重新审核中..."})

        # ── 阶段4：标书查重 ──────────────────────────────────────────
        yield _sse_event({"stage": "plagiarism_check", "progress": 88, "message": "标书查重检测..."})
        plagiarism_checker = get_plagiarism_checker()
        plagiarism_result = plagiarism_checker.check(
            bid_content=content,
            exclude_doc_ids=req.materials or [],
        )
        
        # 阶段5：生成 Word
        yield _sse_event({"stage": "word", "progress": 95, "message": "正在生成 Word 文件..."})
        doc = _docx_from_markdown(content, req.parse_result.get("project_name", "投标标书"))
        output_path = GENERATED_DIR / f"bid_{uuid.uuid4().hex[:8]}.docx"
        doc.save(str(output_path))

        # 阶段6：完成
        yield _sse_event({
            "stage": "done",
            "progress": 100,
            "message": "生成完成",
            "file_path": str(output_path),
            "filename": output_path.name,
            "review": {
                "passed": review["passed"],
                "score": review.get("score", 0),
                "issues": review.get("issues", []),
            },
            "violation_result": violation_result,
            "plagiarism_result": {
                "passed": plagiarism_result["passed"],
                "overall_score": plagiarism_result["overall_score"],
                "high_risk_sections": plagiarism_result["high_risk_sections"],
                "sections": [{"section_name": s["section_name"], "risk_level": s["risk_level"], "similarity_score": s["similarity_score"]} for s in plagiarism_result["sections"]],
            },
        })

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/download/{filename}")
def download_bid(filename: str):
    path = GENERATED_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/analyze-old/{doc_id}")
def analyze_old_bid(doc_id: int):
    """拆解历史投标标书为结构化章节并存入向量库"""
    from server.tools.bid_analyzer import analyze_old_bid, store_analyzed_sections

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = cur.fetchone()
    conn.close()

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    from server.core.parser.document import parse_file
    text, _ = parse_file(doc["file_path"])

    if len(text.strip()) < 200:
        raise HTTPException(status_code=400, detail="文档内容太少（< 200 字），无法解析")

    sections = analyze_old_bid(text)
    if not sections:
        return Resp(code=1, message="未能识别出标书章节结构，请确认文件是否为投标标书")

    stored = store_analyzed_sections(doc_id, sections)
    return Resp(data={
        "doc_id": doc_id,
        "filename": doc["filename"],
        "section_count": len(sections),
        "sections": [{
            "section_name": s.get("section_name"),
            "section_type": s.get("section_type"),
            "key_info": s.get("key_info"),
        } for s in sections],
    })


@router.get("/analyze-old/{doc_id}/sections")
def get_analyzed_sections(doc_id: int):
    """查看历史标书拆解结果"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM chunks
        WHERE doc_id = ? AND json_extract(metadata, '$.source_type') = 'bid_section'
        ORDER BY chunk_index
    """, (doc_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return Resp(code=1, message="该文档尚未进行标书拆解分析")

    import json
    return Resp(data=[{
        "section_name": json.loads(r["metadata"]).get("section_name", ""),
        "section_type": json.loads(r["metadata"]).get("section_type", ""),
        "key_info": json.loads(r["metadata"]).get("key_info", ""),
        "content": r["text"],
        "chunk_index": r["chunk_index"],
    } for r in rows])


@router.post("/match_check")
def match_check(req: BidMatchCheckReq):
    """
    招标文件与素材的匹配度检测。
    对每个选中素材，用 parse_result 关键字段（项目名称、资格要求、评分标准）
    构造检索 query，查对应素材的 chunks，计算平均 relevance score。
    """
    parse_result = req.parse_result
    project_name = parse_result.get("project_name", "")
    requirements = parse_result.get("requirements", [])
    scoring = parse_result.get("scoring", {})

    # 构造查询文本
    query_parts = [project_name] if project_name else []
    query_parts.extend([r for r in requirements if r and "未识别" not in r])
    if scoring:
        sections = scoring.get("sections", [])
        for section in sections:
            for item in section.get("items", []):
                if item.get("name"):
                    query_parts.append(item["name"])
    query_text = " ".join(query_parts)

    results = []
    for doc_id in req.materials:
        # 查对应 doc 的 chunks
        chunks = retrieve(query_text, top_k=5, doc_ids=[doc_id])
        if not chunks:
            results.append({"doc_id": doc_id, "score": 0.0, "level": "low"})
            continue

        # 用 score 作为匹配度（score 越大相关性越高）
        avg_score = sum(c.get("score", 0.0) for c in chunks) / len(chunks)
        # 归一化到 0-1，越接近 1 相关性越高（retriever 返回的 score 通常是余弦相似度，0.5+ 表示较好）
        normalized = max(0.0, min(1.0, (avg_score + 1) / 2))
        score_pct = round(normalized * 100)

        if normalized >= 0.75:
            level = "high"
        elif normalized >= 0.5:
            level = "mid"
        else:
            level = "low"

        results.append({
            "doc_id": doc_id,
            "score": score_pct,
            "level": level,
        })

    # 汇总
    total = len(results)
    low_count = sum(1 for r in results if r["level"] == "low")
    mid_count = sum(1 for r in results if r["level"] == "mid")
    high_count = sum(1 for r in results if r["level"] == "high")
    avg_score_pct = round(sum(r["score"] for r in results) / total) if total else 0

    return {
        "query_summary": query_text[:200],
        "materials": results,
        "summary": {
            "total": total,
            "high": high_count,
            "mid": mid_count,
            "low": low_count,
            "avg_score": avg_score_pct,
        },
        "warning": "部分素材与招标文件匹配度较低，建议更换或补充相关素材" if low_count > 0 else None,
    }


# ── 废标项检查 ─────────────────────────────────────────────────────────────────


class ViolationCheckReq(BaseModel):
    parse_result: Optional[dict] = None        # 招标文件解析结果
    bid_content: Optional[str] = None          # 标书正文（generate 阶段检测）
    raw_text: Optional[str] = None             # 招标文件原文（parse 阶段检测）
    check_stage: Optional[str] = "auto"       # auto | parse | generate | review


class ViolationCheckResp(BaseModel):
    passed: bool
    violations: List[dict]
    warnings: List[dict]
    summary: dict


@router.post("/violation_check", response_model=ViolationCheckResp)
def check_violations(req: ViolationCheckReq):
    """
    废标项检查接口
    
    - check_stage=parse：检测招标文件本身的合规性（是否有废标条件）
    - check_stage=generate：检测生成的标书正文是否满足招标文件要求
    - check_stage=review：合并两阶段检测
    """
    checker = get_violation_checker()
    
    stage = req.check_stage if req.check_stage != "auto" else None
    
    # 自动判断阶段
    if req.bid_content and req.parse_result:
        # 生成阶段 + 质检阶段合并检测
        result = checker.check_bid_content(req.bid_content, req.parse_result)
    elif req.bid_content:
        result = checker.check_document(req.bid_content, stage=stage or "review")
    elif req.parse_result:
        result = checker.check_parse_result(req.parse_result, req.raw_text or "")
    else:
        raise HTTPException(status_code=400, detail="缺少检测内容：bid_content 或 parse_result 二选一")
    
    return result


@router.get("/disqualify_rules")
def list_disqualify_rules():
    """获取废标红线规则列表（供管理后台展示）"""
    checker = get_violation_checker()
    return checker.get_disqualify_rules()


@router.get("/violation_cases")
def list_violation_cases(category: str = None):
    """获取违规案例库（可按类别过滤）"""
    checker = get_violation_checker()
    return checker.get_violation_cases(category)


# ── 标书查重 ──────────────────────────────────────────────────────────────────


class PlagiarismCheckReq(BaseModel):
    bid_content: str                    # 待检测的标书正文（Markdown）
    exclude_doc_ids: Optional[List[int]] = None   # 排除的文档ID


class PlagiarismCheckResp(BaseModel):
    passed: bool
    overall_score: float
    total_sections: int
    high_risk_sections: int
    sections: List[dict]
    summary: dict


@router.post("/plagiarism_check", response_model=PlagiarismCheckResp)
def check_plagiarism(req: PlagiarismCheckReq):
    """
    标书查重接口
    检测新生成的标书与知识库中已有标书的相似程度。
    相似度超过 85% 的章节会被标记为高风险。
    """
    if not req.bid_content or len(req.bid_content.strip()) < 100:
        raise HTTPException(status_code=400, detail="标书内容太短，无法进行查重检测")
    
    checker = get_plagiarism_checker()
    result = checker.check(
        bid_content=req.bid_content,
        exclude_doc_ids=req.exclude_doc_ids or [],
    )
    return result
