"""按当前招标内容在一份历史素材里推荐相似章节。"""
import json
import re
from typing import Optional

from fastapi import HTTPException

from server.core.retriever.retriever import retrieve
from server.core.retriever.section_query import build_section_retrieval_query
from server.db.sqlite import get_db

_PREVIEW_QUERY_LIMIT = 420
_PREVIEW_TEXT_LIMIT = 500
_PREVIEW_DEFAULT_K = 8
_PREVIEW_MAX_K = 20
_PARSE_CONTEXT_KEYS = (
    "project_name",
    "deadline",
    "requirements",
    "qualification",
    "scoring",
    "technical_requirements",
    "tech_requirements",
    "technical_specs",
)


def _nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_nonempty(item) for item in value)
    if isinstance(value, dict):
        return any(_nonempty(item) for item in value.values())
    return value is not None and value is not False


def _has_recommend_context(parse_result: Optional[dict], chapter: Optional[dict]) -> bool:
    if isinstance(chapter, dict) and any(
        _nonempty(chapter.get(key)) for key in ("name", "description", "key_points")
    ):
        return True
    if not isinstance(parse_result, dict):
        return False
    return any(_nonempty(parse_result.get(key)) for key in _PARSE_CONTEXT_KEYS)


def build_recommend_query(
    q: Optional[str] = None,
    parse_result: Optional[dict] = None,
    chapter: Optional[dict] = None,
) -> str:
    """把显式检索词和当前招标解析结果合成一条检索查询。"""
    explicit = " ".join((q or "").split())
    contextual = ""
    if _has_recommend_context(parse_result, chapter):
        contextual = build_section_retrieval_query(parse_result or {}, chapter)
    if explicit and contextual:
        query = contextual if explicit in contextual else f"{explicit} {contextual}"
    else:
        query = explicit or contextual
    query = " ".join(query.split())
    if len(query) > _PREVIEW_QUERY_LIMIT:
        query = query[:_PREVIEW_QUERY_LIMIT].rstrip()
    return query


def _coerce_top_k(top_k: int) -> int:
    try:
        k = int(top_k)
    except (TypeError, ValueError):
        k = _PREVIEW_DEFAULT_K
    return max(1, min(_PREVIEW_MAX_K, k))


def _preview_chunk_index(hit: dict) -> Optional[int]:
    meta = hit.get("metadata") or {}
    raw = meta.get("chunk_index") if isinstance(meta, dict) else None
    if isinstance(raw, bool):
        raw = None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    match = re.search(r"_chunk(\d+)$", str(hit.get("id") or ""))
    if match:
        return int(match.group(1))
    return None


def _load_preview_doc(doc_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT filename, id FROM documents WHERE id = ?", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            return None
        cur.execute(
            "SELECT chunk_index, metadata FROM chunks WHERE doc_id = ?",
            (doc_id,),
        )
        catalog = {}
        for row in cur.fetchall():
            meta: dict = {}
            try:
                parsed = json.loads(row["metadata"] or "{}")
                if isinstance(parsed, dict):
                    meta = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                meta = {}
            catalog[row["chunk_index"]] = meta
        return {"filename": doc["filename"], "catalog": catalog}
    finally:
        conn.close()


def _section_score(hit: dict) -> Optional[float]:
    raw = hit.get("score")
    try:
        if raw is None:
            return None
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _rank_score(hit: dict) -> float:
    score = _section_score(hit)
    if score is None:
        return float("-inf")
    return score


def recommend_sections(
    doc_id: int,
    q: Optional[str] = None,
    parse_result: Optional[dict] = None,
    chapter: Optional[dict] = None,
    top_k: int = _PREVIEW_DEFAULT_K,
) -> dict:
    """在指定素材内，按与当前招标内容的相似度返回章节。"""
    doc = _load_preview_doc(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    query = build_recommend_query(q, parse_result, chapter)
    if not query:
        raise HTTPException(
            status_code=400,
            detail="请提供当前招标文件的解析结果或检索词，以便按相似度推荐章节",
        )

    k = _coerce_top_k(top_k)
    hits = retrieve(query, top_k=k, doc_ids=[doc_id]) or []
    hits.sort(key=_rank_score, reverse=True)

    sections = []
    for rank, hit in enumerate(hits):
        meta = hit.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        index = _preview_chunk_index(hit)
        stored = doc["catalog"].get(index, {}) if index is not None else {}
        sections.append({
            "index": index if index is not None else rank,
            "rank": rank,
            "text": (hit.get("text") or "")[:_PREVIEW_TEXT_LIMIT],
            "section_name": meta.get("section_name") or stored.get("section_name") or "",
            "section_type": meta.get("section_type") or stored.get("section_type") or "",
            "score": _section_score(hit),
        })

    payload = {
        "id": doc_id,
        "filename": doc["filename"],
        "section_count": len(sections),
        "ranked": True,
        "query": query[:200],
        "sections": sections,
    }
    if not sections:
        payload["message"] = "未找到与当前招标文件相似的章节"
    return payload
