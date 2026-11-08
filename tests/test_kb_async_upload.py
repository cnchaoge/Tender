"""Async knowledge-base upload, status polling, and failure cleanup."""
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import kb as kb_mod
from server.deps import get_current_user
from server.domain.documents import files as files_mod
from server.domain.documents import index_build as index_mod
from server.workers import document_worker as worker_mod
from server.workers.executor import shutdown_executor

SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_sha256 TEXT,
    scope TEXT NOT NULL DEFAULT 'library',
    storage TEXT NOT NULL DEFAULT 'external',
    extracted_relpath TEXT
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
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    return _get


def _count_chunks(getter, doc_id: int) -> int:
    conn = getter()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def _status_row(getter, doc_id: int):
    conn = getter()
    try:
        return conn.execute(
            "SELECT status, chunk_count FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture
def getter(tmp_path):
    db_path = tmp_path / "kb.db"
    _init_db(db_path)
    return _getter(db_path)


def _authorized_app() -> FastAPI:
    """KB routes require a logged-in user. Async tests override that check."""
    app = FastAPI()
    app.include_router(kb_mod.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": 1,
        "username": "tester",
        "role": "user",
    }
    return app


@pytest.fixture
def client(getter, tmp_path, monkeypatch):
    scheduled = []

    def fake_schedule(doc_id, file_path):
        scheduled.append((doc_id, file_path))

    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(kb_mod, "get_db", getter)
    monkeypatch.setattr(kb_mod, "schedule_document", fake_schedule)
    return TestClient(_authorized_app()), scheduled


def test_kb_routes_require_auth(getter, tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(kb_mod, "get_db", getter)
    app = FastAPI()
    app.include_router(kb_mod.router)
    http = TestClient(app)

    assert http.get("/api/kb/documents").status_code == 401
    assert http.get("/api/kb/documents/1/status").status_code == 401
    assert http.get("/api/kb/folder", params={"folder_path": str(tmp_path)}).status_code == 401
    uploaded = http.post(
        "/api/kb/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert uploaded.status_code == 401
    assert http.delete("/api/kb/documents/1").status_code == 401


def test_upload_route_has_no_hardcoded_interpreter():
    source = Path("server/api/kb.py").read_text(encoding="utf-8")
    worker = Path("server/workers/document_worker.py").read_text(encoding="utf-8")
    assert "CommandLineTools" not in source
    assert "subprocess" not in source
    assert "CommandLineTools" not in worker


def test_upload_returns_pending_and_status_endpoint(client):
    http, scheduled = client
    resp = http.post(
        "/api/kb/documents",
        files={"file": ("notes.txt", b"hello knowledge base", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["chunk_count"] == 0
    assert body["doc_id"]
    assert len(scheduled) == 1
    assert scheduled[0][0] == body["doc_id"]
    assert Path(scheduled[0][1]).is_file()

    status = http.get(f"/api/kb/documents/{body['doc_id']}/status")
    assert status.status_code == 200
    assert status.json() == {
        "doc_id": body["doc_id"],
        "status": "pending",
        "chunk_count": 0,
    }

    missing = http.get("/api/kb/documents/9999/status")
    assert missing.status_code == 404


def test_same_bytes_are_duplicate_even_with_another_name(client):
    http, scheduled = client
    first = http.post(
        "/api/kb/documents",
        files={"file": ("one.txt", b"same-bytes", "text/plain")},
    )
    second = http.post(
        "/api/kb/documents",
        files={"file": ("two.txt", b"same-bytes", "text/plain")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["doc_id"] == first.json()["doc_id"]
    assert second.json()["status"] == "pending"
    assert len(scheduled) == 1
    stored = Path(scheduled[0][1])
    assert stored.is_file()
    assert stored.parent.parent.name == "library"


def test_same_name_different_bytes_are_separate_documents(client):
    http, scheduled = client
    first = http.post(
        "/api/kb/documents",
        files={"file": ("same.txt", b"one", "text/plain")},
    )
    second = http.post(
        "/api/kb/documents",
        files={"file": ("same.txt", b"two", "text/plain")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json().get("duplicate") is not True
    assert second.json()["doc_id"] != first.json()["doc_id"]
    assert len(scheduled) == 2


def test_unhashed_legacy_row_still_dedupes_by_filename(client, getter):
    conn = getter()
    try:
        conn.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, content_sha256)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            ("legacy.txt", "txt", "/tmp/legacy.txt", 3, "ready", 1),
        )
        conn.commit()
    finally:
        conn.close()
    http, scheduled = client
    resp = http.post(
        "/api/kb/documents",
        files={"file": ("legacy.txt", b"brand-new", "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is True
    assert resp.json()["status"] == "ready"
    assert scheduled == []


def test_oversize_upload_removes_partial_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(kb_mod, "max_upload_bytes", lambda: 4)
    http, scheduled = client
    resp = http.post(
        "/api/kb/documents",
        files={"file": ("big.txt", b"12345", "text/plain")},
    )
    assert resp.status_code == 413
    assert "超过" in resp.json()["detail"]
    assert scheduled == []
    incoming = tmp_path / "library" / "_incoming"
    if incoming.exists():
        assert list(incoming.iterdir()) == []


def test_delete_removes_managed_copy_and_leaves_external_file(client, tmp_path, getter, monkeypatch):
    monkeypatch.setattr(kb_mod, "delete_doc_chunks", lambda _doc_id: None)
    http, _scheduled = client
    uploaded = http.post(
        "/api/kb/documents",
        files={"file": ("notes.txt", b"managed-body", "text/plain")},
    )
    assert uploaded.status_code == 200
    managed = Path(uploaded.json()["file_path"])
    assert managed.is_file()
    outside = tmp_path / "outside.txt"
    outside.write_text("do-not-delete", encoding="utf-8")

    removed = http.delete(f"/api/kb/documents/{uploaded.json()['doc_id']}")
    assert removed.status_code == 200
    assert not managed.exists()
    assert outside.read_text(encoding="utf-8") == "do-not-delete"

    conn = getter()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, storage, scope)
               VALUES ('outside.txt', 'txt', ?, 13, 'ready', 0, 'external', 'library')""",
            (str(outside),),
        )
        ext_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    removed_external = http.delete(f"/api/kb/documents/{ext_id}")
    assert removed_external.status_code == 200
    assert outside.is_file()
    assert outside.read_text(encoding="utf-8") == "do-not-delete"


def test_unsupported_upload_rejected(client):
    http, scheduled = client
    resp = http.post(
        "/api/kb/documents",
        files={"file": ("evil.exe", b"nope", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert scheduled == []


def test_upload_returns_while_worker_is_still_blocked(getter, tmp_path, monkeypatch):
    gate = threading.Event()
    started = threading.Event()

    def blocked(doc_id, file_path):
        started.set()
        gate.wait(10)

    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(kb_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "process_document", blocked)
    http = TestClient(_authorized_app())
    try:
        started_at = time.perf_counter()
        resp = http.post(
            "/api/kb/documents",
            files={"file": ("slow.txt", b"pending please", "text/plain")},
        )
        elapsed = time.perf_counter() - started_at
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        # The worker blocks for up to 10s. The response must not wait for it.
        assert elapsed < 3
        assert started.wait(3)
        status = http.get(f"/api/kb/documents/{resp.json()['doc_id']}/status")
        assert status.json()["status"] == "pending"
    finally:
        gate.set()
        shutdown_executor(wait=True)


def test_folder_import_queues_pending_without_parsing(client, tmp_path, monkeypatch):
    http, scheduled = client

    def explode(*_args, **_kwargs):
        raise AssertionError("folder import must not parse inside the request")

    monkeypatch.setattr(worker_mod, "parse_file", explode)
    folder = tmp_path / "incoming"
    (folder / "node_modules").mkdir(parents=True)
    (folder / "node_modules" / "skip.txt").write_text("skip", encoding="utf-8")
    (folder / "ok.txt").write_text("hello", encoding="utf-8")
    (folder / "nested").mkdir()
    (folder / "nested" / "b.md").write_text("markdown", encoding="utf-8")
    (folder / "nested" / "ok.txt").write_text("duplicate name", encoding="utf-8")

    missing = http.get("/api/kb/folder", params={"folder_path": str(tmp_path / "nope")})
    assert missing.status_code == 400

    empty = tmp_path / "empty"
    empty.mkdir()
    no_files = http.get("/api/kb/folder", params={"folder_path": str(empty)})
    assert no_files.status_code == 400

    resp = http.get("/api/kb/folder", params={"folder_path": str(folder)})
    assert resp.status_code == 200
    docs = resp.json()
    # 同名但内容不同的文件各自入库；原件留在用户目录，队列里是资料库副本。
    assert sorted(doc["filename"] for doc in docs) == ["b.md", "ok.txt", "ok.txt"]
    assert {doc["status"] for doc in docs} == {"pending"}
    assert len(scheduled) == 3
    for _doc_id, path in scheduled:
        stored = Path(path)
        assert stored.is_file()
        assert stored.parent.parent.name == "library"
        assert stored.name.startswith("original")
    assert (folder / "ok.txt").read_text(encoding="utf-8") == "hello"
    assert (folder / "nested" / "ok.txt").read_text(encoding="utf-8") == "duplicate name"


def _patch_worker(monkeypatch, getter, parse_result=("正文", []), pieces=None, embed=None, add=None, delete=None):
    library_root = Path(tempfile.mkdtemp())
    monkeypatch.setattr(files_mod, "DATA_DIR", library_root)
    monkeypatch.setattr(index_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "parse_file", lambda path: parse_result)
    monkeypatch.setattr(worker_mod, "chunk_text", lambda text: pieces if pieces is not None else ["only"])
    if embed is not None:
        monkeypatch.setattr(worker_mod, "get_embedder", lambda: embed)
    if add is not None:
        monkeypatch.setattr(worker_mod, "add_chunks", add)
    if delete is not None:
        monkeypatch.setattr(worker_mod, "delete_doc_chunks", delete)


class _Embedder:
    def __init__(self, vectors=None, fail=False, on_embed=None):
        self.vectors = vectors
        self.fail = fail
        self.on_embed = on_embed

    def embed(self, texts):
        if self.on_embed:
            self.on_embed(texts)
        if self.fail:
            raise RuntimeError("embed down")
        if self.vectors is not None:
            return self.vectors
        return [[0.1, 0.2] for _ in texts]


def _insert_doc(getter, filename="a.txt", status="pending", file_path="/tmp/a.txt"):
    conn = getter()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count) VALUES (?, ?, ?, ?, ?, ?)",
            (filename, "txt", file_path, 4, status, 0),
        )
        doc_id = cur.lastrowid
        conn.commit()
        return doc_id
    finally:
        conn.close()


def test_worker_success_sets_ready_and_keeps_chunks(getter, monkeypatch):
    doc_id = _insert_doc(getter)
    added = {}
    deleted = []
    seen = {}

    def on_embed(texts):
        row = _status_row(getter, doc_id)
        seen["status"] = row["status"]
        seen["chunk_count"] = row["chunk_count"]
        seen["rows"] = _count_chunks(getter, doc_id)
        assert texts == ["alpha", "beta"]

    def add_chunks(stored_id, records, collection_name=None):
        added["doc_id"] = stored_id
        added["records"] = records

    _patch_worker(
        monkeypatch,
        getter,
        pieces=["alpha", "beta"],
        embed=_Embedder(on_embed=on_embed),
        add=add_chunks,
        delete=lambda doc: deleted.append(doc),
    )
    worker_mod.process_document(doc_id, "/tmp/a.txt")

    row = _status_row(getter, doc_id)
    assert row["status"] == "ready"
    assert row["chunk_count"] == 2
    assert _count_chunks(getter, doc_id) == 2
    assert seen == {"status": "processing", "chunk_count": 2, "rows": 2}
    assert added["doc_id"] == doc_id
    assert [record["vector"] for record in added["records"]] == [[0.1, 0.2], [0.1, 0.2]]
    assert deleted == []


def test_worker_embed_failure_clears_chunks_and_chroma(getter, monkeypatch):
    doc_id = _insert_doc(getter)
    deleted = []
    partial = {}

    def on_embed(_texts):
        partial["chunks"] = _count_chunks(getter, doc_id)

    def delete_doc_chunks(stored_id):
        deleted.append(stored_id)
        raise RuntimeError("chroma unavailable")

    _patch_worker(
        monkeypatch,
        getter,
        pieces=["alpha", "beta"],
        embed=_Embedder(fail=True, on_embed=on_embed),
        add=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("add_chunks should not run")),
        delete=delete_doc_chunks,
    )
    worker_mod.process_document(doc_id, "/tmp/a.txt")

    row = _status_row(getter, doc_id)
    assert partial["chunks"] == 2
    assert row["status"] == "failed"
    assert row["chunk_count"] == 0
    assert _count_chunks(getter, doc_id) == 0
    assert deleted == [doc_id]


def test_worker_chroma_failure_rolls_back_sqlite_chunks(getter, monkeypatch):
    doc_id = _insert_doc(getter)
    deleted = []

    def add_chunks(stored_id, _records, collection_name=None):
        deleted_state = _count_chunks(getter, stored_id)
        assert deleted_state == 2
        raise RuntimeError("chroma down")

    _patch_worker(
        monkeypatch,
        getter,
        pieces=["alpha", "beta"],
        embed=_Embedder(),
        add=add_chunks,
        delete=lambda stored_id: deleted.append(stored_id),
    )
    worker_mod.process_document(doc_id, "/tmp/a.txt")
    row = _status_row(getter, doc_id)
    assert row["status"] == "failed"
    assert row["chunk_count"] == 0
    assert _count_chunks(getter, doc_id) == 0
    assert deleted == [doc_id]


def test_worker_parse_failure_drops_preexisting_partial_chunks(getter, tmp_path, monkeypatch):
    doc_id = _insert_doc(getter, status="processing")
    conn = getter()
    try:
        conn.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
            (doc_id, 0, "partial", "{}"),
        )
        conn.commit()
    finally:
        conn.close()
    deleted = []

    def parse_file(_path):
        raise RuntimeError("ocr blew up")

    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(index_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "parse_file", parse_file)
    monkeypatch.setattr(worker_mod, "delete_doc_chunks", lambda stored_id: deleted.append(stored_id))

    worker_mod.process_document(doc_id, "/tmp/a.txt")
    row = _status_row(getter, doc_id)
    assert row["status"] == "failed"
    assert row["chunk_count"] == 0
    assert _count_chunks(getter, doc_id) == 0
    assert deleted == [doc_id]


def test_worker_real_parse_embed_and_chroma_cleanup(getter, tmp_path, monkeypatch):
    """Parse a real text file, store mock vectors, then prove failure cleanup removes them."""
    from server.core.embedder.embedder import MockEmbedder
    from server.db import chromadb as chroma_mod

    source = tmp_path / "bid.txt"
    source.write_text("投标文件正文。\n" * 40, encoding="utf-8")
    doc_id = _insert_doc(getter, filename="bid.txt", file_path=str(source))
    chroma_dir = tmp_path / "chroma"
    monkeypatch.setattr(
        chroma_mod,
        "settings",
        type("S", (), {"CHROMA_PERSIST_DIR": str(chroma_dir)})(),
    )
    chroma_mod._client = None
    chroma_mod._collection = None
    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(index_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "get_embedder", MockEmbedder)

    try:
        worker_mod.process_document(doc_id, str(source))
        row = _status_row(getter, doc_id)
        assert row["status"] == "ready"
        assert row["chunk_count"] > 0
        assert _count_chunks(getter, doc_id) == row["chunk_count"]
        stored = chroma_mod.get_collection().get(where={"doc_id": doc_id})
        assert len(stored["ids"]) == row["chunk_count"]

        worker_mod.cleanup_partial_document(doc_id)
        row = _status_row(getter, doc_id)
        assert row["status"] == "failed"
        assert row["chunk_count"] == 0
        assert _count_chunks(getter, doc_id) == 0
        remaining = chroma_mod.get_collection().get(where={"doc_id": doc_id})
        assert remaining["ids"] == []
    finally:
        chroma_mod._client = None
        chroma_mod._collection = None


def test_requeue_resets_incomplete_documents(getter, monkeypatch):
    pending_id = _insert_doc(getter, filename="p.txt", status="pending")
    processing_id = _insert_doc(getter, filename="w.txt", status="processing")
    ready_id = _insert_doc(getter, filename="r.txt", status="ready")
    conn = getter()
    try:
        conn.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, ?, ?, ?)",
            (processing_id, 0, "half", "{}"),
        )
        conn.execute(
            "UPDATE documents SET chunk_count = 3 WHERE id = ?",
            (ready_id,),
        )
        conn.commit()
    finally:
        conn.close()

    scheduled = []
    deleted = []
    monkeypatch.setattr(worker_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "delete_doc_chunks", lambda stored_id: deleted.append(stored_id))
    monkeypatch.setattr(
        "server.workers.executor.schedule_document",
        lambda doc_id, file_path: scheduled.append((doc_id, file_path)),
    )

    queued = worker_mod.requeue_incomplete_documents()
    assert queued == 2
    assert _status_row(getter, pending_id)["status"] == "pending"
    assert _status_row(getter, processing_id)["status"] == "pending"
    assert _status_row(getter, processing_id)["chunk_count"] == 0
    assert _count_chunks(getter, processing_id) == 0
    ready = _status_row(getter, ready_id)
    assert ready["status"] == "ready"
    assert ready["chunk_count"] == 3
    assert sorted(doc_id for doc_id, _path in scheduled) == sorted([pending_id, processing_id])
    assert processing_id in deleted
    assert pending_id in deleted
    assert ready_id not in deleted
