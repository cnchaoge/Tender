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


def query_chunks(query_text: str, top_k: int = 5) -> list[dict]:
    """检索相似切片"""
    collection = get_collection()
    embedder = get_embedder()
    query_vector = embedder.embed_one(query_text)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k
    )
    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if "distances" in results else 0,
        }
        for i in range(len(results["ids"][0]))
    ]


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
