"""Process one knowledge-base document: parse, chunk, embed, store.

Status moves pending -> processing -> ready, or failed. On failure, SQLite
chunks and Chroma vectors for that doc_id are removed so the two stores
cannot disagree.
"""
from __future__ import annotations

import logging
import sys
import threading

from server.core.chunker.chunker import chunk_text
from server.core.embedder.embedder import get_embedder
from server.core.parser.document import parse_file
from server.db.chromadb import add_chunks, delete_doc_chunks
from server.db.sqlite import get_db
from server.domain.documents.files import (
    read_extracted_text,
    resolve_stored_path,
    write_extracted_text,
)
from server.domain.documents.index_build import IndexIdentityError, prepare_embedding_target, record_dimension

logger = logging.getLogger(__name__)

# Serializes SQLite chunk writes and Chroma updates. Parse/OCR stays outside
# the lock so two documents can be read at once without blocking the API.
write_lock = threading.Lock()


def _set_status(doc_id: int, status: str, chunk_count: int | None = None) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        if chunk_count is None:
            cur.execute(
                "UPDATE documents SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, doc_id),
            )
        else:
            cur.execute(
                "UPDATE documents SET status=?, chunk_count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, chunk_count, doc_id),
            )
        conn.commit()
    finally:
        conn.close()


def _document_exists(doc_id: int) -> bool:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def discard_partial_artifacts(doc_id: int) -> None:
    """Remove chunks and vectors for doc_id. Does not change document status."""
    try:
        delete_doc_chunks(doc_id)
    except Exception:
        logger.exception("chroma cleanup failed for doc_id=%s", doc_id)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def cleanup_partial_document(doc_id: int) -> None:
    """Drop partial chunks/vectors and mark the document failed."""
    discard_partial_artifacts(doc_id)
    _set_status(doc_id, "failed", 0)


def _store_chunks_and_vectors(doc_id: int, pieces: list[str]) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        cur.execute(
            "UPDATE documents SET chunk_count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (len(pieces), doc_id),
        )
        for index, content in enumerate(pieces):
            cur.execute(
                "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
                (doc_id, index, content, "{}"),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if not pieces:
        return

    from server.domain.jobs.runtime import raise_if_cancelled

    collection_name = prepare_embedding_target()
    raise_if_cancelled()
    batch_size = 32
    if len(pieces) <= batch_size:
        vectors = get_embedder().embed(pieces)
    else:
        vectors = []
        for start in range(0, len(pieces), batch_size):
            raise_if_cancelled()
            part = pieces[start:start + batch_size]
            vectors.extend(get_embedder().embed(part))
    if len(vectors) != len(pieces):
        raise RuntimeError(
            f"embedding count {len(vectors)} != chunk count {len(pieces)} for doc_id={doc_id}"
        )
    records = [
        {
            "text": content,
            "chunk_index": index,
            "metadata": {},
            "vector": vector,
        }
        for index, (content, vector) in enumerate(zip(pieces, vectors))
    ]
    add_chunks(doc_id, records, collection_name=collection_name)
    if vectors:
        record_dimension(len(vectors[0]))


def _load_text(doc_id: int, file_path: str) -> str:
    """优先读已抽出的文本，避免重新解析 PDF。没有时才解析原件并写下来。"""
    extracted = read_extracted_text(doc_id)
    if extracted is not None:
        return extracted
    text, _pages = parse_file(file_path)
    relpath = write_extracted_text(doc_id, text or "")
    _remember_extracted(doc_id, relpath)
    return text or ""


def _remember_extracted(doc_id: int, relpath: str) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE documents SET extracted_relpath=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (relpath, doc_id),
        )
        conn.commit()
    finally:
        conn.close()


def process_document(doc_id: int, file_path: str, on_progress=None) -> str:
    """解析、切块、嵌入。返回 ready / failed / cancelled。

    直接调用时行为与以前一致。作业运行器传入 on_progress，并在批次之间看取消标记。
    """
    from server.domain.jobs.store import JobCancelled

    def report(progress: int, message: str) -> None:
        if on_progress is not None:
            on_progress(progress, message)

    try:
        with write_lock:
            if not _document_exists(doc_id):
                return "cancelled"
            _set_status(doc_id, "processing")
        report(20, "正在解析")
        resolved = str(resolve_stored_path(file_path))
        logger.info("doc_id=%s processing %s", doc_id, resolved)

        text = _load_text(doc_id, resolved)
        pieces = chunk_text(text or "")
        report(40, "正在切块")

        with write_lock:
            if not _document_exists(doc_id):
                discard_partial_artifacts(doc_id)
                return "cancelled"
            try:
                report(70, "正在嵌入")
                _store_chunks_and_vectors(doc_id, pieces)
            except JobCancelled:
                raise
            except IndexIdentityError:
                logger.exception("doc_id=%s index identity mismatch", doc_id)
                try:
                    delete_doc_chunks(doc_id)
                except Exception:
                    logger.exception("doc_id=%s vector delete after identity mismatch failed", doc_id)
                if _document_exists(doc_id):
                    _set_status(doc_id, "failed", len(pieces))
                return "failed"
            if not _document_exists(doc_id):
                discard_partial_artifacts(doc_id)
                return "cancelled"
            _set_status(doc_id, "ready", len(pieces))
        report(100, "完成")
        logger.info("doc_id=%s ready chunks=%s", doc_id, len(pieces))
        return "ready"
    except JobCancelled:
        logger.info("doc_id=%s cancelled", doc_id)
        try:
            with write_lock:
                discard_partial_artifacts(doc_id)
                if _document_exists(doc_id):
                    _set_status(doc_id, "cancelled", 0)
        except Exception:
            logger.exception("doc_id=%s cancel cleanup failed", doc_id)
        raise
    except Exception:
        logger.exception("doc_id=%s failed", doc_id)
        try:
            with write_lock:
                cleanup_partial_document(doc_id)
        except Exception:
            logger.exception("doc_id=%s cleanup failed", doc_id)
        return "failed"


def requeue_incomplete_documents() -> int:
    """After a restart, discard partial writes and schedule pending/processing rows again."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, file_path FROM documents WHERE status IN ('pending', 'processing')"
        )
        rows = list(cur.fetchall())
    finally:
        conn.close()

    from server.workers.executor import schedule_document

    prepared = []
    for row in rows:
        doc_id = row["id"]
        file_path = str(resolve_stored_path(row["file_path"]))
        try:
            with write_lock:
                discard_partial_artifacts(doc_id)
                _set_status(doc_id, "pending", 0)
        except Exception:
            logger.exception("failed to reset doc_id=%s", doc_id)
            continue
        prepared.append((doc_id, file_path))
    # 全部清完再入队，避免运行器先跑起来又被下一轮清掉半成品。
    queued = 0
    for doc_id, file_path in prepared:
        schedule_document(doc_id, file_path)
        queued += 1
    if queued:
        logger.info("requeued %s incomplete documents", queued)
    return queued


if __name__ == "__main__":
    process_document(int(sys.argv[1]), sys.argv[2])
