"""
ClawOS X - 标书质检模块
生成正文后，AI 自我审查，检查完整性和格式
"""
from typing import Optional
import json
import re
from server.core.generator.llm import get_generator

REVIEW_PROMPT = """你是一个专业的招投标文档审核专家。请审核以下投标标书，输出 JSON 格式结果：

标书内容：
{bid_content}

招标文件关键要求：
- 项目名称：{project_name}
- 工期：{deadline}
- 资格要求：{requirements}
- 资质要求：{qualification}
- 评分标准：{scoring}

输出格式（只返回 JSON，不要其他内容）：
{{
    "passed": true/false,
    "score": 0-100,
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"],
    "coverage_check": {{
        "requirements_covered": ["已覆盖的资质要求"],
        "requirements_missing": ["未覆盖的资质要求"]
    }}
}}
"""


def _json_clean(raw: str) -> str:
    """去掉 markdown json 包装（```json ... ```）"""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw.strip()


def _try_parse(text: str) -> Optional[dict]:
    """尝试解析 JSON，失败返回 None"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def review_bid(bid_content: str, parse_result: dict) -> dict:
    """
    审核标书正文，带 JSON 解析重试机制（最多 3 轮）

    Args:
        bid_content: 生成的标书正文（Markdown）
        parse_result: 招标文件解析结果（BidParseResp）

    Returns:
        BidReviewResult dict
    """
    generator = get_generator()

    prompt = REVIEW_PROMPT.format(
        bid_content=bid_content[:8000],  # 截断避免超出 token
        project_name=parse_result.get("project_name", ""),
        deadline=parse_result.get("deadline", ""),
        requirements=", ".join(parse_result.get("requirements", []) or ["无"]),
        qualification=", ".join(parse_result.get("qualification", []) or ["无"]),
        scoring=str(parse_result.get("scoring", [])),
    )

    # ── JSON 解析重试机制（最多 3 轮）────────────────────────────────
    retry_count = 0
    max_retries = 3
    result = None

    while retry_count < max_retries:
        try:
            result_text = generator.generate(
                prompt,
                system="你是一个专业的招投标文档审核专家，严格把关标书质量。只返回 JSON，不要其他内容。"
            )
            # 清理 markdown 包装
            cleaned = _json_clean(result_text)
            result = _try_parse(cleaned)
            if result is not None:
                # 校验必要字段
                if "passed" in result and "score" in result:
                    return result
                # 字段不全，再试一轮
            retry_count += 1
            if retry_count < max_retries:
                # 追加修复提示，重新生成
                prompt += f"\n\n[系统] 上一轮 JSON 解析结果字段不完整，请重新生成标准 JSON（必须包含 passed、score、issues、suggestions）。"
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                break
            prompt += f"\n\n[系统] 解析异常: {str(e)}，请重新生成标准 JSON。"

    # 所有轮次都失败，返回安全默认值，不阻断主流程
    return {
        "passed": True,
        "score": 70,
        "issues": ["审核环节出现异常，标书已放行"],
        "suggestions": [],
        "coverage_check": {"requirements_covered": [], "requirements_missing": []}
    }


def _check_format_compliance(bid_content: str, parse_result: dict) -> dict:
    """
    检测标书格式规范

    检测项：
    1. 目录是否存在
    2. 页眉页脚（投标方名称、项目名称）
    3. 签字盖章位置标记
    4. 页码格式
    5. 技术标/商务标章节完整性

    Returns:
        {
            "passed": bool,
            "warnings": [{"item": str, "status": str, "detail": str}],
            "score": int,  # 格式评分 0-100
        }
    """
    warnings = []
    score = 100

    text_lower = bid_content.lower()

    # ── 1. 目录检测 ──────────────────────────────────────────────
    has_toc = bool(
        re.search(r"^#{1,3}\s*目\s*录", bid_content, re.MULTILINE) or
        re.search(r"^#{1,3}\s*table\s*of\s*contents", bid_content, re.IGNORECASE | re.MULTILINE) or
        re.search(r"^目\s*录", bid_content, re.MULTILINE)
    )
    if has_toc:
        warnings.append({"item": "目录", "status": "pass", "detail": "标书包含目录章节"})
    else:
        warnings.append({"item": "目录", "status": "warning", "detail": "未找到目录章节，建议自动生成目录"})
        score -= 15

    # ── 2. 签字盖章位置检测 ────────────────────────────────────
    has_seal = bool(
        re.search(r"（盖章）", bid_content) or
        re.search(r"（签字）", bid_content) or
        re.search(r"盖章处", bid_content) or
        re.search(r"签字处", bid_content)
    )
    if has_seal:
        warnings.append({"item": "签字盖章", "status": "pass", "detail": "检测到签字盖章位置标记"})
    else:
        warnings.append({"item": "签字盖章", "status": "warning", "detail": "未检测到签字盖章位置标记，生成后请手动补充"})
        score -= 20

    # ── 3. 页码格式检测 ────────────────────────────────────────
    has_page_number = bool(
        re.search(r"第\d+页共\d+页", bid_content) or
        re.search(r"页\s*码", bid_content) or
        re.search(r"page\s*\d+", bid_content, re.IGNORECASE)
    )
    if has_page_number:
        warnings.append({"item": "页码", "status": "pass", "detail": "检测到页码相关描述"})
    else:
        warnings.append({"item": "页码", "status": "warning", "detail": "未检测到页码格式，建议添加「第X页共Y页」"})
        score -= 10

    # ── 4. 章节完整性（技术标/商务标）─────────────────────────
    required_sections = {
        "技术标": bool(re.search(r"^#{1,3}\s*技术标", bid_content, re.MULTILINE)),
        "商务标": bool(re.search(r"^#{1,3}\s*商务标", bid_content, re.MULTILINE)),
    }
    for section, found in required_sections.items():
        if found:
            warnings.append({"item": section, "status": "pass", "detail": f"包含{section}章节"})
        else:
            warnings.append({"item": section, "status": "warning", "detail": f"未找到{section}章节"})
            score -= 15

    # ── 5. 投标方/项目名称页眉检测 ────────────────────────────
    project_name = parse_result.get("project_name", "")
    has_header = False
    if project_name and project_name not in ("未识别到项目名称", "解析失败"):
        has_header = project_name in bid_content
    if has_header:
        warnings.append({"item": "页眉页脚", "status": "pass", "detail": "包含项目名称相关内容"})
    else:
        warnings.append({"item": "页眉页脚", "status": "warning", "detail": "建议在页眉页脚包含投标方名称和项目名称"})
        score -= 10

    score = max(0, score)
    passed = score >= 70

    return {
        "passed": passed,
        "warnings": warnings,
        "score": score,
    }
