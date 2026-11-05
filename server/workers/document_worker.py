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

    vectors = get_embedder().embed(pieces)
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
    add_chunks(doc_id, records)


def process_document(doc_id: int, file_path: str) -> None:
    try:
        with write_lock:
            if not _document_exists(doc_id):
                return
            _set_status(doc_id, "processing")
        logger.info("doc_id=%s processing %s", doc_id, file_path)

        text, _pages = parse_file(file_path)
        pieces = chunk_text(text or "")

        with write_lock:
            if not _document_exists(doc_id):
                discard_partial_artifacts(doc_id)
                return
            _store_chunks_and_vectors(doc_id, pieces)
            if not _document_exists(doc_id):
                discard_partial_artifacts(doc_id)
                return
            _set_status(doc_id, "ready", len(pieces))
        logger.info("doc_id=%s ready chunks=%s", doc_id, len(pieces))
    except Exception:
        logger.exception("doc_id=%s failed", doc_id)
        try:
            with write_lock:
                cleanup_partial_document(doc_id)
        except Exception:
            logger.exception("doc_id=%s cleanup failed", doc_id)


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

    queued = 0
    for row in rows:
        doc_id = row["id"]
        file_path = row["file_path"]
        try:
            with write_lock:
                discard_partial_artifacts(doc_id)
                _set_status(doc_id, "pending", 0)
        except Exception:
            logger.exception("failed to reset doc_id=%s", doc_id)
            continue
        schedule_document(doc_id, file_path)
        queued += 1
    if queued:
        logger.info("requeued %s incomplete documents", queued)
    return queued


if __name__ == "__main__":
    process_document(int(sys.argv[1]), sys.argv[2])
