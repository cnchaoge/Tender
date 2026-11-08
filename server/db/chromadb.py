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

LEGACY_COLLECTION = "documents"


def get_chroma_client():
    global _client, _collection
    if _client is None:
        _collection = None
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
    return _client


def invalidate_collection_cache():
    global _collection
    _collection = None


def open_collection(name: str, metadata: dict | None = None):
    """打开或创建指定集合。已存在时不因为元数据不同而重建。"""
    client = get_chroma_client()
    try:
        return client.get_collection(name)
    except Exception:
        return client.create_collection(
            name=name,
            metadata=metadata or {"description": "Tender document chunks"},
        )


def get_collection():
    """当前可写集合。身份一致时用 active，否则仍是遗留的 documents。"""
    global _collection
    name = LEGACY_COLLECTION
    try:
        from server.domain.documents.index_build import readable_collection_name

        preferred = readable_collection_name()
        if preferred:
            name = preferred
    except Exception:
        name = LEGACY_COLLECTION
    if _collection is not None:
        # 测试可以塞进一个没有 name 的集合替身。真实集合的 name 必须和当前索引一致。
        current = getattr(_collection, "name", None)
        if current is None or current == name:
            return _collection
    _collection = open_collection(name)
    return _collection


def add_chunks(doc_id: int, chunks: list[dict], collection_name: str | None = None):
    """批量添加切片到向量库（需要外部已 embed 的 vectors）"""
    if collection_name:
        collection = open_collection(collection_name)
    else:
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

    from server.domain.documents.index_build import assert_retrieval_identity

    assert_retrieval_identity()
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
    """删除某个文档在各集合中的切片。打不开的退役集合忽略。"""
    from server.domain.documents.index_build import collection_names

    client = get_chroma_client()
    for name in collection_names():
        try:
            collection = client.get_collection(name)
        except Exception:
            continue
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:
            continue


def reset():
    """重置向量库（测试用）"""
    client = get_chroma_client()
    try:
        client.delete_collection(LEGACY_COLLECTION)
    except Exception:
        pass
    global _collection
    _collection = None
