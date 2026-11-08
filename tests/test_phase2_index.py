"""阶段 2：受管原件、删除边界、索引身份与重建。"""
from pathlib import Path

import pytest
from fastapi import HTTPException

from server.db import chromadb as chroma_mod
from server.db import sqlite as sqlite_mod
from server.domain.documents import files as files_mod
from server.domain.documents import index_build as index_mod
from server.domain.documents.index_build import (
    MISMATCH_MESSAGE,
    EmbeddingIdentity,
    IndexIdentityError,
    MockIndexError,
    RebuildInProgress,
)


class _FixedEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0, 0.25] for _ in texts]

    def embed_one(self, text):
        return [1.0, 0.0, 0.0, 0.25]


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sqlite_mod, "DB_PATH", data / "tender.db")
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", data)
    monkeypatch.setattr(files_mod, "DATA_DIR", data)
    monkeypatch.setattr(index_mod, "get_db", sqlite_mod.get_db)
    sqlite_mod.init_db()
    return data


def _identity(provider: str, model: str):
    def _current():
        return EmbeddingIdentity(provider, model)
    return _current


def _insert_chunk(text: str = "唯一句子") -> int:
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('a.txt', 'txt', 'library/1/original.txt', 4, 'ready', 1, 'library', 'managed')"""
        )
        doc_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, 0, ?, '{}')",
            (doc_id, text),
        )
        conn.commit()
        return doc_id
    finally:
        conn.close()


def _prepare_chroma(monkeypatch, tmp_path: Path):
    chroma_dir = tmp_path / "chroma"
    monkeypatch.setattr(
        chroma_mod,
        "settings",
        type("S", (), {"CHROMA_PERSIST_DIR": str(chroma_dir)})(),
    )
    chroma_mod._client = None
    chroma_mod._collection = None
    monkeypatch.setattr(chroma_mod, "get_embedder", lambda: _FixedEmbedder())
    monkeypatch.setattr(
        "server.core.embedder.embedder.get_embedder",
        lambda: _FixedEmbedder(),
    )
    return chroma_dir


def _run_rebuild(monkeypatch) -> dict:
    scheduled = []
    monkeypatch.setattr(
        "server.workers.executor.schedule_reindex",
        lambda build_id: scheduled.append(build_id),
    )
    started = index_mod.begin_rebuild()
    assert scheduled == [started["id"]]
    index_mod.execute_rebuild(started["id"])
    return started


def test_backfill_copies_uploads_and_keeps_external_paths(monkeypatch, tmp_path):
    data = _use_temp_db(monkeypatch, tmp_path)
    uploads = data / "uploads"
    uploads.mkdir()
    upload = uploads / "owned.txt"
    upload.write_text("owned", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("leave-me", encoding="utf-8")

    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, storage)
               VALUES ('owned.txt', 'txt', ?, 5, 'ready', 0, 'external')""",
            (str(upload),),
        )
        owned_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, storage)
               VALUES ('outside.txt', 'txt', ?, 8, 'ready', 0, 'external')""",
            (str(outside),),
        )
        outside_id = int(cur.lastrowid)
        conn.commit()
        managed, external = files_mod.backfill_document_storage(conn)
        conn.commit()
    finally:
        conn.close()

    assert managed == 1
    assert external == 1
    copied = data / "library" / str(owned_id) / "original.txt"
    assert copied.read_text(encoding="utf-8") == "owned"
    assert upload.read_text(encoding="utf-8") == "owned"
    assert not (data / "library" / str(outside_id)).exists()

    conn = sqlite_mod.get_db()
    try:
        owned = conn.execute("SELECT storage, file_path, content_sha256 FROM documents WHERE id=?", (owned_id,)).fetchone()
        ext = conn.execute("SELECT storage, file_path FROM documents WHERE id=?", (outside_id,)).fetchone()
    finally:
        conn.close()
    assert owned["storage"] == "managed"
    assert owned["content_sha256"]
    assert not Path(owned["file_path"]).is_absolute()
    assert ext["storage"] == "external"
    assert ext["file_path"] == str(outside)

    again = sqlite_mod.get_db()
    try:
        assert files_mod.backfill_document_storage(again) == (0, 0)
    finally:
        again.close()

    files_mod.remove_managed_tree(owned_id)
    assert not copied.exists()
    assert upload.read_text(encoding="utf-8") == "owned"
    files_mod.remove_managed_tree(outside_id)
    assert outside.read_text(encoding="utf-8") == "leave-me"


def test_delete_refuses_to_follow_symlink_out_of_library(monkeypatch, tmp_path):
    data = _use_temp_db(monkeypatch, tmp_path)
    outside = tmp_path / "precious"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("keep", encoding="utf-8")
    link = data / "library" / "7"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)
    files_mod.remove_managed_tree(7)
    assert secret.read_text(encoding="utf-8") == "keep"
    assert not link.exists()


def test_mock_cannot_become_active_index(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("mock", "mock"))
    with pytest.raises(MockIndexError):
        index_mod.begin_rebuild()
    assert index_mod._fetch_one("active") is None
    with pytest.raises(IndexIdentityError, match=MISMATCH_MESSAGE):
        index_mod.assert_retrieval_identity()


def test_rebuild_switches_active_without_mixing_or_deleting(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    _prepare_chroma(monkeypatch, tmp_path)
    _insert_chunk("唯一句子")
    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("bge", "model-a"))

    first = _run_rebuild(monkeypatch)
    active = index_mod._fetch_one("active")
    assert active["id"] == first["id"]
    assert active["embed_provider"] == "bge"
    assert active["embed_model"] == "model-a"
    assert active["collection_name"] == f"documents_b{first['id']}"
    old_name = active["collection_name"]
    old = chroma_mod.get_chroma_client().get_collection(old_name)
    assert old.count() == 1
    meta = old.metadata or {}
    assert meta.get("index_build_id") == first["id"]
    assert meta.get("embed_provider") == "bge"
    assert meta.get("embed_model") == "model-a"

    from server.db.chromadb import query_chunks

    hits = query_chunks("唯一句子", top_k=3)
    assert [hit["text"] for hit in hits] == ["唯一句子"]

    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("ollama", "model-b"))
    with pytest.raises(IndexIdentityError) as mismatch:
        query_chunks("唯一句子", top_k=3)
    assert str(mismatch.value) == MISMATCH_MESSAGE
    with pytest.raises(IndexIdentityError):
        index_mod.prepare_embedding_target()
    assert chroma_mod.get_chroma_client().get_collection(old_name).count() == 1

    second = _run_rebuild(monkeypatch)
    assert second["id"] != first["id"]
    assert chroma_mod.get_chroma_client().get_collection(old_name).count() == 1
    new = chroma_mod.get_chroma_client().get_collection(f"documents_b{second['id']}")
    assert new.count() == 1
    hits = query_chunks("唯一句子", top_k=3)
    assert [hit["text"] for hit in hits] == ["唯一句子"]
    conn = sqlite_mod.get_db()
    try:
        retired = conn.execute(
            "SELECT status FROM index_builds WHERE id=?",
            (first["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert retired["status"] == "retired"


def test_second_rebuild_is_rejected_while_one_is_building(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("bge", "model-a"))
    monkeypatch.setattr("server.workers.executor.schedule_reindex", lambda build_id: None)
    index_mod.begin_rebuild()
    with pytest.raises(RebuildInProgress):
        index_mod.begin_rebuild()


def test_retrieve_returns_conflict_when_index_identity_differs(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    _prepare_chroma(monkeypatch, tmp_path)
    _insert_chunk()
    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("bge", "model-a"))
    _run_rebuild(monkeypatch)
    monkeypatch.setattr(index_mod, "current_embedding_identity", _identity("m3e", "model-c"))

    from server.core.retriever.retriever import retrieve

    with pytest.raises(HTTPException) as exc:
        retrieve("唯一句子", top_k=2)
    assert exc.value.status_code == 409
    assert exc.value.detail == MISMATCH_MESSAGE
