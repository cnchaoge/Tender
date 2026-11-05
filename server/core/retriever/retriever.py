"""
Tender - RAG 检索器
"""
from server.db.chromadb import query_chunks
from server.db.sqlite import get_db


def _as_doc_id(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scope_doc_ids(doc_ids: list[int] | None) -> list[int]:
    scoped: list[int] = []
    seen: set[int] = set()
    for raw in doc_ids or []:
        doc_id = _as_doc_id(raw)
        if doc_id is None or doc_id in seen:
            continue
        seen.add(doc_id)
        scoped.append(doc_id)
    return scoped


def _chroma_where(doc_ids: list[int]) -> dict | None:
    if not doc_ids:
        return None
    if len(doc_ids) == 1:
        return {"doc_id": doc_ids[0]}
    return {"doc_id": {"$in": doc_ids}}


def retrieve(query: str, top_k: int = 5, doc_ids: list[int] | None = None) -> list[dict]:
    """检索相关切片

    Args:
        query: 用户问题
        top_k: 返回数量
        doc_ids: 可选，限定文档范围。限定时在向量库内过滤，
            而不是先取全局前几条再丢掉其他文档。

    Returns:
        [{"id", "text", "metadata", "score", "doc_id", "filename"}]
    """
    scoped = _scope_doc_ids(doc_ids)
    where = _chroma_where(scoped)
    fetch_k = top_k if where else top_k * 2
    if where:
        chunks = query_chunks(query, top_k=fetch_k, where=where)
    else:
        chunks = query_chunks(query, top_k=fetch_k)

    # 获取文档名（一次性批量查询，避免 N+1）
    conn = get_db()
    cur = conn.cursor()

    doc_ids_in_chunks = set()
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        did = _as_doc_id(meta.get("doc_id")) if isinstance(meta, dict) else None
        if did is not None:
            doc_ids_in_chunks.add(did)

    filename_map = {}
    if doc_ids_in_chunks:
        placeholders = ",".join("?" * len(doc_ids_in_chunks))
        cur.execute(f"SELECT id, filename FROM documents WHERE id IN ({placeholders})", list(doc_ids_in_chunks))
        filename_map = {row["id"]: row["filename"] for row in cur.fetchall()}

    allowed = set(scoped)
    results = []
    seen = set()
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        doc_id = _as_doc_id(meta.get("doc_id"))
        if allowed and doc_id not in allowed:
            continue
        if chunk["id"] in seen:
            continue
        seen.add(chunk["id"])

        results.append({
            "id": chunk["id"],
            "text": chunk["text"],
            "metadata": meta,
            "score": 1 - chunk.get("distance", 0),  # 距离转相似度
            "doc_id": doc_id,
            "filename": filename_map.get(doc_id, "unknown"),
        })

        if len(results) >= top_k:
            break

    conn.close()
    return results


def build_context(retrieved: list[dict]) -> str:
    """将检索结果组装成上下文"""
    if not retrieved:
        return ""
    
    parts = []
    for i, r in enumerate(retrieved, 1):
        parts.append(
            f"[参考{i}] {r['filename']}\n{r['text']}"
        )
    return "\n\n".join(parts)
