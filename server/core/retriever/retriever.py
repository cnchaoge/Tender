"""
Tender - RAG 检索器
"""
from fastapi import HTTPException

from server.db.chromadb import query_chunks
from server.db.sqlite import get_db
from server.domain.documents.index_build import IndexIdentityError


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


def _library_ready_ids(cur) -> list[int] | None:
    """全局问答的文档范围。没有 scope 列时返回 None，保持旧的不筛选行为。"""
    cur.execute("PRAGMA table_info(documents)")
    columns = {row[1] for row in cur.fetchall()}
    if "scope" not in columns:
        return None
    if "status" in columns:
        cur.execute(
            """SELECT id FROM documents
               WHERE COALESCE(scope, 'library') = 'library' AND status = 'ready'"""
        )
    else:
        cur.execute(
            "SELECT id FROM documents WHERE COALESCE(scope, 'library') = 'library'"
        )
    return [int(row["id"]) for row in cur.fetchall()]


def retrieve(query: str, top_k: int = 5, doc_ids: list[int] | None = None) -> list[dict]:
    """检索相关切片。

    未指定文档时只返回 scope=library 且 status=ready 的资料。
    招标文件 scope=project 不进入全局问答。调用方显式传入 doc_ids 时
    （例如生成本项目标书）仍可以检索这些文档，包括该项目自己的招标文件。

    Args:
        query: 用户问题
        top_k: 返回数量
        doc_ids: 可选，限定文档范围。限定时在向量库内过滤，
            而不是先取全局前几条再丢掉其他文档。

    Returns:
        [{"id", "text", "metadata", "score", "doc_id", "filename"}]
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        explicit = _scope_doc_ids(doc_ids)
        if explicit:
            scoped = explicit
        else:
            library_ids = _library_ready_ids(cur)
            if library_ids is None:
                scoped = []
            elif not library_ids:
                return []
            else:
                scoped = library_ids

        where = _chroma_where(scoped) if scoped else None
        fetch_k = top_k if where else top_k * 2
        try:
            if where:
                chunks = query_chunks(query, top_k=fetch_k, where=where)
            else:
                chunks = query_chunks(query, top_k=fetch_k)
        except IndexIdentityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        doc_ids_in_chunks = set()
        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            did = _as_doc_id(meta.get("doc_id")) if isinstance(meta, dict) else None
            if did is not None:
                doc_ids_in_chunks.add(did)

        filename_map = {}
        if doc_ids_in_chunks:
            placeholders = ",".join("?" * len(doc_ids_in_chunks))
            cur.execute(
                f"SELECT id, filename FROM documents WHERE id IN ({placeholders})",
                list(doc_ids_in_chunks),
            )
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
        return results
    finally:
        conn.close()


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
