import sqlite3
from pathlib import Path

from server.core import glossary as glossary_mod
from server.domain.documents import files as files_mod
from server.domain.documents import index_build as index_mod
from server.workers import document_worker as worker_mod

SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,
    file_path TEXT,
    file_size INTEGER,
    status TEXT,
    chunk_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_sha256 TEXT,
    scope TEXT NOT NULL DEFAULT 'library',
    storage TEXT NOT NULL DEFAULT 'external',
    extracted_relpath TEXT
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    chunk_index INTEGER,
    text TEXT,
    metadata TEXT
);
"""


def _getter(path: Path):
    def _get():
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    return _get


def _prepare(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "glossary.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    getter = _getter(db_path)
    monkeypatch.setattr(files_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr("server.db.sqlite.get_db", getter)
    monkeypatch.setattr(worker_mod, "get_db", getter)
    monkeypatch.setattr(index_mod, "get_db", getter)
    monkeypatch.setattr(worker_mod, "delete_doc_chunks", lambda _doc_id: None)
    return getter


def _status(getter):
    conn = getter()
    try:
        return conn.execute(
            "SELECT status, scope, storage, chunk_count FROM documents WHERE filename=?",
            (glossary_mod.GLOSSARY_FILENAME,),
        ).fetchone()
    finally:
        conn.close()


def test_glossary_embed_failure_is_failed_and_retries(monkeypatch, tmp_path):
    glossary_mod.GLOSSARY_ENTRIES = [("term1", "explanation1"), ("term2", "explanation2")]
    getter = _prepare(monkeypatch, tmp_path)
    added = []

    class Boom:
        def embed(self, texts):
            raise RuntimeError("embed down")

    class Ok:
        def embed(self, texts):
            return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(worker_mod, "get_embedder", lambda: Boom())
    monkeypatch.setattr(worker_mod, "add_chunks", lambda doc_id, records, collection_name=None: added.append(records))

    glossary_mod.init_builtin_glossary()
    failed = _status(getter)
    assert failed["status"] == "failed"
    assert failed["scope"] == "system"
    assert failed["chunk_count"] == 0
    assert added == []

    monkeypatch.setattr(worker_mod, "get_embedder", lambda: Ok())
    glossary_mod.init_builtin_glossary()
    ready = _status(getter)
    assert ready["status"] == "ready"
    assert ready["storage"] == "managed"
    assert ready["chunk_count"] > 0
    assert added

    calls = len(added)
    glossary_mod.init_builtin_glossary()
    assert len(added) == calls
    assert _status(getter)["status"] == "ready"
