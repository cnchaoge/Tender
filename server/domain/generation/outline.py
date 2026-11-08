"""标书目录规划。指定模板且章节可读时直接返回，否则调用模型。"""
from server.core.generator.llm import get_generator
from server.db.sqlite import get_db
from server.domain.generation.draft import format_scoring as _format_scoring
from server.domain.generation.materials import _retrieve_materials_text
from server.domain.generation.parse import _json_clean
from server.models import BidPlanReq, BidPlanResp

def plan_bid(req: BidPlanReq):
    """生成标书目录大纲（规划阶段）"""

    # 如果指定了模板，直接返回模板定义的章节
    if req.template_id:
        import json
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT chapters FROM bid_templates WHERE id = ?", (req.template_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            try:
                chapters_data = json.loads(row["chapters"])
                chapters_with_status = [
                    {"index": idx, "name": ch.get("name", ""), "description": ch.get("description", ""), "status": "pending", "key_points": ch.get("key_points", "")}
                    for idx, ch in enumerate(chapters_data)
                ]
                return BidPlanResp(chapters=chapters_with_status)
            except (json.JSONDecodeError, KeyError):
                pass  # 模板数据异常，降级到 LLM 生成

    generator = get_generator()

    # 规划阶段还没有章节，用招标要求与评分项做文档级检索，而不是只查项目名和工期。
    materials_text = _retrieve_materials_text(
        req.parse_result, req.materials, per_doc_k=2, max_chars=2000
    )

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
        # Add index and initial status to each chapter
        chapters_with_status = [
            {"index": idx, "name": ch.get("name", ""), "description": ch.get("description", ""), "status": "pending"}
            for idx, ch in enumerate(chapters)
        ]
        return BidPlanResp(chapters=chapters_with_status)
    except Exception:
        # 失败时返回默认结构
        default_chapters = [
            {"name": "第一章 投标函", "description": "投标函正文，包含投标报价、工期承诺等"},
            {"name": "第二章 资格审查文件", "description": "企业资质证明、业绩材料等"},
            {"name": "第三章 技术标", "description": "施工方案、技术路线、进度计划等"},
            {"name": "第四章 商务标", "description": "报价明细表、投标保证金等"},
        ]
        chapters_with_status = [
            {"index": idx, "name": ch["name"], "description": ch["description"], "status": "pending"}
            for idx, ch in enumerate(default_chapters)
        ]
        return BidPlanResp(chapters=chapters_with_status)
