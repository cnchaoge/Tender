"""受管原件路径。

新文件放在 ``data/library/{id}/``。删除只移除这个目录，不删除资料库以外的路径。
``file_path`` 能放进 ``data/`` 时写成相对路径。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from pathlib import Path

from server.config import DATA_DIR

GLOSSARY_FILENAME = "内置投标术语表"
_GLOSSARY_PATH_MARK = "__glossary__"


def library_root() -> Path:
    return DATA_DIR / "library"


def resolve_stored_path(file_path: str | None) -> Path:
    """绝对路径原样使用，相对路径相对 ``data/``。"""
    raw = Path(file_path or "")
    if raw.is_absolute():
        return raw
    return DATA_DIR / raw


def relative_to_data(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(DATA_DIR.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def is_inside_library(path: Path) -> bool:
    root = library_root()
    if not _inside(path, root):
        return False
    try:
        return path.resolve() != root.resolve()
    except OSError:
        return False


def is_inside_data(path: Path) -> bool:
    return _inside(path, DATA_DIR)


def managed_dir(doc_id: int) -> Path:
    return library_root() / str(int(doc_id))


def incoming_path(suffix: str) -> Path:
    folder = library_root() / "_incoming"
    folder.mkdir(parents=True, exist_ok=True)
    from uuid import uuid4

    return folder / f"{uuid4().hex}{suffix}"


def move_into_library(doc_id: int, source: Path, suffix: str) -> Path:
    folder = managed_dir(doc_id)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"original{suffix}"
    os.replace(source, dest)
    return dest


def copy_into_library(doc_id: int, source: Path) -> Path:
    folder = managed_dir(doc_id)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"original{source.suffix.lower()}"
    if source.resolve() != dest.resolve():
        shutil.copyfile(source, dest)
    return dest


def write_original_bytes(doc_id: int, data: bytes, suffix: str) -> Path:
    folder = managed_dir(doc_id)
    folder.mkdir(parents=True, exist_ok=True)
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    dest = folder / f"original{suffix or '.bin'}"
    dest.write_bytes(data)
    return dest


def extracted_path(doc_id: int) -> Path:
    return managed_dir(doc_id) / "extracted.txt"


def read_extracted_text(doc_id: int) -> str | None:
    path = extracted_path(doc_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_extracted_text(doc_id: int, text: str) -> str:
    path = extracted_path(doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")
    return relative_to_data(path)


def remove_managed_tree(doc_id: int) -> None:
    """删除 ``data/library/{id}``。符号链接只卸掉链接，不删除链接目标。"""
    root = library_root().resolve()
    raw = managed_dir(doc_id)
    if raw.is_symlink():
        raw.unlink()
        return
    if not raw.exists():
        return
    resolved = raw.resolve()
    if resolved == root or not _inside(resolved, root):
        return
    shutil.rmtree(raw)


def backfill_document_storage(conn: sqlite3.Connection) -> tuple[int, int]:
    """把已有上传复制进资料库；库外旧路径标成 external，不移动用户文件。

    返回 ``(受管数, 外部数)``，只统计这次真正改写的行。
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT id, filename, file_type, file_path, storage, content_sha256, scope
           FROM documents"""
    )
    rows = list(cur.fetchall())
    managed = 0
    external = 0
    for row in rows:
        kind = _classify_existing(cur, row)
        if kind == "managed":
            managed += 1
        elif kind == "external":
            external += 1
    return managed, external


def _settled(row: sqlite3.Row, resolved: Path) -> bool:
    storage = row["storage"] or ""
    file_path = row["file_path"] or ""
    if storage == "managed" and row["content_sha256"] and not Path(file_path).is_absolute():
        return resolved.is_file() and is_inside_library(resolved)
    if storage == "external" and Path(file_path).is_absolute() and not is_inside_data(resolved):
        return bool(row["content_sha256"]) or not resolved.is_file()
    return False


def _classify_existing(cur: sqlite3.Cursor, row: sqlite3.Row) -> str:
    doc_id = int(row["id"])
    file_path = row["file_path"] or ""
    file_type = row["file_type"] or ""
    resolved = resolve_stored_path(file_path)
    if _settled(row, resolved):
        return ""
    if file_type == "glossary" or file_path == _GLOSSARY_PATH_MARK or row["filename"] == GLOSSARY_FILENAME:
        cur.execute(
            "UPDATE documents SET scope='system' WHERE id=? AND scope!='system'",
            (doc_id,),
        )
        return ""

    readable = resolved.is_file()
    digest = sha256_file(resolved) if readable else None
    if digest and _hash_taken(cur, digest, doc_id):
        digest = None

    if readable and is_inside_library(resolved):
        return _mark_managed(cur, row, resolved, digest)

    if readable and is_inside_data(resolved):
        dest = copy_into_library(doc_id, resolved)
        copied = sha256_file(dest)
        if _hash_taken(cur, copied, doc_id):
            copied = None
        return _mark_managed(cur, row, dest, copied)

    changed = (row["storage"] != "external") or (
        digest is not None and row["content_sha256"] != digest
    )
    cur.execute(
        """UPDATE documents
           SET storage='external',
               content_sha256=COALESCE(?, content_sha256),
               scope=CASE WHEN scope IS NULL OR scope='' THEN 'library' ELSE scope END
           WHERE id=?""",
        (digest, doc_id),
    )
    return "external" if changed else ""


def _mark_managed(cur: sqlite3.Cursor, row: sqlite3.Row, path: Path, digest: str | None) -> str:
    doc_id = int(row["id"])
    rel = relative_to_data(path)
    changed = (
        row["storage"] != "managed"
        or (row["file_path"] or "") != rel
        or (digest is not None and row["content_sha256"] != digest)
    )
    cur.execute(
        """UPDATE documents
           SET storage='managed',
               file_path=?,
               content_sha256=COALESCE(?, content_sha256),
               scope=CASE WHEN scope IS NULL OR scope='' THEN 'library' ELSE scope END
           WHERE id=?""",
        (rel, digest, doc_id),
    )
    return "managed" if changed else ""


def _hash_taken(cur: sqlite3.Cursor, digest: str, doc_id: int) -> bool:
    cur.execute(
        "SELECT id FROM documents WHERE content_sha256=? AND id!=?",
        (digest, doc_id),
    )
    return cur.fetchone() is not None
