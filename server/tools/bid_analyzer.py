"""
ClawOS X - 旧标书解析工具
将历史投标标书拆解为结构化章节，存入向量库供新标书生成时匹配复用
"""
import json
from server.core.generator.llm import get_generator
from server.db.sqlite import get_db
from server.db.chromadb import add_chunks
from server.core.embedder.embedder import get_embedder

BID_SECTION_TYPES = {
    "bid_letter": "投标函",
    "qualification": "资格审查文件",
    "technical": "技术标",
    "commercial": "商务标",
    "price": "报价明细",
    "company_profile": "公司介绍",
    "appendix": "附录附件",
    "other": "其他",
}


def analyze_old_bid(text: str) -> list[dict]:
    """用 LLM 拆解旧标书为结构化章节"""
    generator = get_generator()

    prompt = f"""你是一个投标标书分析专家。请分析以下旧标书文件，将其拆解为结构化章节。

每个章节包含：
- section_name: 章节名称
- section_type: 章节类型（technical=技术标, commercial=商务标, qualification=资格审查, price=报价, company_profile=公司介绍, bid_letter=投标函, appendix=附录/附件, other=其他）
- content: 该章节的完整文本内容
- key_info: 该章节的核心内容摘要（一句话说明）

旧标书内容：
{text[:12000]}

以JSON数组格式返回分析结果（如果内容不足或不是标书文件，返回空数组）：
[
    {{
        "section_name": "技术方案",
        "section_type": "technical",
        "content": "该章节的完整文本...",
        "key_info": "详细描述了监控系统的技术架构和实施方案"
    }}
]

要求：
1. 根据实际内容自动判断章节数量（2-8个章节）
2. 每个章节内容完整，保留原文关键信息
3. section_type 必须是预定义类型之一
4. 只返回JSON数组，不要其他内容"""

    raw = generator.generate(prompt, system="你是一个投标标书文档结构化专家。")

    # 清理 markdown 包装
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        sections = json.loads(raw)
        if not isinstance(sections, list):
            return []
        return sections
    except json.JSONDecodeError:
        return []


def store_analyzed_sections(doc_id: int, sections: list[dict]):
    """将拆解后的标书章节存入 SQLite 和 ChromaDB（作为特殊类型的 chunk）"""
    embedder = get_embedder()
    conn = get_db()
    cur = conn.cursor()

    chunk_records = []
    for i, sec in enumerate(sections):
        section_type = sec.get("section_type", "other")
        section_name = sec.get("section_name", "")
        content = sec.get("content", "")
        key_info = sec.get("key_info", "")

        # 写入 SQLite chunks 表
        metadata = json.dumps({
            "source_type": "bid_section",
            "section_type": section_type,
            "section_name": section_name,
            "key_info": key_info,
        }, ensure_ascii=False)
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
            (doc_id, i, content, metadata)
        )
        chunk_records.append({
            "text": content,
            "chunk_index": i,
            "metadata": {
                "source_type": "bid_section",
                "section_type": section_type,
                "section_name": section_name,
                "key_info": key_info,
            }
        })

    # Embed 并写入 ChromaDB
    texts = [r["text"] for r in chunk_records]
    vectors = embedder.embed(texts)
    for r, v in zip(chunk_records, vectors):
        r["vector"] = v

    add_chunks(doc_id, chunk_records)

    # 更新文档的 chunk_count
    cur.execute("UPDATE documents SET chunk_count = chunk_count + ? WHERE id = ?",
                (len(sections), doc_id))
    conn.commit()
    conn.close()

    return len(sections)
