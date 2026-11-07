"""生成和规划共用的素材读取与按章节检索。"""
from typing import Optional

from server.core.retriever.retriever import retrieve
from server.core.retriever.section_query import collect_section_materials
from server.db.sqlite import get_db

def _load_material_docs(doc_ids: list) -> list[dict]:
    """按素材 ID 读取文件名。缺失的文档直接跳过。"""
    if not doc_ids:
        return []
    conn = get_db()
    try:
        cur = conn.cursor()
        docs = []
        for doc_id in doc_ids:
            cur.execute("SELECT id, filename FROM documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if row:
                docs.append({"id": row["id"], "filename": row["filename"]})
        return docs
    finally:
        conn.close()


def _retrieve_materials_text(
    parse_result: dict,
    materials,
    chapters=None,
    per_doc_k: Optional[int] = None,
    max_chars: int = 6000,
) -> str:
    """按章节检索选中素材。流式与非流式生成共用这一条路径。"""
    docs = _load_material_docs(list(materials or []))
    return collect_section_materials(
        docs,
        parse_result or {},
        chapters,
        retrieve_fn=retrieve,
        per_doc_k=per_doc_k,
        max_chars=max_chars,
    )
