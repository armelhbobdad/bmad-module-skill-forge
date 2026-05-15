#!/usr/bin/env python3
"""Tests for skf-compare-file-hashes.py.

Covers:
  - compare: added (new file in source tree, not in provenance),
             removed (provenance row, file missing on disk),
             changed (hash mismatch),
             unchanged (hash match, counted only)
  - hash-prefix normalization: bare-hex stored vs sha256: stored both
    correctly equal a freshly computed prefixed hash
  - inverse walk: respects SCRIPT_DIRS / ASSET_DIRS / DOC_DIR_PREFIXES;
    prunes EXCLUDED_DIR_NAMES; skips binary extensions; ignores files
    outside the tracked directory taxonomy
  - load_file_entries: accepts both top-level object and bare-array shapes;
    missing `file_entries` key returns []; malformed JSON raises
  - CLI smoke: shape conformance + exit codes
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-compare-file-hashes.py"

spec = importlib.util.spec_from_file_location("skf_compare_file_hashes", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _bare_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# normalize_hash
# --------------------------------------------------------------------------


class TestNormalizeHash:
    def test_strips_sha256_prefix(self) -> None:
        assert mod.normalize_hash("sha256:abcdef") == "abcdef"

    def test_idempotent_on_bare_hex(self) -> None:
        # no leading lowercase-alphanumeric prefix-with-colon → unchanged
        assert mod.normalize_hash("abcdef1234567890") == "abcdef1234567890"

    def test_strips_alt_algorithm_prefix(self) -> None:
        assert mod.normalize_hash("sha1:cafebabe") == "cafebabe"
        assert mod.normalize_hash("md5:deadbeef") == "deadbeef"

    def test_none_input_returns_none(self) -> None:
        assert mod.normalize_hash(None) is None

    def test_non_string_returns_none(self) -> None:
        assert mod.normalize_hash(42) is None


# --------------------------------------------------------------------------
# load_file_entries
# --------------------------------------------------------------------------


class TestLoadFileEntries:
    def test_object_with_file_entries(self, tmp_path: Path) -> None:
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [{"source_file": "scripts/a.sh", "content_hash": "sha256:x"}]},
        )
        entries = mod.load_file_entries(prov)
        assert entries == [{"source_file": "scripts/a.sh", "content_hash": "sha256:x"}]

    def test_object_without_file_entries_returns_empty(self, tmp_path: Path) -> None:
        # A single-skill with no scripts/assets/docs may omit the field per
        # skill-sections.md — should not raise.
        prov = _write_json(tmp_path / "p.json", {"entries": []})
        assert mod.load_file_entries(prov) == []

    def test_bare_array(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", [{"source_file": "x.md"}])
        assert mod.load_file_entries(prov) == [{"source_file": "x.md"}]

    def test_file_entries_not_array_raises(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", {"file_entries": "nope"})
        import pytest

        with pytest.raises(ValueError, match="not an array"):
            mod.load_file_entries(prov)

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        prov = tmp_path / "p.json"
        prov.write_text("{not json", encoding="utf-8")
        import pytest

        with pytest.raises(ValueError, match="malformed JSON"):
            mod.load_file_entries(prov)


# --------------------------------------------------------------------------
# candidate_source_files (inverse walk)
# --------------------------------------------------------------------------


class TestCandidateSourceFiles:
    def test_finds_scripts_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "build.sh", "echo")
        _write(source / "scripts" / "deploy.py", "print('x')")
        assert sorted(mod.candidate_source_files(source)) == [
            "scripts/build.sh",
            "scripts/deploy.py",
        ]

    def test_finds_assets_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "assets" / "template.md", "...")
        _write(source / "schemas" / "config.json", "{}")
        assert sorted(mod.candidate_source_files(source)) == [
            "assets/template.md",
            "schemas/config.json",
        ]

    def test_finds_doc_prefix(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "docs" / "authoritative" / "llms.txt", "...")
        assert list(mod.candidate_source_files(source)) == [
            "docs/authoritative/llms.txt"
        ]

    def test_skips_non_tracked_directories(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "src" / "main.ts", "...")  # not tracked
        _write(source / "lib" / "util.py", "...")  # not tracked
        _write(source / "scripts" / "ok.sh", "...")
        assert list(mod.candidate_source_files(source)) == ["scripts/ok.sh"]

    def test_prunes_excluded_dirs(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "real.sh", "...")
        _write(source / "node_modules" / "scripts" / "fake.sh", "...")
        _write(source / "dist" / "scripts" / "fake2.sh", "...")
        _write(source / "__pycache__" / "scripts" / "fake3.sh", "...")
        assert list(mod.candidate_source_files(source)) == ["scripts/real.sh"]

    def test_skips_binary_extensions(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "assets" / "logo.png", "")
        _write(source / "assets" / "doc.md", "")
        assert list(mod.candidate_source_files(source)) == ["assets/doc.md"]

    def test_handles_nested_tracked_dirs(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "packages" / "core" / "scripts" / "build.sh", "...")
        # Any depth — segment-match anywhere in path qualifies
        assert list(mod.candidate_source_files(source)) == [
            "packages/core/scripts/build.sh"
        ]


# --------------------------------------------------------------------------
# compare end-to-end
# --------------------------------------------------------------------------


class TestCompare:
    def test_mixed_added_removed_changed_unchanged(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        # unchanged: tracked, file present, hash matches
        _write(source / "scripts" / "a.sh", "unchanged\n")
        # changed: tracked, file present, hash differs
        _write(source / "scripts" / "b.sh", "new content\n")
        # added: present on disk, NOT in provenance — must be in a tracked dir
        _write(source / "scripts" / "c.sh", "brand new\n")
        # removed: in provenance but not on disk → no file written for d.sh

        prov = _write_json(
            tmp_path / "p.json",
            {
                "file_entries": [
                    {
                        "source_file": "scripts/a.sh",
                        "content_hash": _sha256(b"unchanged\n"),
                    },
                    {
                        "source_file": "scripts/b.sh",
                        "content_hash": "sha256:stalehashvalue",
                    },
                    {
                        "source_file": "scripts/d.sh",
                        "content_hash": "sha256:was-here",
                    },
                ]
            },
        )
        result = mod.compare(source, prov)
        assert result["stats"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}
        assert result["added"] == ["scripts/c.sh"]
        assert result["removed"] == ["scripts/d.sh"]
        assert len(result["changed"]) == 1
        assert result["changed"][0]["path"] == "scripts/b.sh"
        assert result["changed"][0]["stored_hash"] == "sha256:stalehashvalue"
        assert result["changed"][0]["current_hash"] == _sha256(b"new content\n")

    def test_unchanged_with_bare_hex_stored_hash(self, tmp_path: Path) -> None:
        # Writer-vs-reader hash-prefix story: stored hash without sha256:
        # prefix must still compare equal to a freshly computed prefixed hash.
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "content\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts/a.sh", "content_hash": _bare_hex(b"content\n")},
            ]},
        )
        result = mod.compare(source, prov)
        assert result["stats"] == {"added": 0, "removed": 0, "changed": 0, "unchanged": 1}

    def test_empty_provenance_returns_empty_added_if_no_candidates(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov)
        assert result == {
            "added": [],
            "removed": [],
            "changed": [],
            "stats": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
        }

    def test_empty_provenance_with_disk_candidates_yields_added(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov)
        assert result["added"] == ["scripts/new.sh"]
        assert result["stats"]["added"] == 1

    def test_provenance_missing_file_entries_field_ok(self, tmp_path: Path) -> None:
        # provenance with no scripts/assets/docs may omit field entirely;
        # candidate walk still produces added[] from disk
        source = tmp_path / "src"
        _write(source / "scripts" / "x.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"entries": []})
        result = mod.compare(source, prov)
        assert result["added"] == ["scripts/x.sh"]

    def test_paths_are_posix_form(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        # nested dirs to make sure path normalization happens
        _write(source / "packages" / "core" / "scripts" / "build.sh", "x\n")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov)
        assert result["added"] == ["packages/core/scripts/build.sh"]
        for p in result["added"] + result["removed"]:
            assert "\\" not in p

    def test_provenance_entry_path_backslash_normalized(self, tmp_path: Path) -> None:
        # If a provenance entry was written with backslash separators
        # (legacy Windows writer), we should still find it on disk.
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts\\a.sh", "content_hash": _sha256(b"x\n")},
            ]},
        )
        result = mod.compare(source, prov)
        assert result["stats"]["unchanged"] == 1


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
    def test_compare_emits_json_shape(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts/a.sh", "content_hash": _sha256(b"x\n")},
            ]},
        )
        result = _run_cli("compare", str(prov), str(source))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert set(payload.keys()) == {"added", "removed", "changed", "stats"}
        assert set(payload["stats"].keys()) == {"added", "removed", "changed", "unchanged"}
        assert payload["stats"]["unchanged"] == 1

    def test_compare_missing_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        result = _run_cli("compare", str(tmp_path / "missing.json"), str(source))
        assert result.returncode == 1
        assert "provenance map" in result.stderr

    def test_compare_missing_source_exits_1(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = _run_cli("compare", str(prov), str(tmp_path / "missing"))
        assert result.returncode == 1
        assert "source root" in result.stderr

    def test_compare_malformed_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = tmp_path / "p.json"
        prov.write_text("{not json", encoding="utf-8")
        result = _run_cli("compare", str(prov), str(source))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr
