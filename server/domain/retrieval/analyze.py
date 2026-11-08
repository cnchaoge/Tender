"""历史标书拆节。结果仍写在资料库文档的切片上。"""
from fastapi import HTTPException

from server.db.sqlite import get_db
from server.models import Resp

def analyze_old_bid(doc_id: int):
    """拆解历史投标标书为结构化章节并存入向量库"""
    from server.tools.bid_analyzer import analyze_old_bid, store_analyzed_sections

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = cur.fetchone()
    conn.close()

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    from server.core.parser.document import parse_file
    from server.domain.documents.files import resolve_stored_path

    text, _ = parse_file(str(resolve_stored_path(doc["file_path"])))

    if len(text.strip()) < 200:
        raise HTTPException(status_code=400, detail="文档内容太少（< 200 字），无法解析")

    sections = analyze_old_bid(text)
    if not sections:
        return Resp(code=1, message="未能识别出标书章节结构，请确认文件是否为投标标书")

    from server.domain.documents.index_build import IndexIdentityError

    try:
        store_analyzed_sections(doc_id, sections)
    except IndexIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Resp(data={
        "doc_id": doc_id,
        "filename": doc["filename"],
        "section_count": len(sections),
        "sections": [{
            "section_name": s.get("section_name"),
            "section_type": s.get("section_type"),
            "key_info": s.get("key_info"),
        } for s in sections],
    })


def get_analyzed_sections(doc_id: int):
    """查看历史标书拆解结果"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM chunks
        WHERE doc_id = ? AND json_extract(metadata, '$.source_type') = 'bid_section'
        ORDER BY chunk_index
    """, (doc_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return Resp(code=1, message="该文档尚未进行标书拆解分析")

    import json
    return Resp(data=[{
        "section_name": json.loads(r["metadata"]).get("section_name", ""),
        "section_type": json.loads(r["metadata"]).get("section_type", ""),
        "key_info": json.loads(r["metadata"]).get("key_info", ""),
        "content": r["text"],
        "chunk_index": r["chunk_index"],
    } for r in rows])
