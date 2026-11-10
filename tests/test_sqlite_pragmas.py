"""SQLite connections use WAL and a bounded busy timeout."""
from server.db import sqlite as sqlite_mod


def test_get_db_enables_wal_and_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_mod, "DB_PATH", tmp_path / "tender.db")
    conn = sqlite_mod.get_db()
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()
    assert str(mode).lower() == "wal"
    assert int(timeout) >= 5000
    assert int(timeout) == sqlite_mod.SQLITE_BUSY_TIMEOUT_MS
