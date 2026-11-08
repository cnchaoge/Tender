"""Embedding 索引身份。

同一时间只有一条 active。检索时当前模型必须和它一致，否则拒绝查询，
避免换模型后把旧向量和新向量混在一次结果里。mock 的向量是随机的，
不能标成可供检索的 active。重建只读 SQLite 切片，不重新解析原文，
也不删除已退役的集合。
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from server.config import get_settings
from server.db.sqlite import get_db

logger = logging.getLogger(__name__)

LEGACY_COLLECTION = "documents"
MISMATCH_MESSAGE = "索引与当前模型不一致"
MOCK_MESSAGE = "mock 不能作为可供检索的索引"


class IndexIdentityError(RuntimeError):
    """当前 Embedding 与 active 索引不是同一套。"""

    def __init__(self, message: str = MISMATCH_MESSAGE) -> None:
        super().__init__(message)


class MockIndexError(IndexIdentityError):
    def __init__(self, message: str = MOCK_MESSAGE) -> None:
        super().__init__(message)


class RebuildInProgress(RuntimeError):
    def __init__(self, message: str = "索引正在重建") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    model: str
    dimension: int | None = None


def current_embedding_identity() -> EmbeddingIdentity:
    """读取当前配置。新代码在调用时取设置，不使用导入期快照。"""
    settings = get_settings()
    provider = (settings.EMBED_PROVIDER or "").strip().lower()
    if provider == "ollama":
        model = (settings.OLLAMA_EMBED_MODEL or settings.OLLAMA_MODEL or provider).strip()
    elif provider == "dashscope":
        model = (settings.DASHSCOPE_EMBED_MODEL or provider).strip()
    elif provider == "bge":
        model = (settings.BGE_MODEL_PATH or "bge").strip()
    elif provider == "m3e":
        model = (settings.M3E_MODEL_PATH or "m3e").strip()
    elif provider == "mock":
        model = "mock"
    else:
        model = provider or "unknown"
    return EmbeddingIdentity(provider=provider, model=model or provider)


def assert_retrieval_identity() -> EmbeddingIdentity:
    """身份不一致时抛出，调用方不能继续查询向量。"""
    identity = current_embedding_identity()
    if identity.provider == "mock":
        raise IndexIdentityError(MISMATCH_MESSAGE)
    try:
        active = _fetch_one("active")
    except sqlite3.OperationalError:
        raise IndexIdentityError(MISMATCH_MESSAGE) from None
    if not _matches(active, identity):
        raise IndexIdentityError(MISMATCH_MESSAGE)
    return identity


def readable_collection_name() -> str | None:
    """当前模型可用的集合名。不一致时返回 None，检索不得改去查别的集合。"""
    try:
        identity = current_embedding_identity()
        active = _fetch_one("active")
    except sqlite3.OperationalError:
        return None
    if identity.provider == "mock":
        return None
    if not _matches(active, identity):
        return None
    return active["collection_name"]


def prepare_embedding_target() -> str | None:
    """返回这次写入应该使用的集合。

    mock 不建立 active，写入仍落到遗留集合，但检索不会把它当成有效索引。
    已有别的模型的 active，或遗留集合里已有来源不明的向量时，拒绝写入。
    """
    identity = current_embedding_identity()
    try:
        active = _fetch_one("active")
    except sqlite3.OperationalError:
        return None
    if identity.provider == "mock":
        if active is not None:
            raise IndexIdentityError(MISMATCH_MESSAGE)
        return None
    if active is not None:
        if not _matches(active, identity):
            raise IndexIdentityError(MISMATCH_MESSAGE)
        return active["collection_name"]
    if _legacy_vector_count() > 0:
        raise IndexIdentityError(MISMATCH_MESSAGE)
    return _activate_new(identity, LEGACY_COLLECTION, dimension=None)


def ensure_active_index_if_empty() -> None:
    """空库且当前不是 mock 时，记下当前模型，避免第一次检索被当成身份冲突。"""
    identity = current_embedding_identity()
    if identity.provider == "mock":
        return
    try:
        if _fetch_one("active") is not None or _fetch_one("building") is not None:
            return
    except sqlite3.OperationalError:
        return
    if _legacy_vector_count() > 0:
        return
    _activate_new(identity, LEGACY_COLLECTION, dimension=None)


def recover_interrupted_builds() -> int:
    """进程退出时仍在 building 的重建标为 failed。不自动接着嵌。"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE index_builds
               SET status='failed',
                   error='进程退出时重建未完成',
                   updated_at=CURRENT_TIMESTAMP
               WHERE status='building'"""
        )
        changed = cur.rowcount
        conn.commit()
        return int(changed or 0)
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def index_status() -> dict:
    identity = current_embedding_identity()
    try:
        active = _fetch_one("active")
        building = _fetch_one("building")
    except sqlite3.OperationalError:
        active = None
        building = None
    consistent = identity.provider != "mock" and _matches(active, identity)
    message = ""
    if identity.provider == "mock":
        message = MISMATCH_MESSAGE
    elif not consistent:
        message = MISMATCH_MESSAGE
    return {
        "consistent": consistent,
        "message": message,
        "rebuilding": building is not None,
        "mock": identity.provider == "mock",
        "current": {"embed_provider": identity.provider, "embed_model": identity.model},
        "active": _public_build(active),
        "building": _public_build(building),
    }


def begin_rebuild() -> dict:
    """写入 building 行并交给现有线程池。mock 直接拒绝。"""
    identity = current_embedding_identity()
    if identity.provider == "mock":
        raise MockIndexError(MOCK_MESSAGE)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute("SELECT id FROM index_builds WHERE status='building'")
        if cur.fetchone() is not None:
            conn.rollback()
            raise RebuildInProgress("索引正在重建")
        cur.execute(
            """INSERT INTO index_builds
               (embed_provider, embed_model, dimension, status, collection_name)
               VALUES (?, ?, NULL, 'building', '')""",
            (identity.provider, identity.model),
        )
        build_id = int(cur.lastrowid)
        collection_name = f"documents_b{build_id}"
        cur.execute(
            "UPDATE index_builds SET collection_name=? WHERE id=?",
            (collection_name, build_id),
        )
        conn.commit()
    except (RebuildInProgress, MockIndexError):
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    from server.workers.executor import schedule_reindex

    try:
        schedule_reindex(build_id)
    except Exception:
        _mark_failed(build_id, "未能加入重建队列")
        raise
    return {"id": build_id, "status": "building", "collection_name": collection_name}


def execute_rebuild(build_id: int) -> None:
    """在工作线程里重嵌切片。失败时保留原来的 active，不删除新集合。"""
    from server.workers.document_worker import write_lock

    with write_lock:
        _execute_rebuild_locked(build_id)


def record_dimension(dimension: int) -> None:
    if dimension <= 0:
        return
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE index_builds
               SET dimension=?, updated_at=CURRENT_TIMESTAMP
               WHERE status='active' AND (dimension IS NULL OR dimension=0)""",
            (int(dimension),),
        )
        conn.commit()
    except sqlite3.OperationalError:
        return
    finally:
        conn.close()


def _execute_rebuild_locked(build_id: int) -> None:
    row = _fetch_build(build_id)
    if row is None:
        return
    identity = current_embedding_identity()
    if identity.provider == "mock" or identity.provider != row["embed_provider"] or identity.model != row["embed_model"]:
        _mark_failed(build_id, MOCK_MESSAGE if identity.provider == "mock" else MISMATCH_MESSAGE)
        return

    from server.core.embedder.embedder import get_embedder
    from server.db.chromadb import invalidate_collection_cache, open_collection

    collection_name = row["collection_name"]
    try:
        collection = open_collection(
            collection_name,
            metadata=_collection_metadata(build_id, identity, 0),
        )
        chunks = _load_chunks()
        dimension = _embed_into(collection, chunks, get_embedder())
        _spot_check(collection, chunks)
        _stamp(collection, build_id, identity, dimension)
        _switch_active(build_id, dimension)
        _mark_chunked_documents_ready()
        invalidate_collection_cache()
        logger.info("index build %s active collection=%s chunks=%s", build_id, collection_name, len(chunks))
    except Exception as exc:
        logger.exception("index build %s failed", build_id)
        _mark_failed(build_id, str(exc) or "重建失败")


def _embed_into(collection, chunks: list[dict], embedder) -> int:
    dimension = 0
    batch_size = 32
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        vectors = embedder.embed([item["text"] for item in batch])
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"embedding count {len(vectors)} != chunk count {len(batch)}"
            )
        if vectors:
            dimension = len(vectors[0])
        ids = [_vector_id(item) for item in batch]
        metadatas = [
            {
                "doc_id": int(item["doc_id"]),
                "chunk_index": int(item["chunk_index"]),
            }
            for item in batch
        ]
        collection.upsert(
            ids=ids,
            documents=[item["text"] for item in batch],
            embeddings=vectors,
            metadatas=metadatas,
        )
    return dimension


def _spot_check(collection, chunks: list[dict]) -> None:
    """写入后核对条数，并抽查至少一条能按 id 读回。对不上就不切换 active。"""
    expected = len(chunks)
    try:
        actual = int(collection.count() or 0)
    except Exception as exc:
        raise RuntimeError(f"重建抽查失败：无法读取新集合 ({exc})") from exc
    if actual != expected:
        raise RuntimeError(f"重建抽查失败：集合 {actual} 条，切片 {expected} 条")
    if not chunks:
        return
    sample = chunks[0]
    found = collection.get(ids=[_vector_id(sample)])
    ids = (found or {}).get("ids") or []
    if _vector_id(sample) not in ids:
        raise RuntimeError("重建抽查失败：抽样切片不在新集合中")


def _switch_active(build_id: int, dimension: int | None) -> None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            """UPDATE index_builds
               SET status='retired', updated_at=CURRENT_TIMESTAMP
               WHERE status='active' AND id!=?""",
            (build_id,),
        )
        cur.execute(
            """UPDATE index_builds
               SET status='active',
                   dimension=?,
                   error=NULL,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (dimension or None, build_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _mark_chunked_documents_ready() -> None:
    """身份冲突时切片留在 SQLite、状态是 failed。重建成功后这些文档可以检索。"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE documents
               SET status='ready', updated_at=CURRENT_TIMESTAMP
               WHERE status='failed' AND chunk_count > 0"""
        )
        conn.commit()
    finally:
        conn.close()


def _activate_new(identity: EmbeddingIdentity, collection_name: str, dimension: int | None) -> str:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute("SELECT id, collection_name FROM index_builds WHERE status='active'")
        existing = cur.fetchone()
        if existing is not None:
            conn.commit()
            return existing["collection_name"]
        cur.execute(
            """INSERT INTO index_builds
               (embed_provider, embed_model, dimension, status, collection_name)
               VALUES (?, ?, ?, 'active', ?)""",
            (identity.provider, identity.model, dimension, collection_name),
        )
        build_id = int(cur.lastrowid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _stamp_named(collection_name, build_id, identity, dimension or 0)
    return collection_name


def _stamp_named(collection_name: str, build_id: int, identity: EmbeddingIdentity, dimension: int) -> None:
    try:
        from server.db.chromadb import open_collection

        collection = open_collection(collection_name, metadata=_collection_metadata(build_id, identity, dimension))
        _stamp(collection, build_id, identity, dimension)
    except Exception:
        logger.exception("failed to stamp collection %s", collection_name)


def _stamp(collection, build_id: int, identity: EmbeddingIdentity, dimension: int | None) -> None:
    collection.modify(metadata=_collection_metadata(build_id, identity, dimension or 0))


def _collection_metadata(build_id: int, identity: EmbeddingIdentity, dimension: int) -> dict:
    return {
        "index_build_id": int(build_id),
        "embed_provider": identity.provider,
        "embed_model": identity.model,
        "dimension": int(dimension or 0),
    }


def _load_chunks() -> list[dict]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT doc_id, chunk_index, text
               FROM chunks
               ORDER BY doc_id, chunk_index"""
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _vector_id(item: dict) -> str:
    return f"doc{int(item['doc_id'])}_chunk{int(item['chunk_index'])}"


def _legacy_vector_count() -> int:
    try:
        from server.db.chromadb import open_collection

        return int(open_collection(LEGACY_COLLECTION).count() or 0)
    except Exception:
        return 0


def _matches(row: sqlite3.Row | None, identity: EmbeddingIdentity) -> bool:
    if row is None or identity.provider == "mock":
        return False
    if row["embed_provider"] != identity.provider or row["embed_model"] != identity.model:
        return False
    stored = row["dimension"]
    if stored and identity.dimension and int(stored) != int(identity.dimension):
        return False
    return True


def _fetch_one(status: str) -> sqlite3.Row | None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, embed_provider, embed_model, dimension, status, collection_name, error
               FROM index_builds
               WHERE status=?
               ORDER BY id DESC
               LIMIT 1""",
            (status,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _fetch_build(build_id: int) -> sqlite3.Row | None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, embed_provider, embed_model, dimension, status, collection_name
               FROM index_builds WHERE id=?""",
            (build_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _mark_failed(build_id: int, error: str) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE index_builds
               SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='building'""",
            (error[:500], build_id),
        )
        conn.commit()
    finally:
        conn.close()


def _public_build(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "embed_provider": row["embed_provider"],
        "embed_model": row["embed_model"],
        "dimension": row["dimension"],
        "status": row["status"],
        "collection_name": row["collection_name"],
        "error": row["error"],
    }


def collection_names() -> list[str]:
    """删除向量时要覆盖的集合，包含已退役的，避免只删当前这一套。"""
    names = [LEGACY_COLLECTION]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT collection_name FROM index_builds WHERE collection_name!=''")
        for row in cur.fetchall():
            name = row["collection_name"]
            if name and name not in names:
                names.append(name)
    except sqlite3.OperationalError:
        return names
    finally:
        conn.close()
    return names
