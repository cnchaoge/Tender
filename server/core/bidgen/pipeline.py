"""标书生成的一条流水线：组 prompt、调模型、质检后最多重写一轮。

`POST /api/bid/generate` 与 `POST /api/bid/generate/stream` 都走这里。
流式接口额外的废标预检、格式检查、查重和 SSE 进度仍留在路由里。
"""
import re

from server.core.reviewer.bid_reviewer import review_bid

SYSTEM_PROMPT = """你是一个专业的招投标文档专家，擅长分析招标文件并生成投标标书。"""

_CHAPTER_PREFIXES = (
    "第一章 ",
    "第二章 ",
    "第三章 ",
    "第四章 ",
    "第五章 ",
    "第六章 ",
    "第七章 ",
    "第八章 ",
    "第九章 ",
    "第十章 ",
    "第1章 ",
    "第2章 ",
    "第3章 ",
    "第4章 ",
    "第5章 ",
)

_STRATEGIES = {
    "技术优先型": "【投标策略】：技术优先型\n- 侧重技术方案完整性、创新点、工程质量保障措施\n- 技术标内容要详细、专业，突出企业技术优势和施工能力\n- 适当弱化价格因素，以技术方案得分最大化为目标\n- 注重施工工艺、质量控制体系、安全文明施工等章节的深度",
    "成本控制型": "【投标策略】：成本控制型\n- 侧重成本优化、施工方案经济性、项目利润最大化\n- 在满足招标要求的前提下，尽量压缩成本，提高利润率\n- 报价策略优先，采用有竞争力的价格策略\n- 技术方案以「合格」为标准，不过度展开，简明扼要即可",
    "综合均衡型": "【投标策略】：综合均衡型\n- 技术和价格平衡，在满足招标要求的前提下追求性价比最优\n- 技术方案完整、专业，但不过度冗余\n- 报价合理有竞争力，既不过高也不恶性低价\n- 标书整体均衡、专业、完整，能满足评标的各方面要求",
}


def format_scoring(scoring: dict) -> str:
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


def strategy_guidance(strategy: str) -> str:
    """根据策略返回对应的投标策略指导文本。未知策略回落到综合均衡型。"""
    return _STRATEGIES.get(strategy, _STRATEGIES["综合均衡型"])


def build_bid_info(parse_result: dict) -> str:
    """招标文件摘要。解析置信度低时附上原文，供模型自行抽取。"""
    parse_result = parse_result or {}
    raw_text = parse_result.get("raw_text", "")
    project_name = parse_result.get("project_name", "")
    confidence = parse_result.get("parse_meta", {}).get("confidence", 1.0)
    use_raw_fallback = (
        "未识别" in project_name
        or "解析失败" in project_name
        or confidence < 0.5
    )
    bid_info = f"""招标文件：
- 项目名称：{project_name}
- 工期：{parse_result.get("deadline", "")}
- 资格要求：{", ".join(parse_result.get("requirements", []))}
- 资质要求：{", ".join(parse_result.get("qualification", []))}
- {format_scoring(parse_result.get("scoring", {}))}"""
    if use_raw_fallback and raw_text:
        bid_info += f"\n\n【原文内容】（解析结果不可信，请直接阅读原文提取关键信息）：\n{raw_text[:3000]}"
    return bid_info


def build_generation_prompt(parse_result: dict, materials_text: str, strategy: str = "综合均衡型") -> str:
    """批量接口和流式接口共用的正文 prompt。策略段始终写入，避免两条路径各写一份。"""
    materials_block = materials_text if materials_text else "无"
    return f"""根据以下招标文件要求和素材，生成一份投标标书。

{build_bid_info(parse_result)}

{strategy_guidance(strategy)}

可用素材（按章节分组，撰写该章节时优先使用对应素材）：
{materials_block}

请生成完整的投标标书，包含：
1. 投标函
2. 资格审查文件
3. 技术标
4. 商务标

输出格式：Markdown"""


def review_retry_prompt(prompt: str, review: dict) -> str:
    review_note = "\n\n[审核意见] " + "；".join(review.get("suggestions", []))
    return prompt + review_note


def chapter_lookup(chapters: list | None) -> dict:
    """章节标题去掉「第N章」前缀后映射到 index，供流式输出识别当前章。"""
    lookup = {}
    for ch in chapters or []:
        name = ch.get("name", "")
        for prefix in _CHAPTER_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        lookup[name] = ch.get("index", 0)
    return lookup


def match_heading_chapter(delta: str, lookup: dict):
    """delta 以 markdown 标题开头且能对上章节时，返回 (index, 去前缀后的章节名)。"""
    if not lookup:
        return None
    heading_match = re.match(r"^(#{1,4})\s+(.+?)\n", delta)
    if not heading_match:
        return None
    heading_text = heading_match.group(2).strip()
    for ch_name, ch_idx in lookup.items():
        if ch_name in heading_text or heading_text in ch_name:
            return ch_idx, ch_name
    return None


class BidDraftPipeline:
    """一次生成，质检不通过则按审核意见再生成一轮。"""

    def __init__(self, generator, parse_result: dict, materials_text: str, strategy: str = "综合均衡型"):
        self.generator = generator
        self.parse_result = parse_result or {}
        self.prompt = build_generation_prompt(self.parse_result, materials_text, strategy)
        self.content = ""
        self.review: dict | None = None
        self.attempt = 0

    def iter_deltas(self, *, stream: bool):
        """产出模型增量。stream=False 时整段作为一次增量，对应 generate()。"""
        self.attempt += 1
        if self.attempt > 2:
            raise RuntimeError("标书生成最多重写一轮")
        if self.attempt == 1:
            prompt = self.prompt
        else:
            if not self.review:
                raise RuntimeError("重写前需要先质检")
            prompt = review_retry_prompt(self.prompt, self.review)
        parts: list[str] = []
        if stream:
            chunks = self.generator.generate_stream(prompt, system=SYSTEM_PROMPT)
        else:
            chunks = (self.generator.generate(prompt, system=SYSTEM_PROMPT),)
        for delta in chunks:
            parts.append(delta)
            yield delta
        self.content = "".join(parts)

    def review_draft(self) -> dict:
        self.review = review_bid(self.content, self.parse_result)
        return self.review

    def needs_retry(self) -> bool:
        if self.attempt != 1 or not self.review:
            return False
        return not self.review["passed"]
