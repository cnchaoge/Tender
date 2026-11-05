"""历史素材预览应按当前招标内容排序，而不是返回文件开头的切片。"""
import json
import math
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import bid
from server.core.retriever import retriever
from server.deps import get_current_user

WELD_QUERY = "螺旋焊管埋弧焊壁厚防腐焊缝"
PRICE_TEXT = "分项报价表列示单价和投标保证金。"
WELD_TEXT = "螺旋焊管采用埋弧焊工艺。"
OTHER_DOC_TEXT = "螺旋焊管埋弧焊壁厚防腐焊缝，这份在另一份文件里更贴近。"
PREFIX = "公司食堂本周菜单与年会座位表"


class TopicEmbedder:
    """把指定词映射到彼此正交的维度，用来在测试里稳定比较相似度。"""

    TERMS = ("螺旋焊管", "埋弧焊", "壁厚", "防腐", "焊缝", "保证金")

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            counts = [float(text.count(term)) for term in self.TERMS]
            counts.append(0.0 if any(counts) else 1.0)
            norm = math.sqrt(sum(value * value for value in counts)) or 1.0
            vectors.append([value / norm for value in counts])
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    chunk_count INTEGER DEFAULT 0
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT
);
"""


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _getter(path: Path):
    def _get():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    return _get


def _insert_doc(conn, doc_id: int, filename: str, chunks: list[tuple[int, str, dict]]) -> None:
    conn.execute(
        """INSERT INTO documents (id, filename, file_type, file_path, file_size, chunk_count)
           VALUES (?, ?, 'docx', ?, 10, ?)""",
        (doc_id, filename, f"/tmp/{filename}", len(chunks)),
    )
    conn.executemany(
        "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
        [
            (doc_id, index, text, json.dumps(meta, ensure_ascii=False))
            for index, text, meta in chunks
        ],
    )


def _history_chunks() -> list[tuple[int, str, dict]]:
    chunks = []
    for index in range(19):
        chunks.append((index, f"{PREFIX}第{index}周", {}))
    chunks.append((19, PRICE_TEXT, {"section_name": "报价明细", "section_type": "price"}))
    chunks.append((20, WELD_TEXT, {"section_name": "技术方案", "section_type": "technical"}))
    return chunks


class _ExactCollection:
    """按平方欧氏距离精确排序，并执行文档过滤。

    生产代码走的仍是 ``query_chunks``。这里替换的是向量库本身，避免
    Chroma 在进程内共用一个内存实例时，把别的测试留下的切片算进结果。
    """

    def __init__(self):
        self.rows: list[dict] = []
        self.queries: list[dict] = []

    def count(self) -> int:
        return len(self.rows)

    def add(self, ids, documents, embeddings, metadatas) -> None:
        for chunk_id, text, vector, meta in zip(ids, documents, embeddings, metadatas):
            self.rows.append({
                "id": chunk_id,
                "text": text,
                "vector": list(vector),
                "metadata": dict(meta or {}),
            })

    def _matches(self, meta: dict, where: dict | None) -> bool:
        if not where:
            return True
        for key, expected in where.items():
            value = meta.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if value not in expected["$in"]:
                    return False
            elif value != expected:
                return False
        return True

    def query(self, query_embeddings, n_results, where=None):
        self.queries.append({"n_results": n_results, "where": where})
        query = query_embeddings[0]
        ranked = []
        for row in self.rows:
            if not self._matches(row["metadata"], where):
                continue
            distance = sum((left - right) ** 2 for left, right in zip(query, row["vector"]))
            ranked.append((distance, row))
        ranked.sort(key=lambda item: (item[0], item[1]["id"]))
        picked = ranked[:n_results]
        return {
            "ids": [[row["id"] for _, row in picked]],
            "documents": [[row["text"] for _, row in picked]],
            "metadatas": [[row["metadata"] for _, row in picked]],
            "distances": [[distance for distance, _ in picked]],
        }


def _use_memory_chroma(monkeypatch, embedder: TopicEmbedder):
    from server.db import chromadb as chroma_mod

    collection = _ExactCollection()
    monkeypatch.setattr(chroma_mod, "_collection", collection)
    monkeypatch.setattr(chroma_mod, "get_embedder", lambda: embedder)
    return chroma_mod


def _seed(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "recommend.db"
    _init_db(db_path)
    getter = _getter(db_path)
    conn = getter()
    _insert_doc(conn, 1, "历史标书.docx", _history_chunks())
    other = [
        (index, f"{OTHER_DOC_TEXT}#{index}", {})
        for index in range(8)
    ]
    _insert_doc(conn, 2, "另一份标书.docx", other)
    conn.commit()
    conn.close()

    embedder = TopicEmbedder()
    chroma_mod = _use_memory_chroma(monkeypatch, embedder)

    def _store(doc_id: int, rows: list[tuple[int, str, dict]]) -> None:
        records = []
        vectors = embedder.embed([text for _, text, _ in rows])
        for (index, text, _meta), vector in zip(rows, vectors):
            records.append({
                "text": text,
                "chunk_index": index,
                "metadata": {},
                "vector": vector,
            })
        chroma_mod.add_chunks(doc_id, records)

    _store(1, _history_chunks())
    _store(2, other)
    monkeypatch.setattr(bid, "get_db", getter)
    monkeypatch.setattr(retriever, "get_db", getter)
    return getter


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(bid.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": 1,
        "username": "tester",
        "role": "user",
        "must_change_password": False,
    }
    return app


def _assert_ranked_first(body: dict, index: int, snippet: str) -> None:
    sections = body["sections"]
    assert body["ranked"] is True
    assert sections
    assert sections[0]["index"] == index
    assert snippet in sections[0]["text"]
    assert sections[0]["rank"] == 0
    assert not sections[0]["text"].startswith(PREFIX)
    assert all("更贴近" not in sec["text"] for sec in sections)
    scores = [sec["score"] for sec in sections]
    assert scores == sorted(scores, reverse=True)
    if len(sections) > 1:
        assert sections[0]["score"] > max(sec["score"] for sec in sections[1:])
    assert [sec["index"] for sec in sections] != list(range(len(sections)))
    assert body["section_count"] == len(sections)
    assert body["section_count"] <= 5


def test_preview_requires_login():
    app = FastAPI()
    app.include_router(bid.router)
    http = TestClient(app)
    assert http.get("/api/bid/recommend/1/preview").status_code == 401
    assert http.post("/api/bid/recommend/1/preview", json={"q": WELD_QUERY}).status_code == 401


def test_preview_without_context_is_not_a_prefix(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)

    def boom(*_args, **_kwargs):
        raise AssertionError("没有检索条件时不应去取切片")

    monkeypatch.setattr(bid, "retrieve", boom)
    http = TestClient(_app())
    resp = http.get("/api/bid/recommend/1/preview")
    assert resp.status_code == 400
    assert "相似度" in resp.json()["detail"]
    assert "sections" not in resp.json()


def test_preview_without_vectors_does_not_return_the_prefix(monkeypatch, tmp_path):
    db_path = tmp_path / "empty-vectors.db"
    _init_db(db_path)
    getter = _getter(db_path)
    conn = getter()
    _insert_doc(conn, 1, "历史标书.docx", _history_chunks())
    conn.commit()
    conn.close()
    _use_memory_chroma(monkeypatch, TopicEmbedder())
    monkeypatch.setattr(bid, "get_db", getter)
    monkeypatch.setattr(retriever, "get_db", getter)

    http = TestClient(_app())
    resp = http.get(
        "/api/bid/recommend/1/preview",
        params={"q": WELD_QUERY, "top_k": 20},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ranked"] is True
    assert body["sections"] == []
    assert body["section_count"] == 0
    assert "相似" in body["message"]


def test_preview_missing_document(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    http = TestClient(_app())
    resp = http.get("/api/bid/recommend/99/preview", params={"q": WELD_QUERY})
    assert resp.status_code == 404


def test_preview_ranks_weld_chapter_over_unrelated_prefix(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    http = TestClient(_app())
    resp = http.get(
        "/api/bid/recommend/1/preview",
        params={"q": WELD_QUERY, "top_k": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_ranked_first(body, 20, "埋弧焊")
    assert body["filename"] == "历史标书.docx"
    assert body["sections"][0]["section_name"] == "技术方案"
    assert body["sections"][0]["section_type"] == "technical"
    assert body["query"]
    # 旧实现只返回 chunk_index 0..19，第 20 段焊管章节永远进不了预览。
    assert 20 in [sec["index"] for sec in body["sections"]]
    assert body["sections"][0]["index"] != 0


def test_preview_ranks_price_chapter_when_query_is_commercial(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    http = TestClient(_app())
    resp = http.post(
        "/api/bid/recommend/1/preview",
        json={
            "q": "分项报价 投标保证金",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_ranked_first(body, 19, "保证金")
    assert body["sections"][0]["section_name"] == "报价明细"


def test_preview_uses_parse_result_from_the_current_tender(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    http = TestClient(_app())
    resp = http.post(
        "/api/bid/recommend/1/preview",
        json={
            "parse_result": {
                "project_name": "某油田地面工程物资采购",
                "requirements": ["螺旋焊管须采用埋弧焊，并说明壁厚、防腐和焊缝"],
                "qualification": ["特种设备制造许可证"],
            },
            "chapter": {"name": "技术方案", "description": "焊接工艺"},
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_ranked_first(body, 20, "埋弧焊")
    assert "技术方案" in body["query"]
    assert "埋弧焊" in body["query"]


def test_build_recommend_query_keeps_tender_context():
    query = bid.build_recommend_query(
        "技术方案",
        {
            "project_name": "某油田地面工程物资采购",
            "requirements": ["螺旋焊管须采用埋弧焊，并说明防腐和焊缝"],
            "deadline": "90日历天",
        },
        {"name": "技术方案", "description": "焊接工艺"},
    )
    assert "技术方案" in query
    assert "埋弧焊" in query
    assert "防腐" in query
    # 技术方案章节不把工期塞进检索词，避免把进度类片段排到前面。
    assert "90日历天" not in query
    assert query.count("技术方案") == 1
    assert bid.build_recommend_query(None, {"project_name": ""}, None) == ""
    assert bid.build_recommend_query("  焊管防腐  ", None, None) == "焊管防腐"


def test_retrieve_asks_chroma_for_the_selected_documents(monkeypatch, tmp_path):
    calls = []

    def fake_query(query, top_k=5, where=None):
        calls.append({"query": query, "top_k": top_k, "where": where})
        return [
            {
                "id": "doc2_chunk0",
                "text": OTHER_DOC_TEXT,
                "metadata": {"doc_id": 2, "chunk_index": 0},
                "distance": 0.05,
            },
            {
                "id": "doc1_chunk20",
                "text": WELD_TEXT,
                "metadata": {"doc_id": "1", "chunk_index": 20},
                "distance": 0.4,
            },
        ]

    db_path = tmp_path / "retriever.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO documents (id, filename, file_type, file_path, file_size, chunk_count)
           VALUES (1, '历史标书.docx', 'docx', '/tmp/a', 1, 1)"""
    )
    conn.commit()
    conn.close()

    def getter():
        opened = sqlite3.connect(db_path)
        opened.row_factory = sqlite3.Row
        return opened

    monkeypatch.setattr(retriever, "query_chunks", fake_query)
    monkeypatch.setattr(retriever, "get_db", getter)

    hits = retriever.retrieve(WELD_QUERY, top_k=5, doc_ids=[1])
    assert calls[0]["where"] == {"doc_id": 1}
    assert calls[0]["top_k"] == 5
    assert [hit["doc_id"] for hit in hits] == [1]
    assert hits[0]["filename"] == "历史标书.docx"
    assert hits[0]["text"] == WELD_TEXT

    hits = retriever.retrieve(WELD_QUERY, top_k=4, doc_ids=[2, 1, 2])
    assert calls[1]["where"] == {"doc_id": {"$in": [2, 1]}}
    assert calls[1]["top_k"] == 4
    assert {hit["doc_id"] for hit in hits} <= {1, 2}


def test_chroma_where_ranks_later_chapter_ahead_of_prefix():
    """真实 Chroma 在限定文档后，应把靠后的同主题章节排到无关前缀之前。"""
    import chromadb
    from chromadb.config import Settings

    embedder = TopicEmbedder()
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    name = "tender_recommend_probe"
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.get_or_create_collection(name)
    try:
        ids, documents, embeddings, metadatas = [], [], [], []
        rows = _history_chunks() + [
            (index, f"{OTHER_DOC_TEXT}#{index}", {})
            for index in range(8)
        ]
        # 前 21 条属于文档 1，后面 8 条属于文档 2。
        owners = [1] * len(_history_chunks()) + [2] * 8
        for (index, text, _meta), doc_id in zip(rows, owners):
            ids.append(f"doc{doc_id}_chunk{index}")
            documents.append(text)
            embeddings.append(embedder.embed_one(text))
            metadatas.append({"doc_id": doc_id, "chunk_index": index})
        collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        found = collection.query(
            query_embeddings=[embedder.embed_one(WELD_QUERY)],
            n_results=5,
            where={"doc_id": 1},
        )
        assert found["metadatas"][0][0]["chunk_index"] == 20
        assert "埋弧焊" in found["documents"][0][0]
        assert all(meta["doc_id"] == 1 for meta in found["metadatas"][0])
        assert all("更贴近" not in text for text in found["documents"][0])
    finally:
        try:
            client.delete_collection(name)
        except Exception:
            pass
