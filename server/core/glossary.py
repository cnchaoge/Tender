"""
Tender - 内置招投标词汇表初始化
系统启动时将词汇表嵌入到 ChromaDB，供 RAG 检索使用
"""
import json
from server.data.glossary_data import GLOSSARY_ENTRIES


def init_builtin_glossary():
    """将内置词汇表嵌入到知识库（如果尚未加载）"""
    from server.db.sqlite import get_db
    from server.db.chromadb import add_chunks
    from server.core.chunker.chunker import chunk_text
    from server.core.embedder.embedder import get_embedder

    conn = get_db()
    cur = conn.cursor()

    # 检查是否已加载
    cur.execute("SELECT id FROM documents WHERE filename = '内置投标术语表'")
    if cur.fetchone():
        conn.close()
        return

    # 构建词汇表文本
    lines = []
    for term, explanation in GLOSSARY_ENTRIES:
        lines.append(f"## {term}\n{explanation}")
    full_text = "\n\n---\n\n".join(lines)

    # 切块：每条术语作为独立切片
    chunk_texts = []
    chunk_metas = []
    for idx, (term, explanation) in enumerate(GLOSSARY_ENTRIES):
        chunk_texts.append(f"## {term}\n{explanation}")
        chunk_metas.append({"source_type": "glossary", "term": term, "explanation": explanation[:100]})

    # 插入 SQLite documents 表
    cur.execute(
        "INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count) VALUES (?, ?, ?, ?, ?, ?)",
        ("内置投标术语表", "glossary", "__glossary__", len(full_text), "ready", len(chunk_texts))
    )
    doc_id = cur.lastrowid

    # 插入 chunks + 向量化
    embedder = get_embedder()
    chunk_records = []
    for i, (text, meta) in enumerate(zip(chunk_texts, chunk_metas)):
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
            (doc_id, i, text, json.dumps(meta, ensure_ascii=False))
        )
        chunk_records.append({"text": text, "chunk_index": i, "metadata": meta})

    try:
        vectors = embedder.embed([r["text"] for r in chunk_records])
        for r, vec in zip(chunk_records, vectors):
            r["vector"] = vec
        add_chunks(doc_id, chunk_records)
    except Exception as e:
        print(f"[Glossary] Embed 失败，降级跳过: {e}")

    conn.commit()
    conn.close()
    print(f"[Glossary] 已加载 {len(GLOSSARY_ENTRIES)} 条招投标术语到知识库")
