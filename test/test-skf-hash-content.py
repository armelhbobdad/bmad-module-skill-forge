#!/usr/bin/env python3
"""Tests for skf-hash-content.py.

Covers:
  - hash: content_hash + size_bytes + line_count; --include-path flag
  - compare: UNCHANGED / MODIFIED_FILE / DELETED_FILE classification
  - provenance shapes: top-level object with file_entries[]; bare array
  - guard against ../.. escapes from source-root
  - error paths: missing file, malformed JSON, missing file_entries key
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-hash-content.py"

spec = importlib.util.spec_from_file_location("skf_hash_content", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _expected_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _write(path: Path, content: str) -> Path:
    # binary write so newline-translation on Windows doesn't change
    # size_bytes / SHA-256 vs the bytes the test passed in
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


# --------------------------------------------------------------------------
# hash subcommand
# --------------------------------------------------------------------------


class TestHash:
    def test_basic_record(self, tmp_path: Path) -> None:
        content = "hello world\nsecond line\n"
        path = _write(tmp_path / "f.txt", content)
        rec = mod.hash_record(path)
        assert rec == {
            "content_hash": _expected_hash(content.encode()),
            "size_bytes": len(content),
            "line_count": 2,
        }

    def test_include_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "x.txt", "x\n")
        rec = mod.hash_record(path, include_path=True)
        assert rec["path"] == str(path)
        assert "content_hash" in rec

    def test_empty_file(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "empty.txt", "")
        rec = mod.hash_record(path)
        assert rec["content_hash"] == _expected_hash(b"")
        assert rec["size_bytes"] == 0
        assert rec["line_count"] == 0

    def test_binary_content(self, tmp_path: Path) -> None:
        # bytes that aren't valid UTF-8 — hash should still work
        path = tmp_path / "blob.bin"
        path.write_bytes(b"\x00\x01\xff\xfe\n")
        rec = mod.hash_record(path)
        assert rec["content_hash"] == _expected_hash(b"\x00\x01\xff\xfe\n")
        assert rec["line_count"] == 1

    def test_no_trailing_newline_line_count(self, tmp_path: Path) -> None:
        # line_count counts newlines, not "lines that have content"
        path = _write(tmp_path / "f.txt", "one\ntwo")  # 1 newline, 2 lines of text
        rec = mod.hash_record(path)
        assert rec["line_count"] == 1


# --------------------------------------------------------------------------
# load_file_entries
# --------------------------------------------------------------------------


class TestLoadFileEntries:
    def test_object_with_file_entries(self, tmp_path: Path) -> None:
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({
                "file_entries": [
                    {"source_file": "scripts/a.sh", "content_hash": "sha256:abc"},
                    {"source_file": "assets/b.json", "content_hash": "sha256:def"},
                ]
            }),
        )
        entries = mod.load_file_entries(prov)
        assert len(entries) == 2
        assert entries[0]["source_file"] == "scripts/a.sh"

    def test_bare_array(self, tmp_path: Path) -> None:
        prov = _write(
            tmp_path / "prov.json",
            json.dumps([{"source_file": "x.md", "content_hash": "sha256:z"}]),
        )
        entries = mod.load_file_entries(prov)
        assert entries == [{"source_file": "x.md", "content_hash": "sha256:z"}]

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", "{not json")
        import pytest

        with pytest.raises(ValueError, match="failed to read"):
            mod.load_file_entries(prov)

    def test_object_missing_file_entries_raises(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", "{}")
        import pytest

        with pytest.raises(ValueError, match="no `file_entries`"):
            mod.load_file_entries(prov)

    def test_file_entries_not_array_raises(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", '{"file_entries": "not an array"}')
        import pytest

        with pytest.raises(ValueError, match="not an array"):
            mod.load_file_entries(prov)

    def test_top_level_scalar_raises(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", "42")
        import pytest

        with pytest.raises(ValueError, match="must be an object or array"):
            mod.load_file_entries(prov)


# --------------------------------------------------------------------------
# classify_entry / compare
# --------------------------------------------------------------------------


class TestClassifyEntry:
    def test_unchanged(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        f = _write(source / "scripts" / "a.sh", "echo hi\n")
        stored = _expected_hash(b"echo hi\n")
        result = mod.classify_entry(
            source, {"source_file": "scripts/a.sh", "content_hash": stored}
        )
        assert result["classification"] == "UNCHANGED"
        assert result["current_hash"] == stored

    def test_modified(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "echo new content\n")
        result = mod.classify_entry(
            source,
            {"source_file": "scripts/a.sh", "content_hash": "sha256:oldhash"},
        )
        assert result["classification"] == "MODIFIED_FILE"
        assert result["stored_hash"] == "sha256:oldhash"
        assert result["current_hash"] != "sha256:oldhash"

    def test_deleted(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        result = mod.classify_entry(
            source,
            {"source_file": "scripts/gone.sh", "content_hash": "sha256:was-here"},
        )
        assert result["classification"] == "DELETED_FILE"
        assert result["current_hash"] is None
        assert result["current_size_bytes"] is None

    def test_path_escape_treated_as_deleted(self, tmp_path: Path) -> None:
        # source_file with ../.. attempting to escape source-root → DELETED
        source = tmp_path / "src"
        source.mkdir()
        # write a real file outside the source-root
        _write(tmp_path / "outside.txt", "outside\n")
        result = mod.classify_entry(
            source,
            {"source_file": "../outside.txt", "content_hash": "sha256:x"},
        )
        assert result["classification"] == "DELETED_FILE"

    def test_missing_source_file_field_raises(self, tmp_path: Path) -> None:
        import pytest

        with pytest.raises(ValueError, match="source_file"):
            mod.classify_entry(tmp_path, {"content_hash": "sha256:x"})


class TestCompare:
    def test_mixed_classifications(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "a.sh", "unchanged content\n")
        _write(source / "b.sh", "modified content\n")
        # c.sh missing → DELETED
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({
                "file_entries": [
                    {"source_file": "a.sh", "content_hash": _expected_hash(b"unchanged content\n")},
                    {"source_file": "b.sh", "content_hash": "sha256:stale"},
                    {"source_file": "c.sh", "content_hash": "sha256:was-here"},
                ]
            }),
        )
        result = mod.compare(source, prov)
        assert result["stats"] == {"total": 3, "unchanged": 1, "modified": 1, "deleted": 1}
        # check ordering preserved
        classifications = [c["classification"] for c in result["comparisons"]]
        assert classifications == ["UNCHANGED", "MODIFIED_FILE", "DELETED_FILE"]

    def test_empty_provenance(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = _write(tmp_path / "prov.json", '{"file_entries": []}')
        result = mod.compare(source, prov)
        assert result == {
            "comparisons": [],
            "stats": {"total": 0, "unchanged": 0, "modified": 0, "deleted": 0},
        }


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_hash_emits_json(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "x.txt", "hello\n")
        result = _run_cli("hash", str(path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["content_hash"] == _expected_hash(b"hello\n")
        assert payload["size_bytes"] == 6
        assert payload["line_count"] == 1
        # without --include-path, the field is absent
        assert "path" not in payload

    def test_hash_include_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "x.txt", "x\n")
        result = _run_cli("hash", str(path), "--include-path")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["path"] == str(path)

    def test_hash_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("hash", str(tmp_path / "missing.txt"))
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_compare_emits_json(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "a.sh", "x\n")
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({
                "file_entries": [
                    {"source_file": "a.sh", "content_hash": _expected_hash(b"x\n")}
                ]
            }),
        )
        result = _run_cli("compare", str(source), "--provenance-map", str(prov))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stats"]["unchanged"] == 1

    def test_compare_bad_source_exits_1(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", '{"file_entries": []}')
        result = _run_cli(
            "compare", str(tmp_path / "missing"), "--provenance-map", str(prov)
        )
        assert result.returncode == 1
        assert "source root" in result.stderr

    def test_compare_bad_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        result = _run_cli(
            "compare", str(source), "--provenance-map", str(tmp_path / "missing.json")
        )
        assert result.returncode == 1
        assert "provenance map" in result.stderr

    def test_compare_malformed_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = _write(tmp_path / "prov.json", "{not json")
        result = _run_cli("compare", str(source), "--provenance-map", str(prov))
        assert result.returncode == 1
        assert "failed to read" in result.stderr
