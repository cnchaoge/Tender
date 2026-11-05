import sqlite3
from importlib import import_module


def test_retrieve_and_build_context(monkeypatch):
    retriever = import_module('server.core.retriever.retriever')

    chunks = [
        {'id': 'c1', 'text': 'foo', 'metadata': {'doc_id': 1}, 'distance': 0.2},
        {'id': 'c2', 'text': 'bar', 'metadata': {'doc_id': 2}, 'distance': 0.1},
        {'id': 'c3', 'text': 'baz', 'metadata': {}, 'distance': 0.5},
    ]

    monkeypatch.setattr(retriever, 'query_chunks', lambda q, top_k: chunks)

    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('CREATE TABLE documents (id INTEGER PRIMARY KEY, filename TEXT)')
    cur.executemany('INSERT INTO documents (id, filename) VALUES (?,?)', [(1, 'f1.pdf'), (2, 'f2.docx')])
    conn.commit()

    monkeypatch.setattr(retriever, 'get_db', lambda: conn)

    res = retriever.retrieve('query', top_k=2)
    assert len(res) == 2
    assert res[0]['filename'] in ('f1.pdf', 'f2.docx', 'unknown')

    ctx = retriever.build_context(res)
    assert '[参考1]' in ctx
