#!/usr/bin/env python3
"""Tests for skf-resolve-authoritative-files.py.

Covers all five deterministic phases of extract.md §2a:
  - Heuristic scan: case-insensitive basename match, depth-agnostic, prunes
    EXCLUDED_DIR_NAMES, recognizes all 9 heuristics
  - Scope diff: in-scope when include matches AND exclude doesn't; reports
    matching-exclude or no-include-matched
  - Amendment reconciliation: promoted / skipped / deferred-headless (and a
    legacy headless skip read as one) / most-recent-wins
  - Preview load: first N lines, UTF-8 best effort
  - Hash + size + line_count: SHA-256 prefix, size_bytes, newline count
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "src" / "shared" / "scripts" / "skf-resolve-authoritative-files.py"
)

spec = importlib.util.spec_from_file_location(
    "skf_resolve_authoritative_files", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def _expected_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _write(path: Path, content: str = "") -> Path:
    # binary write so Windows CRLF translation doesn't perturb size/hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _make_brief(
    tmp_path: Path,
    *,
    includes: list[str] = ("**",),
    excludes: list[str] = (),
    amendments: list[dict] = (),
) -> Path:
    brief = {
        "name": "x",
        "version": "1.0.0",
        "scope": {
            "include": list(includes),
            "exclude": list(excludes),
            "notes": "",
            "amendments": list(amendments),
        },
    }
    p = tmp_path / "brief.yaml"
    p.write_text(yaml.safe_dump(brief), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# Heuristic scan (iter_auth_doc_files)
# --------------------------------------------------------------------------


class TestHeuristicScan:
    def test_finds_llms_txt_at_root(self, tmp_path: Path) -> None:
        _write(tmp_path / "llms.txt", "content")
        found = list(mod.iter_auth_doc_files(tmp_path))
        assert len(found) == 1
        assert found[0][1] == "llms.txt"

    def test_finds_at_any_depth(self, tmp_path: Path) -> None:
        _write(tmp_path / "deeply" / "nested" / "AGENTS.md", "x")
        found = list(mod.iter_auth_doc_files(tmp_path))
        assert len(found) == 1

    def test_case_insensitive_basename(self, tmp_path: Path) -> None:
        _write(tmp_path / "LLMs.TXT", "x")
        _write(tmp_path / "AgEnTs.Md", "x")
        found = list(mod.iter_auth_doc_files(tmp_path))
        assert {f[1] for f in found} == {"llms.txt", "agents.md"}

    def test_recognizes_all_heuristics(self, tmp_path: Path) -> None:
        names = [
            "llms.txt", "llms-full.txt",
            "AGENTS.md", "CLAUDE.md", "GEMINI.md", "COPILOT.md",
            ".cursorrules", ".windsurfrules", ".clinerules",
        ]
        for name in names:
            _write(tmp_path / name, "x")
        found = list(mod.iter_auth_doc_files(tmp_path))
        assert len(found) == len(names)

    def test_skips_unrelated_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "x")
        _write(tmp_path / "src" / "main.py", "x")
        found = list(mod.iter_auth_doc_files(tmp_path))
        assert found == []

    def test_prunes_excluded_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / "node_modules" / "lib" / "llms.txt", "x")
        _write(tmp_path / "dist" / "AGENTS.md", "x")
        _write(tmp_path / "src" / "llms.txt", "x")
        found = list(mod.iter_auth_doc_files(tmp_path))
        # only the src/ one is kept; as_posix() so the assertion holds
        # on Windows where str(Path) uses backslash separators
        names = {p.relative_to(tmp_path).as_posix() for p, _ in found}
        assert names == {"src/llms.txt"}


# --------------------------------------------------------------------------
# scope_match
# --------------------------------------------------------------------------


class TestScopeMatch:
    def test_in_scope_when_include_matches_no_exclude(self) -> None:
        in_scope, excluded_by = mod.scope_match(
            "src/foo.py", ["src/**"], []
        )
        assert in_scope is True
        assert excluded_by is None

    def test_out_when_exclude_fires(self) -> None:
        in_scope, excluded_by = mod.scope_match(
            "src/test_foo.py", ["src/**"], ["**/test_*"]
        )
        assert in_scope is False
        assert excluded_by == "**/test_*"

    def test_out_when_no_include_matches(self) -> None:
        in_scope, excluded_by = mod.scope_match(
            "docs/llms.txt", ["src/**"], []
        )
        assert in_scope is False
        assert excluded_by == "not matched by any scope.include"

    def test_exclude_wins_over_include(self) -> None:
        # both rules match — exclude should take precedence
        in_scope, excluded_by = mod.scope_match(
            "src/llms.txt", ["**"], ["**/llms.txt"]
        )
        assert in_scope is False
        assert excluded_by == "**/llms.txt"


class TestGlobMatch:
    """Verify the `**` recursive-glob handling — these patterns appear
    routinely in brief.scope.include/exclude, and fnmatch can't handle
    them, so we use a custom translator."""

    def test_double_star_prefix_matches_any_depth(self) -> None:
        assert mod.glob_match("llms.txt", "**/llms.txt") is True
        assert mod.glob_match("a/llms.txt", "**/llms.txt") is True
        assert mod.glob_match("a/b/c/llms.txt", "**/llms.txt") is True

    def test_double_star_prefix_does_not_match_wrong_basename(self) -> None:
        assert mod.glob_match("a/AGENTS.md", "**/llms.txt") is False

    def test_double_star_suffix_matches_anything_below(self) -> None:
        assert mod.glob_match("src/foo.py", "src/**") is True
        assert mod.glob_match("src/a/b/c.py", "src/**") is True

    def test_double_star_middle_matches_zero_or_more_segments(self) -> None:
        assert mod.glob_match("a/b", "a/**/b") is True  # zero segments between
        assert mod.glob_match("a/x/b", "a/**/b") is True
        assert mod.glob_match("a/x/y/b", "a/**/b") is True

    def test_single_star_does_not_cross_separator(self) -> None:
        assert mod.glob_match("a/b", "a*") is False
        assert mod.glob_match("foo.py", "*.py") is True

    def test_question_mark_matches_single_char(self) -> None:
        assert mod.glob_match("file1.txt", "file?.txt") is True
        assert mod.glob_match("file12.txt", "file?.txt") is False

    def test_literal_dot_escaped(self) -> None:
        # `.` in pattern must match literal `.` only, not any char
        assert mod.glob_match("a.b", "a.b") is True
        assert mod.glob_match("aXb", "a.b") is False


# --------------------------------------------------------------------------
# resolve end-to-end
# --------------------------------------------------------------------------


class TestResolve:
    def test_no_candidates_when_no_auth_docs(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "main.py", "x")
        brief = _make_brief(tmp_path)
        result = mod.resolve(source, brief)
        assert result["status"] == "no-candidates"
        assert result["summary"]["candidates_total"] == 0

    def test_already_in_scope_populated(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "llms.txt", "first line\nsecond line\n")
        brief = _make_brief(tmp_path, includes=["**"], excludes=[])
        result = mod.resolve(source, brief)
        assert result["summary"]["already_in_scope_count"] == 1
        rec = result["already_in_scope"][0]
        assert rec["path"] == "llms.txt"
        assert rec["heuristic"] == "llms.txt"
        assert rec["size_bytes"] == len(b"first line\nsecond line\n")
        assert rec["line_count"] == 2
        assert rec["content_hash"] == _expected_hash(b"first line\nsecond line\n")

    def test_unresolved_when_excluded_no_amendment(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "AGENTS.md", "AI doc content\nmore content\n")
        brief = _make_brief(tmp_path, includes=["src/**.py"], excludes=[])
        result = mod.resolve(source, brief)
        assert result["summary"]["unresolved_count"] == 1
        rec = result["unresolved"][0]
        assert rec["path"] == "AGENTS.md"
        assert rec["heuristic"] == "agents.md"
        assert rec["excluded_by_pattern"] == "not matched by any scope.include"
        # preview is populated with the first lines
        assert "AI doc content" in rec["preview"]

    def test_unresolved_reports_matching_exclude(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(
            tmp_path, includes=["**"], excludes=["**/llms.txt"]
        )
        result = mod.resolve(source, brief)
        rec = result["unresolved"][0]
        assert rec["excluded_by_pattern"] == "**/llms.txt"

    def test_pre_decided_promoted_populates_hash(self, tmp_path: Path) -> None:
        # amendment says promoted but scope.include doesn't currently match.
        # Should still populate promoted_docs[] for deterministic replay.
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(
            tmp_path,
            includes=["**.py"],
            amendments=[{"action": "promoted", "path": "llms.txt"}],
        )
        result = mod.resolve(source, brief)
        assert result["summary"]["pre_decided_count"] == 1
        rec = result["pre_decided"][0]
        assert rec["prior_action"] == "promoted"
        assert rec["should_add_to_promoted_docs"] is True
        assert rec["content_hash"] is not None

    def test_pre_decided_skipped_no_hash(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(
            tmp_path,
            includes=["**.py"],
            amendments=[{"action": "skipped", "path": "llms.txt"}],
        )
        result = mod.resolve(source, brief)
        rec = result["pre_decided"][0]
        assert rec["prior_action"] == "skipped"
        assert rec["should_add_to_promoted_docs"] is False
        assert rec["content_hash"] is None
        assert rec["size_bytes"] is None

    def test_in_scope_with_skipped_amendment_is_pre_decided(
        self, tmp_path: Path
    ) -> None:
        # If amendments say skipped, honor that even when scope.include now
        # matches (most recent decision wins).
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(
            tmp_path,
            includes=["**"],
            amendments=[{"action": "skipped", "path": "llms.txt"}],
        )
        result = mod.resolve(source, brief)
        assert result["summary"]["already_in_scope_count"] == 0
        assert result["summary"]["pre_decided_count"] == 1

    def test_most_recent_amendment_wins(self, tmp_path: Path) -> None:
        # User skipped, then promoted later. Promoted should win.
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(
            tmp_path,
            includes=["**.py"],
            amendments=[
                {"action": "skipped", "path": "llms.txt"},
                {"action": "promoted", "path": "llms.txt"},
            ],
        )
        result = mod.resolve(source, brief)
        rec = result["pre_decided"][0]
        assert rec["prior_action"] == "promoted"

    def test_preview_respects_max_lines(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        content = "".join(f"line {i}\n" for i in range(50))
        _write(source / "llms.txt", content)
        brief = _make_brief(tmp_path, includes=["**.py"])
        result = mod.resolve(source, brief, preview_lines=5)
        preview = result["unresolved"][0]["preview"]
        assert preview.count("\n") == 4  # 5 lines, 4 newlines between
        assert "line 4" in preview
        assert "line 5" not in preview

    def test_paths_forward_slash_form(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "sub" / "dir" / "AGENTS.md", "x\n")
        brief = _make_brief(tmp_path, includes=["**"])
        result = mod.resolve(source, brief)
        # path is forward-slash form regardless of platform
        assert result["already_in_scope"][0]["path"] == "sub/dir/AGENTS.md"

    def test_stable_ordering(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "zzz" / "llms.txt", "x")
        _write(source / "aaa" / "llms.txt", "x")
        _write(source / "mmm" / "llms.txt", "x")
        brief = _make_brief(tmp_path, includes=["**"])
        result = mod.resolve(source, brief)
        paths = [r["path"] for r in result["already_in_scope"]]
        assert paths == sorted(paths)


LEGACY_HEADLESS_SKIP = {"action": "skipped", "path": "llms.txt",
                        "reason": "headless: no user to prompt", "workflow": "skf-create-skill"}
DEFERRED = {"action": "deferred-headless", "path": "llms.txt", "workflow": "skf-create-skill"}
USER_SKIP = {"action": "skipped", "path": "llms.txt", "reason": "user declined promotion at create-skill §2a"}
PROMOTED = {"action": "promoted", "path": "llms.txt"}


class TestDeferredHeadless:
    """A headless run leaves each authoritative file for the next interactive
    run: nobody declined it, so it must never read as a person's skip."""

    def _resolve(self, tmp_path: Path, amendments: list[dict], includes=("**.py",)) -> dict:
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(tmp_path, includes=list(includes), amendments=amendments)
        return mod.resolve(source, brief)

    def test_deferred_amendment_stays_unresolved(self, tmp_path: Path) -> None:
        result = self._resolve(tmp_path, [DEFERRED])
        assert result["summary"]["pre_decided_count"] == 0
        assert result["summary"]["unresolved_count"] == 1
        rec = result["unresolved"][0]
        assert rec["prior_action"] == "deferred-headless"
        assert rec["content_hash"] == _expected_hash(b"content\n")
        assert "content" in rec["preview"]

    def test_legacy_headless_skip_is_read_as_deferred(self, tmp_path: Path) -> None:
        result = self._resolve(tmp_path, [LEGACY_HEADLESS_SKIP])
        assert result["pre_decided"] == []
        assert result["unresolved"][0]["prior_action"] == "deferred-headless"

    def test_legacy_reason_matches_with_surrounding_space(self, tmp_path: Path) -> None:
        amend = {**LEGACY_HEADLESS_SKIP, "reason": "  headless: no user to prompt \n"}
        assert self._resolve(tmp_path, [amend])["summary"]["unresolved_count"] == 1

    def test_a_person_s_skip_is_still_pre_decided(self, tmp_path: Path) -> None:
        result = self._resolve(tmp_path, [USER_SKIP])
        assert result["pre_decided"][0]["prior_action"] == "skipped"
        assert result["unresolved"] == []

    def test_undecided_file_has_no_prior_action(self, tmp_path: Path) -> None:
        assert self._resolve(tmp_path, [])["unresolved"][0]["prior_action"] is None

    @pytest.mark.parametrize("amendments,bucket,prior", [
        ([DEFERRED, PROMOTED], "pre_decided", "promoted"),
        ([DEFERRED, USER_SKIP], "pre_decided", "skipped"),
        ([LEGACY_HEADLESS_SKIP, USER_SKIP], "pre_decided", "skipped"),
        ([USER_SKIP, DEFERRED], "unresolved", "deferred-headless"),
        ([PROMOTED, LEGACY_HEADLESS_SKIP], "unresolved", "deferred-headless"),
    ])
    def test_most_recent_decision_wins(self, tmp_path: Path, amendments, bucket, prior) -> None:
        result = self._resolve(tmp_path, amendments)
        assert [r["prior_action"] for r in result[bucket]] == [prior]

    @pytest.mark.parametrize("amendment", [DEFERRED, LEGACY_HEADLESS_SKIP])
    def test_deferred_file_now_in_scope_is_already_in_scope(self, tmp_path: Path, amendment) -> None:
        result = self._resolve(tmp_path, [amendment], includes=("**",))
        assert result["summary"]["already_in_scope_count"] == 1
        assert result["unresolved"] == [] and result["pre_decided"] == []

    def test_cli_reports_the_deferral(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(tmp_path, includes=["**.py"], amendments=[LEGACY_HEADLESS_SKIP])
        result = _run_cli("resolve", "--source-root", str(source), "--brief", str(brief))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["unresolved"][0]["prior_action"] == "deferred-headless"

    def test_docstring_states_the_deferral_contract(self) -> None:
        doc = mod.__doc__
        assert '"prior_action": null | "deferred-headless"' in doc
        assert "headless: no user to prompt" in doc


# --------------------------------------------------------------------------
# load_brief
# --------------------------------------------------------------------------


class TestLoadBrief:
    def test_missing_brief_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read"):
            mod.load_brief(tmp_path / "missing.yaml")

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "brief.yaml"
        p.write_text("name: : :\nbad", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid YAML"):
            mod.load_brief(p)

    def test_non_mapping_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "brief.yaml"
        p.write_text("- just\n- a list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            mod.load_brief(p)


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
    def test_resolve_emits_json(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "llms.txt", "content\n")
        brief = _make_brief(tmp_path, includes=["**"])
        result = _run_cli(
            "resolve", "--source-root", str(source), "--brief", str(brief)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "candidates-found"
        assert payload["summary"]["candidates_total"] == 1

    def test_no_candidates_via_cli(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        brief = _make_brief(tmp_path)
        result = _run_cli(
            "resolve", "--source-root", str(source), "--brief", str(brief)
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "no-candidates"

    def test_missing_source_root_exits_1(self, tmp_path: Path) -> None:
        brief = _make_brief(tmp_path)
        result = _run_cli(
            "resolve",
            "--source-root", str(tmp_path / "missing"),
            "--brief", str(brief),
        )
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_missing_brief_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        result = _run_cli(
            "resolve",
            "--source-root", str(source),
            "--brief", str(tmp_path / "missing.yaml"),
        )
        assert result.returncode == 1
        assert "brief not found" in result.stderr

    def test_bad_preview_lines_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        brief = _make_brief(tmp_path)
        result = _run_cli(
            "resolve",
            "--source-root", str(source),
            "--brief", str(brief),
            "--preview-lines", "0",
        )
        assert result.returncode == 1
        assert "preview-lines" in result.stderr

    def test_no_subcommand_exits_2(self) -> None:
        result = _run_cli()
        assert result.returncode == 2


# --------------------------------------------------------------------------
# --provenance-map: candidates the map already tracks (update-skill's mirror)
# --------------------------------------------------------------------------


def _make_provenance(tmp_path: Path, *, entries=(), file_entries=()) -> Path:
    data = {
        "provenance_version": "2.0",
        "entries": [{"export_name": "x", "source_file": p} for p in entries],
        "file_entries": [{"file_name": Path(p).name, "file_type": "doc", "source_file": p}
                         for p in file_entries],
    }
    p = tmp_path / "provenance-map.json"
    p.write_bytes(json.dumps(data).encode("utf-8"))
    return p


class TestProvenanceMap:
    def _source(self, tmp_path: Path) -> Path:
        source = tmp_path / "src"
        _write(source / "llms.txt", "tracked doc\n")
        _write(source / "docs" / "AGENTS.md", "tracked as an entry\n")
        _write(source / "CLAUDE.md", "new since creation\n")
        return source

    def test_tracked_candidates_are_listed_apart(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        prov = _make_provenance(tmp_path, entries=["docs/AGENTS.md"], file_entries=["llms.txt"])
        result = mod.resolve(source, _make_brief(tmp_path, includes=["**.py"]), provenance_map=prov)
        assert result["already_tracked"] == [
            {"path": "docs/AGENTS.md", "heuristic": "agents.md"},
            {"path": "llms.txt", "heuristic": "llms.txt"},
        ]
        assert [r["path"] for r in result["unresolved"]] == ["CLAUDE.md"]
        assert result["summary"]["already_tracked_count"] == 2
        assert result["summary"]["candidates_total"] == 3

    def test_a_tracked_candidate_is_in_no_other_bucket(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        prov = _make_provenance(tmp_path, file_entries=["llms.txt", "docs/AGENTS.md", "CLAUDE.md"])
        brief = _make_brief(tmp_path, includes=["**"], amendments=[{"action": "skipped", "path": "llms.txt"}])
        result = mod.resolve(source, brief, provenance_map=prov)
        assert result["summary"]["already_tracked_count"] == 3
        assert result["already_in_scope"] == [] and result["pre_decided"] == [] and result["unresolved"] == []
        assert result["status"] == "candidates-found"

    def test_map_paths_are_normalized(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        prov = _make_provenance(tmp_path, entries=["./docs\\AGENTS.md"])
        result = mod.resolve(source, _make_brief(tmp_path, includes=["**.py"]), provenance_map=prov)
        assert [r["path"] for r in result["already_tracked"]] == ["docs/AGENTS.md"]

    def test_without_the_option_nothing_is_tracked(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        result = mod.resolve(source, _make_brief(tmp_path, includes=["**"]))
        assert result["already_tracked"] == [] and result["summary"]["already_tracked_count"] == 0
        assert result["summary"]["already_in_scope_count"] == 3

    @pytest.mark.parametrize("content,message", [
        (b"{not json", "not valid JSON"),
        (b"[1, 2]", "must be a JSON object"),
    ], ids=["invalid-json", "not-an-object"])
    def test_an_unreadable_map_raises(self, tmp_path: Path, content: bytes, message: str) -> None:
        prov = tmp_path / "provenance-map.json"
        prov.write_bytes(content)
        with pytest.raises(ValueError, match=message):
            mod.load_tracked_files(prov)

    def test_the_cli_takes_the_map(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        prov = _make_provenance(tmp_path, file_entries=["llms.txt"])
        brief = _make_brief(tmp_path, includes=["**.py"])
        result = _run_cli("resolve", "--source-root", str(source), "--brief", str(brief),
                          "--provenance-map", str(prov))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [r["path"] for r in payload["already_tracked"]] == ["llms.txt"]

    def test_the_cli_refuses_a_missing_map(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        brief = _make_brief(tmp_path)
        result = _run_cli("resolve", "--source-root", str(source), "--brief", str(brief),
                          "--provenance-map", str(tmp_path / "absent.json"))
        assert result.returncode == 1
        assert "provenance map not found" in result.stderr

    def test_the_cli_refuses_an_invalid_map(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        prov = tmp_path / "provenance-map.json"
        prov.write_bytes(b"{not json")
        result = _run_cli("resolve", "--source-root", str(source), "--brief", str(_make_brief(tmp_path)),
                          "--provenance-map", str(prov))
        assert result.returncode == 1
        assert "not valid JSON" in result.stderr


@pytest.mark.parametrize("raw,expected", [
    ("src/a.py", "src/a.py"),
    ("./src/a.py", "src/a.py"),
    ("src\\pkg\\a.py", "src/pkg/a.py"),
    (" ././x ", "x"),
], ids=["plain", "dot-slash", "backslashes", "repeated-dot-slash"])
def test_normalize_rel_path(raw: str, expected: str) -> None:
    assert mod.normalize_rel_path(raw) == expected
