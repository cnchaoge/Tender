"""
Tender - 内置招投标词汇表初始化

术语表是一条 scope=system 的文档，走和资料库相同的解析、切片、嵌入。
嵌入失败时文档为 failed，下次启动再试。不再在失败后仍标成可用。
"""
import hashlib

try:
    # Shipped separately. A root `.gitignore` rule of `data/` also ignores
    # `server/data/`, so a clean checkout may not have this module.
    from server.data.glossary_data import GLOSSARY_ENTRIES
except ImportError:
    GLOSSARY_ENTRIES = []

GLOSSARY_FILENAME = "内置投标术语表"


def _glossary_text() -> str:
    lines = [f"## {term}\n{explanation}" for term, explanation in GLOSSARY_ENTRIES]
    return "\n\n---\n\n".join(lines)


def init_builtin_glossary():
    """嵌入内置词汇表。已成功且内容未变则跳过；失败或未完成则再跑一遍入库。"""
    if not GLOSSARY_ENTRIES:
        return
    from server.db.sqlite import get_db
    from server.domain.documents.files import relative_to_data, write_original_bytes
    from server.workers.document_worker import process_document

    text = _glossary_text()
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, status, content_sha256, chunk_count
               FROM documents WHERE filename=?""",
            (GLOSSARY_FILENAME,),
        )
        row = cur.fetchone()
        if (
            row is not None
            and row["status"] == "ready"
            and row["content_sha256"] == digest
            and (row["chunk_count"] or 0) > 0
        ):
            return
        if row is None:
            cur.execute(
                """INSERT INTO documents
                   (filename, file_type, file_path, file_size, status, chunk_count,
                    scope, storage, content_sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    GLOSSARY_FILENAME,
                    "glossary",
                    "",
                    len(raw),
                    "pending",
                    0,
                    "system",
                    "managed",
                    digest,
                ),
            )
            doc_id = int(cur.lastrowid)
        else:
            doc_id = int(row["id"])
            cur.execute(
                """UPDATE documents
                   SET status='pending', chunk_count=0, scope='system', storage='managed',
                       content_sha256=?, file_size=?, file_type='glossary',
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (digest, len(raw), doc_id),
            )
        conn.commit()
    finally:
        conn.close()

    dest = write_original_bytes(doc_id, raw, ".txt")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE documents SET file_path=? WHERE id=?",
            (relative_to_data(dest), doc_id),
        )
        conn.commit()
    finally:
        conn.close()

    process_document(doc_id, str(dest))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM documents WHERE id=?", (doc_id,))
        status_row = cur.fetchone()
    finally:
        conn.close()
    status = status_row["status"] if status_row is not None else "failed"
    if status == "ready":
        print(f"[Glossary] 已加载 {len(GLOSSARY_ENTRIES)} 条招投标术语到知识库")
    else:
        print(f"[Glossary] 嵌入失败，文档状态为 {status}，下次启动再试")
