"""
ClawOS X - 知识库管理 API
"""
import os
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from server.config import UPLOADS_DIR, CHUNKS_DIR, get_settings
from server.db.sqlite import get_db
from server.db.chromadb import add_chunks, delete_doc_chunks
from server.core.parser.document import parse_file, get_file_type
from server.core.chunker.chunker import chunk_text
from server.core.embedder.embedder import get_embedder
from server.models import Document, Chunk, Resp

router = APIRouter(prefix="/api/kb", tags=["知识库"])

settings = get_settings()


@router.get("/documents", response_model=list[Document])
def list_documents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [Document(**dict(r)) for r in rows]


@router.get("/folder", response_model=list[Document])
async def add_folder(folder_path: str):
    """扫描指定文件夹，将所有支持的文件加入知识库"""
    folder = Path(folder_path)
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail="文件夹不存在")

    supported = [".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt"]
    files = []
    for ext in supported:
        # 排除 node_modules 和 __pycache__
        for f in folder.rglob(f"*{ext}"):
            if "node_modules" in f.parts or "__pycache__" in f.parts:
                continue
            files.append(f)

    if not files:
        raise HTTPException(status_code=400, detail="文件夹中没有找到支持的文档（.pdf/.docx/.xlsx/.md/.txt）")

    # 查询已有文件（去重：同名已存在则跳过）
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT filename FROM documents")
    existing_filenames = {row["filename"] for row in cur.fetchall()}
    conn.close()

    results = []
    skipped = 0
    for file_path in files:
        # 同名文件已存在则跳过（与单文件上传保持一致）
        if file_path.name in existing_filenames:
            skipped += 1
            continue

        try:
            text, page_info = parse_file(str(file_path))
            chunks = chunk_text(text)

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count) VALUES (?, ?, ?, ?, ?, ?)",
                (file_path.name, get_file_type(str(file_path)), str(file_path), file_path.stat().st_size, "ready", len(chunks))
            )
            doc_id = cur.lastrowid

            chunk_records = []
            for i, chunk_text_content in enumerate(chunks):
                cur.execute(
                    "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
                    (doc_id, i, chunk_text_content, "{}")
                )
                chunk_records.append({
                    "text": chunk_text_content,
                    "chunk_index": i,
                    "metadata": {}
                })

            # Embed 所有 chunk 并加入向量库
            embedder = get_embedder()
            texts = [r["text"] for r in chunk_records]
            vectors = embedder.embed(texts)
            for r, v in zip(chunk_records, vectors):
                r["vector"] = v

            add_chunks(doc_id, chunk_records)
            conn.commit()

            cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            doc = Document(**dict(cur.fetchone()))
            results.append(doc)
            conn.close()
        except Exception as e:
            print(f"解析失败 {file_path}: {e}")
            continue

    if not results and not skipped:
        raise HTTPException(status_code=500, detail="所有文件解析均失败")
    return results


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    """上传单个文件到知识库"""
    import aiofiles

    # 保存文件
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".md", ".txt", ".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    # 去重：同名文件已存在则直接返回
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, file_path FROM documents WHERE filename = ?", (file.filename,))
    existing = cur.fetchone()
    if existing:
        conn.close()
        return {"file_path": existing["file_path"], "doc_id": existing["id"], "chunk_count": 0, "duplicate": True}

    saved_path = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    async with aiofiles.open(saved_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # 解析
    text, _ = parse_file(str(saved_path))
    chunks = chunk_text(text)

    # 存入 SQLite
    file_type = suffix.lstrip(".")
    if file_type in ("jpg", "jpeg", "png"):
        file_type = "image"
    cur.execute(
        "INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count) VALUES (?, ?, ?, ?, ?, ?)",
        (file.filename, file_type, str(saved_path), len(content), "ready", len(chunks))
    )
    doc_id = cur.lastrowid

    chunk_records = []
    for i, chunk_text_content in enumerate(chunks):
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
            (doc_id, i, chunk_text_content, "{}")
        )
        chunk_records.append({"text": chunk_text_content, "chunk_index": i, "metadata": {}})

    # Embed 并加入向量库
    embedder = get_embedder()
    texts = [r["text"] for r in chunk_records]
    vectors = embedder.embed(texts)
    for r, v in zip(chunk_records, vectors):
        r["vector"] = v

    add_chunks(doc_id, chunk_records)
    conn.commit()
    conn.close()

    return {"file_path": str(saved_path), "doc_id": doc_id, "chunk_count": len(chunks)}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除文件
    try:
        os.remove(row["file_path"])
    except Exception:
        pass
    
    # 删除切片
    delete_doc_chunks(doc_id)
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
