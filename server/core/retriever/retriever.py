"""
ClawOS X - RAG 检索器
"""
from server.db.chromadb import query_chunks
from server.db.sqlite import get_db


def retrieve(query: str, top_k: int = 5, doc_ids: list[int] = None) -> list[dict]:
    """检索相关切片
    
    Args:
        query: 用户问题
        top_k: 返回数量
        doc_ids: 可选，限定文档范围
    
    Returns:
        [{"id", "text", "metadata", "score", "doc_id", "filename"}]
    """
    chunks = query_chunks(query, top_k=top_k * 2 if not doc_ids else top_k)
    
    # 获取文档名
    conn = get_db()
    cur = conn.cursor()
    
    results = []
    seen = set()
    for chunk in chunks:
        doc_id = chunk["metadata"].get("doc_id")
        if doc_ids and doc_id not in doc_ids:
            continue
        if chunk["id"] in seen:
            continue
        seen.add(chunk["id"])
        
        cur.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        filename = row["filename"] if row else "unknown"
        
        results.append({
            "id": chunk["id"],
            "text": chunk["text"],
            "metadata": chunk["metadata"],
            "score": 1 - chunk.get("distance", 0),  # 距离转相似度
            "doc_id": doc_id,
            "filename": filename,
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
            f"[参考{i}] {r["filename"]}\n{r["text"]}"
        )
    return "\n\n".join(parts)
