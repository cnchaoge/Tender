"""
Tender - 知识库管理 API
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from server.config import UPLOADS_DIR
from server.db.chromadb import delete_doc_chunks
from server.db.sqlite import get_db
from server.deps import get_current_user
from server.models import Chunk, Document, Resp
from server.workers.document_worker import cleanup_partial_document, write_lock
from server.workers.executor import schedule_document

router = APIRouter(prefix="/api/kb", tags=["知识库"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

_UPLOAD_SUFFIXES = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt", ".jpg", ".jpeg", ".png",
}
_FOLDER_SUFFIXES = [".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt"]


def _file_type_for_suffix(suffix: str) -> str:
    file_type = suffix.lstrip(".")
    if file_type in {"jpg", "jpeg", "png"}:
        return "image"
    return file_type


def _insert_pending_document(filename: str, file_type: str, file_path: str, file_size: int) -> Document:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count) VALUES (?, ?, ?, ?, ?, ?)",
            (filename, file_type, file_path, file_size, "pending", 0),
        )
        doc_id = cur.lastrowid
        conn.commit()
        cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        return Document(**dict(cur.fetchone()))
    finally:
        conn.close()


@router.get("/documents", response_model=list[Document])
def list_documents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [Document(**dict(r)) for r in rows]


def _queue_folder(folder: Path) -> list[Document]:
    """Insert pending rows for new files and hand each one to the worker pool."""
    files: list[Path] = []
    for ext in _FOLDER_SUFFIXES:
        for file_path in folder.rglob(f"*{ext}"):
            if "node_modules" in file_path.parts or "__pycache__" in file_path.parts:
                continue
            files.append(file_path)

    if not files:
        raise HTTPException(status_code=400, detail="文件夹中没有找到支持的文档（.pdf/.docx/.xlsx/.md/.txt）")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT filename FROM documents")
        existing_filenames = {row["filename"] for row in cur.fetchall()}
    finally:
        conn.close()

    results: list[Document] = []
    errors = 0
    for file_path in files:
        if file_path.name in existing_filenames:
            continue
        try:
            doc = _insert_pending_document(
                file_path.name,
                _file_type_for_suffix(file_path.suffix.lower()),
                str(file_path),
                file_path.stat().st_size,
            )
        except Exception:
            logger.exception("failed to queue %s", file_path)
            errors += 1
            continue
        existing_filenames.add(file_path.name)
        # file_path is not on the Document model; schedule with the real path.
        try:
            schedule_document(doc.id, str(file_path))
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


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    """保存文件后立即返回 pending。OCR、切片、向量化在独立线程池中完成。"""
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, chunk_count FROM documents WHERE filename = ?",
            (filename,),
        )
        existing = cur.fetchone()
    finally:
        conn.close()
    if existing:
        return {
            "doc_id": existing["id"],
            "status": existing["status"],
            "chunk_count": existing["chunk_count"] or 0,
            "duplicate": True,
        }

    saved_path = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    async with aiofiles.open(saved_path, "wb") as handle:
        while True:
            blob = await file.read(1024 * 1024)
            if not blob:
                break
            size += len(blob)
            await handle.write(blob)

    try:
        doc = _insert_pending_document(filename, _file_type_for_suffix(suffix), str(saved_path), size)
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise

    doc = _queue_saved_document_at(doc, str(saved_path))
    return {"doc_id": doc.id, "status": doc.status, "chunk_count": doc.chunk_count or 0}


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
    with write_lock:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="文档不存在")

        try:
            os.remove(row["file_path"])
        except Exception:
            pass

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
