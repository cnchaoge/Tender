"""Limits for knowledge-base folder import.

Folder import may only read directories listed in ``KB_SCAN_ROOTS``. The home
directory, any ancestor of home, and a filesystem root are ignored so a
logged-in session cannot sweep the whole disk.
"""
from __future__ import annotations

import os
from pathlib import Path


def parse_scan_root_entries(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if "," in text:
        parts = text.split(",")
    else:
        parts = text.split(os.pathsep)
    cleaned: list[str] = []
    for part in parts:
        item = part.strip().strip('"').strip("'")
        if item:
            cleaned.append(item)
    return cleaned


def is_scan_root_too_broad(path: Path, home: Path | None = None) -> bool:
    """Reject a filesystem root, the home directory, and ancestors of home."""
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return True
    if resolved == Path(resolved.anchor):
        return True
    home_path = (Path.home() if home is None else home).expanduser().resolve()
    try:
        home_path.relative_to(resolved)
    except ValueError:
        return False
    return True


def is_path_within(path: Path, root: Path) -> bool:
    """True when ``path`` resolves to ``root`` or a path inside it.

    ``Path.resolve`` follows symlinks, so a link that points outside ``root``
    is not inside the allowlist.
    """
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def resolve_scan_roots(raw: str, *, home: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for entry in parse_scan_root_entries(raw):
        candidate = Path(entry).expanduser()
        if is_scan_root_too_broad(candidate, home=home):
            continue
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots
