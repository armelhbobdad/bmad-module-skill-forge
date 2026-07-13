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
        # path is emitted in forward-slash form for cross-platform JSON
        assert rec["path"] == path.as_posix()
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
# [MANUAL] block extraction / verification
# --------------------------------------------------------------------------


# A fixture SKILL.md with three named [MANUAL] blocks under three headings.
_FIXTURE = (
    "# My Skill\n"
    "\n"
    "## Usage Patterns\n"
    "\n"
    "Some generated text.\n"
    "\n"
    "<!-- [MANUAL:extra-notes] -->\n"
    "Line one of developer notes.\n"
    "Line two of developer notes.\n"
    "<!-- [/MANUAL:extra-notes] -->\n"
    "\n"
    "## Conventions\n"
    "\n"
    "More generated content.\n"
    "\n"
    "<!-- [MANUAL:gotchas] -->\n"
    "Watch out for the frobnicator.\n"
    "<!-- [/MANUAL:gotchas] -->\n"
    "\n"
    "## Extras\n"
    "\n"
    "<!-- [MANUAL:third-block] -->\n"
    "Third block content here.\n"
    "<!-- [/MANUAL:third-block] -->\n"
)

_GOTCHAS_BLOCK = (
    "<!-- [MANUAL:gotchas] -->\n"
    "Watch out for the frobnicator.\n"
    "<!-- [/MANUAL:gotchas] -->\n"
)


class TestFindManualBlocks:
    def test_extracts_all_blocks_in_order(self) -> None:
        blocks = mod.find_manual_blocks(_FIXTURE.encode("utf-8"))
        assert [b["name"] for b in blocks] == ["extra-notes", "gotchas", "third-block"]
        # sorted ascending by byte_offset
        offsets = [b["byte_offset"] for b in blocks]
        assert offsets == sorted(offsets)

    def test_parent_heading_mapping(self) -> None:
        blocks = mod.find_manual_blocks(_FIXTURE.encode("utf-8"))
        by_name = {b["name"]: b for b in blocks}
        assert by_name["extra-notes"]["parent_heading"] == "Usage Patterns"
        assert by_name["gotchas"]["parent_heading"] == "Conventions"
        assert by_name["third-block"]["parent_heading"] == "Extras"

    def test_content_hash_is_byte_exact_interior(self) -> None:
        blocks = mod.find_manual_blocks(_FIXTURE.encode("utf-8"))
        gotchas = next(b for b in blocks if b["name"] == "gotchas")
        # interior = bytes between the open marker's `-->` and the close `<!--`
        interior = b"\nWatch out for the frobnicator.\n"
        assert gotchas["content_hash"] == _expected_hash(interior)

    def test_no_blocks(self) -> None:
        assert mod.find_manual_blocks(b"# Just a heading\n\nNo markers here.\n") == []

    def test_block_with_no_preceding_heading(self) -> None:
        data = b"<!-- [MANUAL:top] -->\nhi\n<!-- [/MANUAL:top] -->\n"
        blocks = mod.find_manual_blocks(data)
        assert len(blocks) == 1
        assert blocks[0]["parent_heading"] is None

    def test_unclosed_marker_skipped(self) -> None:
        data = b"## H\n<!-- [MANUAL:dangling] -->\nno close marker here\n"
        assert mod.find_manual_blocks(data) == []

    def test_whitespace_tolerant_markers(self) -> None:
        data = b"##  H\n<!--   [MANUAL:spaced]   -->\nx\n<!--  [/MANUAL:spaced]  -->\n"
        blocks = mod.find_manual_blocks(data)
        assert [b["name"] for b in blocks] == ["spaced"]


class TestManualInventory:
    def test_inventory_shape(self, tmp_path: Path) -> None:
        f = _write(tmp_path / "SKILL.md", _FIXTURE)
        inv = mod.manual_inventory(f)
        assert inv["count"] == 3
        assert len(inv["blocks"]) == 3
        assert all(
            set(b) == {"name", "content_hash", "byte_offset", "parent_heading"}
            for b in inv["blocks"]
        )


class TestManualVerify:
    def _inv_path(self, tmp_path: Path) -> Path:
        src = _write(tmp_path / "SKILL.md", _FIXTURE)
        inv = mod.manual_inventory(src)
        return _write(tmp_path / "inv.json", json.dumps(inv))

    def test_identical_all_preserved(self, tmp_path: Path) -> None:
        inv = self._inv_path(tmp_path)
        target = _write(tmp_path / "post.md", _FIXTURE)
        result = mod.manual_verify(inv, target)
        assert result["preserved"] == ["extra-notes", "gotchas", "third-block"]
        assert result["modified"] == []
        assert result["missing"] == []
        assert result["moved"] == []
        assert result["ok"] is True

    def test_interior_truncation_is_modified(self, tmp_path: Path) -> None:
        # Delete one interior line — marker count is UNCHANGED, so this is the
        # blind spot a marker-count-only gate silently passes.
        inv = self._inv_path(tmp_path)
        truncated = _FIXTURE.replace("Line two of developer notes.\n", "")
        target = _write(tmp_path / "post.md", truncated)
        result = mod.manual_verify(inv, target)
        assert result["modified"] == ["extra-notes"]
        assert result["ok"] is False

    def test_removed_markers_is_missing(self, tmp_path: Path) -> None:
        inv = self._inv_path(tmp_path)
        removed = _FIXTURE.replace(
            "<!-- [MANUAL:third-block] -->\n"
            "Third block content here.\n"
            "<!-- [/MANUAL:third-block] -->\n",
            "",
        )
        target = _write(tmp_path / "post.md", removed)
        result = mod.manual_verify(inv, target)
        assert result["missing"] == ["third-block"]
        assert result["ok"] is False

    def test_relocated_block_is_moved_not_failed(self, tmp_path: Path) -> None:
        # Byte-identical block relocated under a different heading.
        inv = self._inv_path(tmp_path)
        relocated = _FIXTURE.replace(_GOTCHAS_BLOCK, "")
        relocated = relocated.replace("## Extras\n", "## Extras\n\n" + _GOTCHAS_BLOCK)
        target = _write(tmp_path / "post.md", relocated)
        result = mod.manual_verify(inv, target)
        assert result["moved"] == ["gotchas"]
        assert result["modified"] == []
        assert result["missing"] == []
        assert result["ok"] is True

    def test_inventory_accepts_bare_blocks_array(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "SKILL.md", _FIXTURE)
        inv = mod.manual_inventory(src)
        bare = _write(tmp_path / "bare.json", json.dumps(inv["blocks"]))
        target = _write(tmp_path / "post.md", _FIXTURE)
        result = mod.manual_verify(bare, target)
        assert result["ok"] is True
        assert result["preserved"] == ["extra-notes", "gotchas", "third-block"]

    def test_malformed_inventory_raises(self, tmp_path: Path) -> None:
        import pytest

        bad = _write(tmp_path / "inv.json", "{not json")
        target = _write(tmp_path / "post.md", _FIXTURE)
        with pytest.raises(ValueError, match="failed to read"):
            mod.manual_verify(bad, target)

    def test_inventory_object_missing_blocks_raises(self, tmp_path: Path) -> None:
        import pytest

        bad = _write(tmp_path / "inv.json", "{}")
        target = _write(tmp_path / "post.md", _FIXTURE)
        with pytest.raises(ValueError, match="no `blocks`"):
            mod.manual_verify(bad, target)


class TestClassifyManualBlocks:
    def test_all_buckets_mutually_exclusive(self) -> None:
        inv = [
            {"name": "keep", "content_hash": "sha256:a", "parent_heading": "H1"},
            {"name": "edit", "content_hash": "sha256:b", "parent_heading": "H2"},
            {"name": "gone", "content_hash": "sha256:c", "parent_heading": "H3"},
            {"name": "shift", "content_hash": "sha256:d", "parent_heading": "H4"},
        ]
        cur = [
            {"name": "keep", "content_hash": "sha256:a", "parent_heading": "H1"},
            {"name": "edit", "content_hash": "sha256:CHANGED", "parent_heading": "H2"},
            {"name": "shift", "content_hash": "sha256:d", "parent_heading": "H-NEW"},
        ]
        result = mod.classify_manual_blocks(inv, cur)
        assert result == {
            "preserved": ["keep"],
            "modified": ["edit"],
            "missing": ["gone"],
            "moved": ["shift"],
            "ok": False,
        }

    def test_empty_inventory_is_ok(self) -> None:
        result = mod.classify_manual_blocks([], [])
        assert result == {
            "preserved": [],
            "modified": [],
            "missing": [],
            "moved": [],
            "ok": True,
        }


# --------------------------------------------------------------------------
# normalize_hash
# --------------------------------------------------------------------------


class TestNormalizeHash:
    def test_strips_sha256_prefix(self) -> None:
        assert mod.normalize_hash("sha256:abc123") == "abc123"

    def test_bare_hex_unchanged(self) -> None:
        assert mod.normalize_hash("abc123") == "abc123"

    def test_strips_only_first_prefix(self) -> None:
        # only one leading algorithm-name prefix is stripped
        assert mod.normalize_hash("sha1:sha256:x") == "sha256:x"

    def test_none_returns_none(self) -> None:
        assert mod.normalize_hash(None) is None
        assert mod.normalize_hash(42) is None


# --------------------------------------------------------------------------
# load_constituents / compare_constituents (compose-mode stack drift)
# --------------------------------------------------------------------------


def _write_constituent(skills_root: Path, skill_path: str, skill_name: str, content: str) -> str:
    """Write a constituent metadata.json at
    {skills_root}/{skill_path}/active/{skill_name}/metadata.json and return
    its sha256:-prefixed content hash (writer convention)."""
    meta = skills_root / skill_path / "active" / skill_name / "metadata.json"
    _write(meta, content)
    return _expected_hash(content.encode("utf-8"))


class TestLoadConstituents:
    def test_object_with_constituents(self, tmp_path: Path) -> None:
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [{"skill_name": "a", "skill_path": "skills/a"}]}),
        )
        assert mod.load_constituents(prov) == [{"skill_name": "a", "skill_path": "skills/a"}]

    def test_bare_array(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", json.dumps([{"skill_name": "a"}]))
        assert mod.load_constituents(prov) == [{"skill_name": "a"}]

    def test_object_missing_constituents_is_empty(self, tmp_path: Path) -> None:
        # a single skill omits the array entirely — valid, no drift
        prov = _write(tmp_path / "prov.json", json.dumps({"skill_name": "solo"}))
        assert mod.load_constituents(prov) == []

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        import pytest

        prov = _write(tmp_path / "prov.json", "{not json")
        with pytest.raises(ValueError, match="malformed JSON"):
            mod.load_constituents(prov)

    def test_constituents_not_array_raises(self, tmp_path: Path) -> None:
        import pytest

        prov = _write(tmp_path / "prov.json", '{"constituents": "nope"}')
        with pytest.raises(ValueError, match="not an array"):
            mod.load_constituents(prov)

    def test_top_level_scalar_raises(self, tmp_path: Path) -> None:
        import pytest

        prov = _write(tmp_path / "prov.json", "7")
        with pytest.raises(ValueError, match="must be an object or array"):
            mod.load_constituents(prov)


class TestCompareConstituents:
    def test_fresh_when_metadata_unchanged(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        h = _write_constituent(skills, "skills/alpha", "alpha", '{"name":"alpha"}')
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "alpha", "skill_path": "skills/alpha", "metadata_hash": h}
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert result["fresh"] == [{"skill_name": "alpha"}]
        assert result["drifted"] == []
        assert result["stats"] == {
            "total": 1, "drifted": 0, "fresh": 1, "missing": 0, "skipped_null_hash": 0
        }

    def test_drifted_when_metadata_changed(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        # write the CURRENT (changed) metadata; store a stale baseline hash
        _write_constituent(skills, "skills/beta", "beta", '{"name":"beta","v":2}')
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "beta", "skill_path": "skills/beta", "metadata_hash": "sha256:stalehash"}
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert len(result["drifted"]) == 1
        d = result["drifted"][0]
        assert d["skill_name"] == "beta"
        assert d["stored_hash"] == "sha256:stalehash"
        assert d["current_hash"].startswith("sha256:")
        assert d["current_hash"] != "sha256:stalehash"
        assert result["stats"]["drifted"] == 1

    def test_missing_when_metadata_absent(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        skills.mkdir()
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "gone", "skill_path": "skills/gone", "metadata_hash": "sha256:x"}
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert result["missing"] == [
            {"skill_name": "gone", "skill_path": "skills/gone",
             "stored_hash": "sha256:x", "reason": "metadata-not-found"}
        ]
        assert result["stats"]["missing"] == 1

    def test_incomplete_record_is_missing(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        skills.mkdir()
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_path": "skills/x", "metadata_hash": "sha256:x"},  # no skill_name
                "not-a-dict",
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        reasons = [m["reason"] for m in result["missing"]]
        assert reasons == ["incomplete-record", "incomplete-record"]
        assert result["stats"]["total"] == 2
        assert result["stats"]["missing"] == 2

    def test_null_metadata_hash_is_skipped(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        _write_constituent(skills, "skills/n", "n", "{}")
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "n", "skill_path": "skills/n", "metadata_hash": None}
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert result["skipped_null_hash"] == [{"skill_name": "n"}]
        assert result["drifted"] == [] and result["fresh"] == []
        assert result["stats"]["skipped_null_hash"] == 1

    def test_bare_hex_stored_hash_matches_prefixed(self, tmp_path: Path) -> None:
        # writer stored a bare-hex hash (no sha256: prefix) — must still match
        skills = tmp_path / "root"
        h = _write_constituent(skills, "skills/p", "p", '{"k":1}')
        bare = mod.normalize_hash(h)  # strip the sha256: prefix
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "p", "skill_path": "skills/p", "metadata_hash": bare}
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert result["fresh"] == [{"skill_name": "p"}]

    def test_absolute_skill_path_ignores_skills_root(self, tmp_path: Path) -> None:
        # skill_path is absolute → --skills-root is not prepended
        abs_base = tmp_path / "elsewhere"
        h = _write_constituent(abs_base, "gamma-pkg", "gamma", '{"name":"gamma"}')
        skill_path = str(abs_base / "gamma-pkg")
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "gamma", "skill_path": skill_path, "metadata_hash": h}
            ]}),
        )
        # an unrelated skills-root is passed — the absolute skill_path must win
        unrelated = tmp_path / "unrelated-root"
        unrelated.mkdir()
        result = mod.compare_constituents(prov, unrelated)
        assert result["fresh"] == [{"skill_name": "gamma"}]

    def test_no_constituents_all_empty(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        skills.mkdir()
        prov = _write(tmp_path / "prov.json", json.dumps({"skill_name": "solo"}))
        result = mod.compare_constituents(prov, skills)
        assert result == {
            "drifted": [], "fresh": [], "missing": [], "skipped_null_hash": [],
            "stats": {"total": 0, "drifted": 0, "fresh": 0, "missing": 0, "skipped_null_hash": 0},
        }

    def test_mixed_buckets_sorted_by_name(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        h_fresh = _write_constituent(skills, "skills/zeta", "zeta", '{"z":1}')
        _write_constituent(skills, "skills/alpha", "alpha", '{"a":2}')  # changed vs stale
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "zeta", "skill_path": "skills/zeta", "metadata_hash": h_fresh},
                {"skill_name": "alpha", "skill_path": "skills/alpha", "metadata_hash": "sha256:stale"},
                {"skill_name": "mu", "skill_path": "skills/mu", "metadata_hash": "sha256:m"},  # absent
            ]}),
        )
        result = mod.compare_constituents(prov, skills)
        assert [d["skill_name"] for d in result["drifted"]] == ["alpha"]
        assert result["fresh"] == [{"skill_name": "zeta"}]
        assert [m["skill_name"] for m in result["missing"]] == ["mu"]
        assert result["stats"] == {
            "total": 3, "drifted": 1, "fresh": 1, "missing": 1, "skipped_null_hash": 0
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
        assert payload["path"] == path.as_posix()

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

    def test_manual_inventory_emits_json(self, tmp_path: Path) -> None:
        f = _write(tmp_path / "SKILL.md", _FIXTURE)
        result = _run_cli("manual-inventory", str(f))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["count"] == 3
        assert [b["name"] for b in payload["blocks"]] == [
            "extra-notes",
            "gotchas",
            "third-block",
        ]

    def test_manual_inventory_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("manual-inventory", str(tmp_path / "nope.md"))
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_manual_verify_ok_exit_0(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "SKILL.md", _FIXTURE)
        inv = _run_cli("manual-inventory", str(src)).stdout
        inv_path = _write(tmp_path / "inv.json", inv)
        result = _run_cli("manual-verify", str(src), "--inventory", str(inv_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["ok"] is True

    def test_manual_verify_failure_still_exit_0_ok_false(self, tmp_path: Path) -> None:
        # An integrity failure is a *result* (ok=false), not an operation error.
        src = _write(tmp_path / "SKILL.md", _FIXTURE)
        inv = _run_cli("manual-inventory", str(src)).stdout
        inv_path = _write(tmp_path / "inv.json", inv)
        truncated = _FIXTURE.replace("Line two of developer notes.\n", "")
        target = _write(tmp_path / "post.md", truncated)
        result = _run_cli("manual-verify", str(target), "--inventory", str(inv_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["modified"] == ["extra-notes"]

    def test_manual_verify_missing_inventory_exits_1(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "SKILL.md", _FIXTURE)
        result = _run_cli(
            "manual-verify", str(src), "--inventory", str(tmp_path / "nope.json")
        )
        assert result.returncode == 1
        assert "inventory not found" in result.stderr

    def test_compare_constituents_emits_json(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        h = _write_constituent(skills, "skills/alpha", "alpha", '{"name":"alpha"}')
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "alpha", "skill_path": "skills/alpha", "metadata_hash": h}
            ]}),
        )
        result = _run_cli(
            "compare-constituent-hashes", str(prov), "--skills-root", str(skills)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["fresh"] == [{"skill_name": "alpha"}]
        assert payload["stats"]["fresh"] == 1

    def test_compare_constituents_drift_still_exit_0(self, tmp_path: Path) -> None:
        # constituent drift is a *result* (in the drifted bucket), not an error
        skills = tmp_path / "root"
        _write_constituent(skills, "skills/beta", "beta", '{"v":2}')
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "beta", "skill_path": "skills/beta", "metadata_hash": "sha256:stale"}
            ]}),
        )
        result = _run_cli(
            "compare-constituent-hashes", str(prov), "--skills-root", str(skills)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stats"]["drifted"] == 1

    def test_compare_constituents_default_skills_root_is_cwd(self, tmp_path: Path) -> None:
        # omitting --skills-root resolves relative skill_path against CWD
        skills = tmp_path / "root"
        h = _write_constituent(skills, "skills/alpha", "alpha", '{"name":"alpha"}')
        prov = _write(
            tmp_path / "prov.json",
            json.dumps({"constituents": [
                {"skill_name": "alpha", "skill_path": "skills/alpha", "metadata_hash": h}
            ]}),
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "compare-constituent-hashes", str(prov)],
            capture_output=True, text=True, check=False, cwd=str(skills),
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["fresh"] == [{"skill_name": "alpha"}]

    def test_compare_constituents_missing_provenance_exits_1(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        skills.mkdir()
        result = _run_cli(
            "compare-constituent-hashes", str(tmp_path / "nope.json"),
            "--skills-root", str(skills),
        )
        assert result.returncode == 1
        assert "provenance map" in result.stderr

    def test_compare_constituents_bad_skills_root_exits_1(self, tmp_path: Path) -> None:
        prov = _write(tmp_path / "prov.json", json.dumps({"constituents": []}))
        result = _run_cli(
            "compare-constituent-hashes", str(prov),
            "--skills-root", str(tmp_path / "missing-dir"),
        )
        assert result.returncode == 1
        assert "skills root" in result.stderr

    def test_compare_constituents_malformed_provenance_exits_1(self, tmp_path: Path) -> None:
        skills = tmp_path / "root"
        skills.mkdir()
        prov = _write(tmp_path / "prov.json", "{not json")
        result = _run_cli(
            "compare-constituent-hashes", str(prov), "--skills-root", str(skills)
        )
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr
