#!/usr/bin/env python3
"""
后台处理 worker：独立进程处理 PDF OCR → chunk → embed
接收参数：doc_id, file_path
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.core.parser.document import parse_file
from server.core.chunker.chunker import chunk_text
from server.core.embedder.embedder import get_embedder
from server.db.sqlite import get_db
from server.db.chromadb import add_chunks


def process(doc_id: int, file_path: str):
    try:
        print(f"[worker] doc_id={doc_id} start, file={file_path}")
        text, _ = parse_file(file_path)
        print(f"[worker] doc_id={doc_id} parsed, text_len={len(text)}")

        chunks = chunk_text(text)
        print(f"[worker] doc_id={doc_id} chunked, count={len(chunks)}")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE documents SET status='processing', chunk_count=? WHERE id=?", (len(chunks), doc_id))

        chunk_records = []
        for i, chunk_text_content in enumerate(chunks):
            cur.execute(
                "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
                (doc_id, i, chunk_text_content, "{}")
            )
            chunk_records.append({"text": chunk_text_content, "chunk_index": i, "metadata": {}})

        embedder = get_embedder()
        texts = [r["text"] for r in chunk_records]
        print(f"[worker] doc_id={doc_id} embedding {len(texts)} texts...")
        vectors = embedder.embed(texts)
        for r, v in zip(chunk_records, vectors):
            r["vector"] = v

        add_chunks(doc_id, chunk_records)
        cur.execute("UPDATE documents SET status='ready' WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        print(f"[worker] doc_id={doc_id} done!")
    except Exception as e:
        print(f"[worker] doc_id={doc_id} FAILED: {e}")
        import traceback
        traceback.print_exc()
        try:
            conn = get_db()
            conn.cursor().execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
            conn.commit()
            conn.close()
        except:
            pass


if __name__ == "__main__":
    doc_id = int(sys.argv[1])
    file_path = sys.argv[2]
    process(doc_id, file_path)