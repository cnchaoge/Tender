"""The backup script copies one consistent path set and refuses a locked database."""
import sqlite3
import stat
from pathlib import Path

from scripts.backup_tender import BackupError, format_plan, main, perform_backup, plan_paths

EXPECTED = (
    "data/tender.db",
    "data/tender.db-wal",
    "data/tender.db-shm",
    "data/chromadb",
    "data/library",
    "data/uploads",
    "data/generated",
    ".env",
    "data/.secret_key",
)


def _sqlite_note(path: Path, note: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE marker (note TEXT)")
    conn.execute("INSERT INTO marker VALUES (?)", (note,))
    conn.commit()
    conn.close()


def _note(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT note FROM marker").fetchone()[0]
    finally:
        conn.close()


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    data = root / "data"
    _sqlite_note(data / "tender.db", "tender")
    _sqlite_note(data / "chromadb" / "chroma.sqlite3", "chroma")
    (data / "library" / "1").mkdir(parents=True)
    (data / "library" / "1" / "original.txt").write_text("managed", encoding="utf-8")
    (data / "uploads").mkdir()
    (data / "uploads" / "legacy.bin").write_bytes(b"legacy")
    (data / "generated").mkdir()
    (data / "generated" / "bid.docx").write_bytes(b"docx")
    (data / ".secret_key").write_text("jwt-secret\n", encoding="utf-8")
    (root / ".env").write_text("SECRET_KEY=not-for-chat\n", encoding="utf-8")
    return root


def test_plan_lists_sqlite_sidecars_when_present(tmp_path):
    root = _project(tmp_path)
    (root / "data" / "tender.db-wal").write_bytes(b"wal-bytes")
    (root / "data" / "tender.db-shm").write_bytes(b"shm-bytes")
    text = format_plan(root, plan_paths(root))
    assert "PRESENT data/tender.db-wal" in text
    assert "PRESENT data/tender.db-shm" in text
    assert "PRESENT data/library" in text
    assert "PRESENT data/uploads" in text
    assert "PRESENT .env secret" in text
    assert "PRESENT data/.secret_key secret" in text


def test_dry_run_lists_expected_paths_and_writes_nothing(tmp_path, capsys):
    root = _project(tmp_path)
    code = main(["--root", str(root), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 0
    for relative in EXPECTED:
        # Sidecars appear only when SQLite left them behind. A clean close has none.
        state = "ABSENT" if relative.endswith(("-wal", "-shm")) else "PRESENT"
        assert f"{state} {relative}" in captured.out
    assert "secret" in captured.out
    assert "do not open the backup and the live data directory" in captured.out
    assert not (tmp_path / "backups").exists()
    assert (root / "data" / "library" / "1" / "original.txt").read_text(encoding="utf-8") == "managed"


def test_backup_copies_library_uploads_secrets_and_sqlite_sidecars(tmp_path):
    root = _project(tmp_path)
    dest_parent = tmp_path / "backups"
    dest = perform_backup(root, dest_parent)
    assert dest.parent == dest_parent.resolve()
    assert _note(dest / "data" / "tender.db") == "tender"
    assert _note(dest / "data" / "chromadb" / "chroma.sqlite3") == "chroma"
    assert (dest / "data" / "library" / "1" / "original.txt").read_text(encoding="utf-8") == "managed"
    assert (dest / "data" / "uploads" / "legacy.bin").read_bytes() == b"legacy"
    assert (dest / "data" / "generated" / "bid.docx").read_bytes() == b"docx"
    assert (dest / ".env").read_text(encoding="utf-8") == "SECRET_KEY=not-for-chat\n"
    assert (dest / "data" / ".secret_key").read_text(encoding="utf-8") == "jwt-secret\n"
    assert (dest / ".env").stat().st_mode & 0o777 == stat.S_IRUSR | stat.S_IWUSR
    assert (dest / "data" / ".secret_key").stat().st_mode & 0o777 == stat.S_IRUSR | stat.S_IWUSR
    manifest = (dest / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "PRESENT data/library" in manifest
    assert "PRESENT data/uploads" in manifest
    assert "ABSENT data/tender.db-wal" in manifest
    assert "ABSENT data/tender.db-shm" in manifest
    assert (root / "data" / "uploads" / "legacy.bin").read_bytes() == b"legacy"


def test_backup_refuses_locked_database_and_destination_inside_project(tmp_path, capsys):
    root = _project(tmp_path)
    conn = sqlite3.connect(root / "data" / "tender.db")
    conn.execute("BEGIN EXCLUSIVE")
    try:
        code = main(["--root", str(root), "--dest", str(tmp_path / "backups")])
        captured = capsys.readouterr()
        assert code == 1
        assert "Stop Tender" in captured.err
        assert list((tmp_path / "backups").glob("tender-backup-*")) == []
    finally:
        conn.rollback()
        conn.close()

    try:
        perform_backup(root, root / "inside")
    except BackupError as exc:
        assert "outside the project" in str(exc)
    else:
        raise AssertionError("destination inside the project must be rejected")
