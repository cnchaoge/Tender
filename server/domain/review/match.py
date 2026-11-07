"""招标要求与选中素材的匹配度。"""
from server.core.retriever.retriever import retrieve
from server.models import BidMatchCheckReq

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
