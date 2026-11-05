import sqlite3
import importlib

from server.core import glossary as glossary_mod


def test_init_builtin_glossary(monkeypatch):
    # Prepare small glossary
    glossary_mod.GLOSSARY_ENTRIES = [('term1', 'explanation1'), ('term2', 'explanation2')]

    # In-memory DB
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, file_type TEXT, file_path TEXT, file_size INTEGER, status TEXT, chunk_count INTEGER)')
    cur.execute('CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, chunk_index INTEGER, text TEXT, metadata TEXT)')
    conn.commit()

    # Provide a wrapper so init_builtin_glossary.close() doesn't close our underlying conn
    class DummyConn:
        def __init__(self, conn):
            self._conn = conn
        def cursor(self):
            return self._conn.cursor()
        def commit(self):
            return self._conn.commit()
        def close(self):
            # prevent closing underlying in-memory DB so test can inspect it
            pass

    # Monkeypatch get_db
    import server.db.sqlite as sqlite_mod
    monkeypatch.setattr(sqlite_mod, 'get_db', lambda: DummyConn(conn))

    # Capture add_chunks calls
    added = {}
    def fake_add_chunks(doc_id, records):
        added['doc_id'] = doc_id
        added['records'] = records
    import server.db.chromadb as chroma_mod
    monkeypatch.setattr(chroma_mod, 'add_chunks', fake_add_chunks)

    # Mock embedder
    class MockE:
        def embed(self, texts):
            return [[0.1]*4 for _ in texts]
    import server.core.embedder.embedder as emb_mod
    monkeypatch.setattr(emb_mod, 'get_embedder', lambda: MockE())

    # Run init
    glossary_mod.init_builtin_glossary()
    # Should have inserted a document and recorded chunks
    assert 'doc_id' in added
    assert len(added['records']) == 2

    # Check DB has exactly one document
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as c FROM documents')
    row = cur.fetchone()
    assert row['c'] == 1
