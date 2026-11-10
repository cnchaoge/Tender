"""Allowlist rules for knowledge-base folder import."""
import os
from pathlib import Path

from server.domain.documents.scan_paths import (
    is_scan_root_too_broad,
    parse_scan_root_entries,
    resolve_scan_roots,
)


def test_parse_scan_roots_accepts_comma_or_pathsep(tmp_path):
    one = tmp_path / "a"
    two = tmp_path / "b"
    assert parse_scan_root_entries(f" {one} , {two} ") == [str(one), str(two)]
    assert parse_scan_root_entries(f"{one}{os.pathsep}{two}") == [str(one), str(two)]
    assert parse_scan_root_entries("  ") == []


def test_home_root_and_ancestors_are_not_scan_roots(tmp_path):
    home = tmp_path / "home" / "me"
    bids = home / "bids"
    bids.mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    assert is_scan_root_too_broad(home, home=home)
    assert is_scan_root_too_broad(home.parent, home=home)
    assert is_scan_root_too_broad(tmp_path, home=home)
    assert is_scan_root_too_broad(Path(tmp_path.anchor), home=home)
    assert not is_scan_root_too_broad(bids, home=home)
    assert not is_scan_root_too_broad(tmp_path / "elsewhere", home=home)

    raw = ",".join(str(path) for path in (home, home.parent, tmp_path, bids))
    assert resolve_scan_roots(raw, home=home) == [bids.resolve()]


def test_real_home_directory_is_ignored_even_if_configured(tmp_path):
    bids = tmp_path / "bids"
    bids.mkdir()
    roots = resolve_scan_roots(f"{Path.home()},~/,{bids}")
    assert roots == [bids.resolve()]
    assert is_scan_root_too_broad(Path("~"))
    assert is_scan_root_too_broad(Path("/"))
