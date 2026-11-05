"""
Tender - ChromaDB 向量数据库
"""
import chromadb
from chromadb.config import Settings
from server.config import get_settings, BASE_DIR
from server.core.embedder.embedder import get_embedder

settings = get_settings()

_client = None
_collection = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
    return _client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="documents",
            metadata={"description": "Tender document chunks"}
        )
    return _collection


def add_chunks(doc_id: int, chunks: list[dict]):
    """批量添加切片到向量库（需要外部已 embed 的 vectors）"""
    collection = get_collection()
    ids = [f"doc{doc_id}_chunk{i}" for i, c in enumerate(chunks)]
    documents = [c["text"] for c in chunks]
    embeddings = [c["vector"] for c in chunks]
    metadatas = [{
        "doc_id": doc_id,
        "chunk_index": c["chunk_index"],
        **{k: v for k, v in c.get("metadata", {}).items()}
    } for i, c in enumerate(chunks)]

    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def _query_rows(results: dict) -> list[dict]:
    ids = (results or {}).get("ids") or []
    if not ids or not ids[0]:
        return []
    documents = (results.get("documents") or [[]])[0] or []
    metadatas = (results.get("metadatas") or [[]])[0] or []
    distances = (results.get("distances") or [[]])[0] if results.get("distances") else []
    rows = []
    for i, chunk_id in enumerate(ids[0]):
        meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
        rows.append({
            "id": chunk_id,
            "text": documents[i] if i < len(documents) else "",
            "metadata": meta,
            "distance": distances[i] if i < len(distances) else 0,
        })
    return rows


def _is_result_window_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "n_results" in message or "greater than" in message or "not enough" in message


def query_chunks(query_text: str, top_k: int = 5, where: dict | None = None) -> list[dict]:
    """检索相似切片。

    ``where`` 传给 Chroma，用来把检索限制在指定文档内。
    只取全局前几条再丢弃其他文档时，目标文档里真正相似的章节会排不进来。
    """
    if top_k < 1 or not str(query_text or "").strip():
        return []

    collection = get_collection()
    embedder = get_embedder()
    query_vector = embedder.embed_one(query_text)
    try:
        total = int(collection.count() or 0)
    except Exception:
        total = top_k
    if total <= 0:
        return []

    def _query(n_results: int) -> dict:
        kwargs = {"query_embeddings": [query_vector], "n_results": n_results}
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    # 过滤后的条数可能少于请求数，Chroma 会拒绝过大的 n_results。
    attempt = min(int(top_k), total)
    while attempt >= 1:
        try:
            return _query_rows(_query(attempt))
        except Exception as exc:
            if _is_result_window_error(exc) and attempt > 1:
                attempt = max(1, attempt // 2)
                continue
            if where and _is_result_window_error(exc):
                return []
            raise
    return []


def delete_doc_chunks(doc_id: int):
    """删除某个文档的所有切片"""
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})


def reset():
    """重置向量库（测试用）"""
    client = get_chroma_client()
    client.delete_collection("documents")
    global _collection
    _collection = None
