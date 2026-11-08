"""
Tender - 知识库管理 API
"""
import asyncio
import logging
import sqlite3
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from server.config import get_settings
from server.db.chromadb import delete_doc_chunks
from server.db.sqlite import get_db
from server.deps import get_current_user
from server.domain.documents.files import (
    copy_into_library,
    incoming_path,
    move_into_library,
    relative_to_data,
    remove_managed_tree,
    resolve_stored_path,
    sha256_file,
)
from server.models import Chunk, Document, Resp
from server.workers.document_worker import cleanup_partial_document, write_lock
from server.workers.executor import schedule_document

router = APIRouter(prefix="/api/kb", tags=["知识库"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

_UPLOAD_SUFFIXES = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt", ".jpg", ".jpeg", ".png",
}
_FOLDER_SUFFIXES = [".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt"]


def max_upload_bytes() -> int:
    return int(get_settings().MAX_FILE_SIZE or 0) * 1024 * 1024


def _file_type_for_suffix(suffix: str) -> str:
    file_type = suffix.lstrip(".")
    if file_type in {"jpg", "jpeg", "png"}:
        return "image"
    return file_type


def _size_error() -> HTTPException:
    limit = int(get_settings().MAX_FILE_SIZE or 0)
    return HTTPException(status_code=413, detail=f"文件超过大小限制（{limit}MB）")


def _lookup_duplicate(filename: str, digest: str) -> sqlite3.Row | None:
    """新文件按内容哈希去重。还没有哈希的旧行才继续按文件名视为同一份。"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, status, chunk_count, file_path
               FROM documents
               WHERE content_sha256=?
               ORDER BY id
               LIMIT 1""",
            (digest,),
        )
        found = cur.fetchone()
        if found is not None:
            return found
        cur.execute(
            """SELECT id, status, chunk_count, file_path
               FROM documents
               WHERE filename=? AND (content_sha256 IS NULL OR content_sha256='')
               ORDER BY id
               LIMIT 1""",
            (filename,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _duplicate_payload(row: sqlite3.Row) -> dict:
    return {
        "doc_id": row["id"],
        "status": row["status"],
        "chunk_count": row["chunk_count"] or 0,
        "duplicate": True,
        "file_path": str(resolve_stored_path(row["file_path"])),
    }


def _insert_pending_document(
    filename: str,
    file_type: str,
    file_size: int,
    digest: str,
) -> Document:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count,
                scope, storage, content_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, file_type, "", file_size, "pending", 0, "library", "managed", digest),
        )
        doc_id = cur.lastrowid
        conn.commit()
        cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        return Document(**dict(cur.fetchone()))
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    finally:
        conn.close()


def _store_managed_path(doc_id: int, path: Path, file_size: int) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE documents
               SET file_path=?, file_size=?, storage='managed', scope='library',
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (relative_to_data(path), file_size, doc_id),
        )
        conn.commit()
    finally:
        conn.close()


@router.get("/documents", response_model=list[Document])
def list_documents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM documents
           WHERE COALESCE(scope, 'library') != 'project'
           ORDER BY created_at DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    return [Document(**dict(r)) for r in rows]


def _queue_folder(folder: Path) -> list[Document]:
    """复制进资料库后立即返回 pending。不把用户磁盘上的原路径当作唯一副本。"""
    files: list[Path] = []
    for ext in _FOLDER_SUFFIXES:
        for file_path in folder.rglob(f"*{ext}"):
            if "node_modules" in file_path.parts or "__pycache__" in file_path.parts:
                continue
            files.append(file_path)

    if not files:
        raise HTTPException(status_code=400, detail="文件夹中没有找到支持的文档（.pdf/.docx/.xlsx/.md/.txt）")

    results: list[Document] = []
    errors = 0
    skipped_large = 0
    for file_path in files:
        try:
            size = file_path.stat().st_size
        except OSError:
            logger.exception("failed to stat %s", file_path)
            errors += 1
            continue
        if max_upload_bytes() > 0 and size > max_upload_bytes():
            skipped_large += 1
            continue
        try:
            digest = sha256_file(file_path)
        except OSError:
            logger.exception("failed to hash %s", file_path)
            errors += 1
            continue
        if _lookup_duplicate(file_path.name, digest) is not None:
            continue
        doc: Document | None = None
        try:
            doc = _insert_pending_document(
                file_path.name,
                _file_type_for_suffix(file_path.suffix.lower()),
                size,
                digest,
            )
            dest = copy_into_library(doc.id, file_path)
            _store_managed_path(doc.id, dest, size)
        except sqlite3.IntegrityError:
            continue
        except Exception:
            logger.exception("failed to queue %s", file_path)
            errors += 1
            if doc is not None:
                try:
                    with write_lock:
                        cleanup_partial_document(doc.id)
                    remove_managed_tree(doc.id)
                except Exception:
                    logger.exception("cleanup after folder copy failure doc_id=%s", doc.id)
            continue
        try:
            schedule_document(doc.id, str(dest))
        except Exception:
            logger.exception("failed to schedule folder doc_id=%s", doc.id)
            try:
                with write_lock:
                    cleanup_partial_document(doc.id)
            except Exception:
                logger.exception("cleanup after folder schedule failure doc_id=%s", doc.id)
            doc.status = "failed"
            doc.chunk_count = 0
        results.append(doc)
    if not results and skipped_large and not errors:
        raise _size_error()
    if not results and errors:
        raise HTTPException(status_code=500, detail="所有文件均未能加入处理队列")
    return results


@router.get("/folder", response_model=list[Document])
async def add_folder(folder_path: str):
    """扫描文件夹并立即返回 pending 文档，解析和向量化在后台完成。"""
    folder = Path(folder_path)
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail="文件夹不存在")
    # Directory walk is synchronous; keep it off the event loop. OCR/embed is
    # not done here — schedule_document only queues the worker pool.
    return await asyncio.to_thread(_queue_folder, folder)


async def _write_limited(file: UploadFile, dest: Path) -> tuple[str, int]:
    """边写边算哈希。超过上限时停写并删掉半截文件。"""
    import hashlib

    limit = max_upload_bytes()
    digest = hashlib.sha256()
    size = 0
    async with aiofiles.open(dest, "wb") as handle:
        while True:
            blob = await file.read(1024 * 1024)
            if not blob:
                break
            size += len(blob)
            if limit > 0 and size > limit:
                raise _size_error()
            digest.update(blob)
            await handle.write(blob)
    return digest.hexdigest(), size


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    """保存受管副本后立即返回 pending。OCR、切片、向量化在独立线程池中完成。"""
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    tmp_path = incoming_path(suffix)
    try:
        digest, size = await _write_limited(file, tmp_path)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    existing = _lookup_duplicate(filename, digest)
    if existing is not None:
        tmp_path.unlink(missing_ok=True)
        return _duplicate_payload(existing)

    doc: Document | None = None
    try:
        doc = _insert_pending_document(filename, _file_type_for_suffix(suffix), size, digest)
        dest = move_into_library(doc.id, tmp_path, suffix)
        _store_managed_path(doc.id, dest, size)
    except sqlite3.IntegrityError:
        tmp_path.unlink(missing_ok=True)
        raced = _lookup_duplicate(filename, digest)
        if raced is not None:
            return _duplicate_payload(raced)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        if doc is not None:
            try:
                remove_managed_tree(doc.id)
                with write_lock:
                    cleanup_partial_document(doc.id)
            except Exception:
                logger.exception("cleanup after upload failure doc_id=%s", doc.id)
        raise

    doc = _queue_saved_document_at(doc, str(dest))
    return {
        "doc_id": doc.id,
        "status": doc.status,
        "chunk_count": doc.chunk_count or 0,
        "file_path": str(dest),
    }


def _queue_saved_document_at(doc: Document, file_path: str) -> Document:
    try:
        schedule_document(doc.id, file_path)
    except Exception:
        logger.exception("failed to schedule doc_id=%s", doc.id)
        try:
            with write_lock:
                cleanup_partial_document(doc.id)
        except Exception:
            logger.exception("cleanup after schedule failure doc_id=%s", doc.id)
        doc.status = "failed"
        doc.chunk_count = 0
    return doc


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int):
    """删除受管副本、切片和向量。不删除资料库以外的路径。"""
    with write_lock:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT id, file_path, storage FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="文档不存在")

        try:
            remove_managed_tree(doc_id)
        except Exception:
            logger.exception("managed delete failed for doc_id=%s", doc_id)

        try:
            delete_doc_chunks(doc_id)
        except Exception:
            logger.exception("chroma delete failed for doc_id=%s", doc_id)
        cur.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        cur.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
    return Resp(message="删除成功")


@router.get("/documents/{doc_id}/chunks", response_model=list[Chunk])
def get_chunks(doc_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,))
    rows = cur.fetchall()
    conn.close()
    return [Chunk(**dict(r), metadata={}) for r in rows]


@router.get("/documents/{doc_id}/status")
def get_doc_status(doc_id: int):
    """查询文档处理状态。前端轮询直到 ready 或 failed。"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, status, chunk_count FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"doc_id": row["id"], "status": row["status"], "chunk_count": row["chunk_count"] or 0}
