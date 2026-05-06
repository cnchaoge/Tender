"""
ClawOS X - 标书生成 API
"""
import re
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from docx import Document as DocxDocument
from docx.shared import Pt, Inches

from server.config import GENERATED_DIR, get_settings
from server.db.sqlite import get_db
from server.core.retriever.retriever import retrieve
from server.core.generator.llm import get_generator
from server.models import BidParseReq, BidParseResp, BidGenerateReq, Resp

router = APIRouter(prefix="/api/bid", tags=["标书生成"])
settings = get_settings()

SYSTEM_PROMPT = """你是一个专业的招投标文档专家，擅长分析招标文件并生成投标标书。"""

 
@router.post("/parse", response_model=BidParseResp)
def parse_bid_file(req: BidParseReq):
    """解析招标文件，提取关键信息"""
    import os
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    from server.core.parser.document import parse_file
    text, _ = parse_file(req.file_path)
    
    generator = get_generator()
    prompt = f"""请从以下招标文件中提取关键信息，以JSON格式返回：

招标文件内容：
{{text[:8000]}}

请提取并返回以下JSON格式（只返回JSON，不要其他内容）：
{{
    "project_name": "项目名称",
    "deadline": "工期/交付时间",
    "requirements": ["资格要求1", "资格要求2"],
    "qualification": ["资质要求1", "资质要求2"],
    "scoring": [{{"item": "评分项", "weight": "权重"}}]
}}"""

    try:
        result_text = generator.generate(prompt, system="你是一个招投标专家，擅长提取招标文件关键信息。")
        # 尝试解析JSON
        import json
        result = json.loads(result_text)
        return BidParseResp(raw_text=text[:2000], **{k: v for k, v in result.items()})
    except Exception as e:
        return BidParseResp(
            project_name="解析失败",
            deadline="",
            requirements=[f"解析错误: {str(e)}"],
            qualification=[],
            scoring=[],
            raw_text=text[:2000]
        )


@router.post("/generate", response_model=dict)
def generate_bid(req: BidGenerateReq):
    """根据招标文件生成标书"""
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
                chunks = retrieve(f"招标文件：{req.parse_result}", top_k=3, doc_ids=[doc_id])
                for chunk in chunks:
                    materials_text += f"[{row['filename']}]\n{chunk['text']}\n\n"
        conn.close()
    
    prompt = f"""根据以下招标文件要求和素材，生成一份投标标书。

招标文件：
- 项目名称：{req.parse_result.get("project_name", "")}
- 工期：{req.parse_result.get("deadline", "")}
- 资格要求：{", ".join(req.parse_result.get("requirements", []))}
- 资质要求：{", ".join(req.parse_result.get("qualification", []))}
- 评分标准：{req.parse_result.get("scoring", [])}

可用素材：
{{materials_text[:5000] if materials_text else "无"}}

请生成完整的投标标书，包含：
1. 投标函
2. 资格审查文件
3. 技术标
4. 商务标

输出格式：Markdown""" 

    content = generator.generate(prompt, system=SYSTEM_PROMPT)
    
    # 转为 Word
    doc = DocxDocument()
    doc.add_heading(req.parse_result.get("project_name", "投标标书"), 0)
    for line in content.split("\n"):
        if line.startswith("# "):
            doc.add_heading(line[2:], 1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], 2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], 3)
        else:
            doc.add_paragraph(line)
    
    output_path = GENERATED_DIR / f"bid_{uuid.uuid4().hex[:8]}.docx"
    doc.save(str(output_path))
    
    return {"file_path": str(output_path), "filename": output_path.name}


@router.get("/download/{filename}")
def download_bid(filename: str):
    path = GENERATED_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
