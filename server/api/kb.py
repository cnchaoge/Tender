"""
ClawOS X - 知识库管理 API
"""
import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from server.config import UPLOADS_DIR, CHUNKS_DIR, get_settings
from server.db.sqlite import get_db
from server.db.chromadb import add_chunks, delete_doc_chunks
from server.core.parser.document import parse_file, get_file_type
from server.core.chunker.chunker import chunk_text
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


@router.post("/documents", response_model=Document)
async def upload_document(file: UploadFile = File(...)):
    # 保存文件
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".md", ".txt"]:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOADS_DIR / unique_name
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    file_size = os.path.getsize(file_path)
    file_type = get_file_type(file.filename)
    
    # 入库
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO documents (filename, file_type, file_path, file_size, status) VALUES (?, ?, ?, ?, ?)",
        (file.filename, file_type, str(file_path), file_size, "processing")
    )
    doc_id = cur.lastrowid
    conn.commit()
    
    # 解析
    try:
        text, page_info = parse_file(str(file_path))
        chunks = chunk_text(text)
        
        # 存入 SQLite
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
        
        # 存入向量库
        add_chunks(doc_id, chunk_records)
        
        cur.execute(
            "UPDATE documents SET chunk_count = ?, status = ? WHERE id = ?",
            (len(chunks), "ready", doc_id)
        )
        conn.commit()
    except Exception as e:
        cur.execute("UPDATE documents SET status = ? WHERE id = ?", ("error", doc_id))
        conn.commit()
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        conn.close()
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = Document(**dict(cur.fetchone()))
    conn.close()
    return doc


@router.delete("/documents/{doc_id}", response_model=Resp)
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
