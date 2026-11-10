#!/usr/bin/env python3
"""Copy one consistent Tender data set while the service is stopped.

Includes SQLite (and WAL/SHM sidecars when they exist), Chroma, the managed
library, legacy ``data/uploads`` when that directory is still present,
generated files, the project ``.env``, and ``data/.secret_key``.

SQLite and Chroma in the destination are from this same run. Do not open the
backup and the live ``data/`` directory from two processes at once.

``.env`` and ``data/.secret_key`` are secrets. Do not paste them into chat
or publish the backup through a public link.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Every entry is part of the set. Missing ones are recorded, not invented.
SET_PATHS = (
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

SECRET_PATHS = {".env", "data/.secret_key"}


class BackupError(RuntimeError):
    """The copy did not run."""


@dataclass(frozen=True)
class PlannedPath:
    relative: str
    source: Path
    present: bool
    secret: bool


def project_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def plan_paths(root: Path) -> list[PlannedPath]:
    items: list[PlannedPath] = []
    for relative in SET_PATHS:
        source = root / relative
        items.append(
            PlannedPath(
                relative=relative,
                source=source,
                present=source.exists(),
                secret=relative in SECRET_PATHS,
            )
        )
    return items


def format_plan(root: Path, items: list[PlannedPath]) -> str:
    lines = [f"backup plan root={root}"]
    for item in items:
        state = "PRESENT" if item.present else "ABSENT"
        secret = " secret" if item.secret else ""
        lines.append(f"{state} {item.relative}{secret}")
    lines.append(
        "note: copy SQLite and Chroma from this same run; "
        "do not open the backup and the live data directory at the same time"
    )
    lines.append(
        "note: .env and data/.secret_key are secrets; "
        "do not send them in chat or publish them with a public link"
    )
    return "\n".join(lines) + "\n"


def database_is_locked(path: Path) -> bool:
    if not path.is_file():
        return False
    conn = sqlite3.connect(path, timeout=0.3)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.rollback()
        return False
    except sqlite3.OperationalError as exc:
        return "locked" in str(exc).lower()
    finally:
        conn.close()


def locked_databases(root: Path) -> list[Path]:
    locked: list[Path] = []
    tender_db = root / "data" / "tender.db"
    if database_is_locked(tender_db):
        locked.append(tender_db)
    chroma = root / "data" / "chromadb"
    if chroma.is_dir():
        for path in sorted(chroma.rglob("*.sqlite3")):
            if database_is_locked(path):
                locked.append(path)
    return locked


def _destination_inside_source(root: Path, dest_parent: Path) -> bool:
    try:
        dest_parent.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _copy_file(src: Path, dest: Path, *, secret: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if secret:
        dest.write_bytes(src.read_bytes())
        _chmod_private(dest)
        return
    if src.is_symlink():
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(os.readlink(src))
        return
    shutil.copy2(src, dest)


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)


def _hold_exclusive(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    conn = sqlite3.connect(path, timeout=1)
    # Outside a transaction, this folds a leftover WAL into the main file.
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError:
        pass
    conn.execute("BEGIN EXCLUSIVE")
    return conn


def perform_backup(root: Path, dest_parent: Path, *, force: bool = False) -> Path:
    """Write ``dest_parent/tender-backup-<stamp>/`` and return that directory."""
    root = root.resolve()
    dest_parent = dest_parent.resolve()
    if _destination_inside_source(root, dest_parent):
        raise BackupError(
            "backup destination must be outside the project directory "
            "so the copy is not stored inside the live data set"
        )
    if not force:
        locked = locked_databases(root)
        if locked:
            joined = ", ".join(str(path) for path in locked)
            raise BackupError(
                "database is open by another process "
                f"({joined}). Stop Tender, then run the backup again. "
                "Pass --force only when you accept a copy taken while a "
                "process may still be writing."
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = dest_parent / f"tender-backup-{stamp}"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest.mkdir()
    try:
        os.chmod(dest, stat.S_IRWXU)
    except OSError:
        pass

    held: list[sqlite3.Connection] = []
    try:
        if not force:
            for path in (root / "data" / "tender.db",):
                conn = _hold_exclusive(path)
                if conn is not None:
                    held.append(conn)
            chroma = root / "data" / "chromadb"
            if chroma.is_dir():
                for path in sorted(chroma.rglob("*.sqlite3")):
                    conn = _hold_exclusive(path)
                    if conn is not None:
                        held.append(conn)
        items = plan_paths(root)
        for item in items:
            if not item.present:
                continue
            target = dest / item.relative
            if item.source.is_dir() and not item.source.is_symlink():
                _copy_tree(item.source, target)
            elif item.source.is_file() or item.source.is_symlink():
                _copy_file(item.source, target, secret=item.secret)
        manifest = dest / "MANIFEST.txt"
        manifest.write_text(format_plan(root, items), encoding="utf-8")
        _chmod_private(manifest)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    finally:
        for conn in held:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            conn.close()
    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="Tender project root")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Directory that will contain the backup folder (outside the project)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the path set and write nothing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Copy even if a database looks locked",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = (args.root or project_root_from_script()).resolve()
    items = plan_paths(root)
    text = format_plan(root, items)
    if args.dry_run:
        # Do not open the databases here. Opening them can checkpoint a WAL.
        sys.stdout.write(text)
        return 0
    if args.dest is None:
        sys.stderr.write("error: --dest is required unless --dry-run is set\n")
        return 2
    try:
        dest = perform_backup(root, args.dest, force=args.force)
    except BackupError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(text)
    sys.stdout.write(f"wrote {dest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
