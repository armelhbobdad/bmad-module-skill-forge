#!/usr/bin/env python3
"""Tests for skf-new-file-diff.py (skf-update-skill detect-changes Category D).

Covers the NEW_FILE set-difference: inventory source_files minus provenance
file_entries, with [MANUAL] paths set aside and kind carried through; a map
with no (or a null) file_entries tracks nothing (#684); with --brief, only
the paths the brief's scope takes (Category A's in-scope test) and its
intents want, and code the map's entries[] cite set aside (#683).
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-update-skill" / "scripts" / "skf-new-file-diff.py"
DETECT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-detect-scripts-assets.py"
CLASSIFY_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-classify-changed-files.py"

spec = importlib.util.spec_from_file_location("skf_new_file_diff", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def detect(scripts=None, assets=None):
    return {
        "scripts_inventory": [{"source_file": s} for s in (scripts or [])],
        "assets_inventory": [{"source_file": a} for a in (assets or [])],
    }


# --------------------------------------------------------------------------
# diff()
# --------------------------------------------------------------------------


class TestDiff:
    def test_new_file_detected(self) -> None:
        result = mod.diff(detect(scripts=["scripts/gen.py"]), set())
        assert result["new_files"] == [{"source_file": "scripts/gen.py", "kind": "script"}]
        assert result["stats"]["new"] == 1

    def test_asset_kind_carried(self) -> None:
        result = mod.diff(detect(assets=["assets/logo.svg"]), set())
        assert result["new_files"] == [{"source_file": "assets/logo.svg", "kind": "asset"}]

    def test_already_tracked_excluded(self) -> None:
        result = mod.diff(detect(scripts=["scripts/gen.py"]), {"scripts/gen.py"})
        assert result["new_files"] == []
        assert result["already_tracked"] == ["scripts/gen.py"]
        assert result["stats"]["new"] == 0

    def test_manual_paths_skipped(self) -> None:
        result = mod.diff(
            detect(scripts=["scripts/[MANUAL]/keep.py"], assets=["assets/[MANUAL]/x.bin"]),
            set(),
        )
        assert result["new_files"] == []
        assert result["skipped_manual"] == ["assets/[MANUAL]/x.bin", "scripts/[MANUAL]/keep.py"]
        assert result["stats"]["skipped_manual"] == 2

    def test_manual_only_under_scripts_or_assets(self) -> None:
        # A [MANUAL] segment not under scripts/ or assets/ is not skipped.
        result = mod.diff(detect(scripts=["src/[MANUAL]/thing.py"]), set())
        assert result["new_files"] == [
            {"source_file": "src/[MANUAL]/thing.py", "kind": "script"}
        ]

    def test_dedupe_scripts_wins_over_assets(self) -> None:
        d = {
            "scripts_inventory": [{"source_file": "shared/x"}],
            "assets_inventory": [{"source_file": "shared/x"}],
        }
        result = mod.diff(d, set())
        assert result["new_files"] == [{"source_file": "shared/x", "kind": "script"}]
        assert result["stats"]["inventory_total"] == 1

    def test_sorted_output(self) -> None:
        result = mod.diff(detect(scripts=["scripts/z.py", "scripts/a.py"]), set())
        assert [r["source_file"] for r in result["new_files"]] == [
            "scripts/a.py",
            "scripts/z.py",
        ]

    def test_windows_paths_normalized(self) -> None:
        d = {"scripts_inventory": [{"source_file": "scripts\\gen.py"}], "assets_inventory": []}
        result = mod.diff(d, {"scripts/gen.py"})
        assert result["already_tracked"] == ["scripts/gen.py"]
        assert result["new_files"] == []

    def test_empty_inventory(self) -> None:
        result = mod.diff(detect(), set())
        assert result["new_files"] == []
        assert result["stats"] == {
            "inventory_total": 0,
            "new": 0,
            "skipped_manual": 0,
            "already_tracked": 0,
        }

    def test_mixed(self) -> None:
        d = detect(
            scripts=["scripts/new.py", "scripts/tracked.py", "scripts/[MANUAL]/m.py"],
            assets=["assets/new.png"],
        )
        result = mod.diff(d, {"scripts/tracked.py"})
        assert result["stats"] == {
            "inventory_total": 4,
            "new": 2,
            "skipped_manual": 1,
            "already_tracked": 1,
        }


# --------------------------------------------------------------------------
# load_tracked_source_files()
# --------------------------------------------------------------------------


class TestLoadTracked:
    def test_canonical_object(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps({"file_entries": [{"source_file": "scripts/a.py"}]}))
        assert mod.load_tracked_source_files(p) == {"scripts/a.py"}

    def test_bare_array(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps([{"source_file": "scripts/a.py"}, {"source_file": "b"}]))
        assert mod.load_tracked_source_files(p) == {"scripts/a.py", "b"}

    def test_entry_without_source_file_ignored(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps({"file_entries": [{"export_name": "x"}]}))
        assert mod.load_tracked_source_files(p) == set()


# --------------------------------------------------------------------------
# CLI / exit codes
# --------------------------------------------------------------------------


def run_cli(provenance: str, stdin: str) -> subprocess.CompletedProcess:
    return run_args([provenance], stdin)


def run_args(args: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_success(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        detect_json = json.dumps(detect(scripts=["scripts/new.py"]))
        proc = run_cli(str(prov), detect_json)
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["new_files"] == [{"source_file": "scripts/new.py", "kind": "script"}]

    def test_missing_provenance_exit_2(self, tmp_path: Path) -> None:
        proc = run_cli(str(tmp_path / "nope.json"), json.dumps(detect()))
        assert proc.returncode == 2

    def test_invalid_stdin_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        proc = run_cli(str(prov), "not json")
        assert proc.returncode == 2

    def test_empty_stdin_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        proc = run_cli(str(prov), "")
        assert proc.returncode == 2

    @pytest.mark.parametrize("prov_json", [{"something_else": []}, {"entries": [], "file_entries": None}],
                             ids=["no-file-entries", "null-file-entries"])
    def test_provenance_without_file_entries_tracks_nothing(self, tmp_path: Path, prov_json: dict) -> None:
        # #684: oms-cognee's 1.0.0 map has no file_entries; Category D no longer halts on it
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps(prov_json))
        proc = run_cli(str(prov), json.dumps(detect(scripts=["scripts/new.py"])))
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["new_files"] == [{"source_file": "scripts/new.py", "kind": "script"}]
        assert out["already_tracked"] == []

    @pytest.mark.parametrize("key", ["file_entries", "entries"])
    def test_a_field_that_is_not_an_array_exit_2(self, tmp_path: Path, key: str) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({key: {"scripts/a.py": "x"}}))
        proc = run_cli(str(prov), json.dumps(detect()))
        assert proc.returncode == 2
        assert "is not an array" in json.loads(proc.stderr)["error"]


class TestArgparse:
    """argparse documents the CLI (#601); arguments, output and exit 2 stay as they were."""

    def test_help_documents_the_cli(self) -> None:
        proc = run_args(["--help"])
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.startswith("usage: skf-new-file-diff.py [-h] [--brief brief-path] provenance-map-path")
        for token in ("detect JSON on stdin", '"new_files"', '"skipped_manual"', '"already_tracked"',
                      '"tracked_code"', '"out_of_scope"', '"intent_none"', "Exit codes:", "2  bad input"):
            assert token in proc.stdout, token

    def test_help_is_ascii(self) -> None:
        # No _force_utf8 needed: --help prints only ASCII, so a cp1252 console prints it as is.
        proc = run_args(["--help"])
        assert proc.returncode == 0 and proc.stdout and proc.stdout.isascii(), proc.stderr

    @pytest.mark.parametrize("args", [[], ["a.json", "b.json"], ["--provenance", "a.json"], ["a.json", "--bri", "b"]],
                             ids=["no-argument", "two-arguments", "unknown-flag", "abbreviated-flag"])
    def test_usage_error_is_a_json_error_with_exit_2(self, args: list[str]) -> None:
        proc = run_args(args, json.dumps(detect()))
        assert proc.returncode == 2
        assert proc.stdout == ""
        error = json.loads(proc.stderr)["error"]
        assert error.startswith("usage: skf-new-file-diff.py <provenance-map-path> [--brief <brief-path>]  "
                                "(detect JSON on stdin): ")

    def test_one_positional_argument(self) -> None:
        parser = mod._build_parser()
        positionals = [a for a in parser._actions if not a.option_strings]
        assert [a.dest for a in positionals] == ["provenance_map"]
        assert {s for a in parser._actions for s in a.option_strings} == {"-h", "--help", "--brief"}

    def test_main_reads_its_own_argv(self, tmp_path: Path, monkeypatch, capsys) -> None:
        prov = tmp_path / "prov.json"
        prov.write_bytes(json.dumps({"file_entries": [{"source_file": "scripts/old.py"}]}).encode("utf-8"))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(detect(scripts=["scripts/old.py", "scripts/new.py"]))))
        assert mod.main(["skf-new-file-diff.py", str(prov)]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["new_files"] == [{"source_file": "scripts/new.py", "kind": "script"}]
        assert out["already_tracked"] == ["scripts/old.py"]


# --------------------------------------------------------------------------
# The map's code entries, the brief's scope and intents (#683, #684)
# --------------------------------------------------------------------------


def _brief(tmp_path: Path, include=None, exclude=None, language="Python", **intents) -> Path:
    lines = ["name: demo", "version: 1.0.0", "source_repo: https://example.com/demo", f"language: {language}",
             "description: demo", "forge_tier: Forge", "created: '2026-10-09'", "created_by: test", "scope:",
             "  type: public-api"]
    for key, patterns in (("include", include), ("exclude", exclude)):
        if patterns is None:
            continue
        lines.append(f"  {key}:" + ("" if patterns else " []"))
        lines += [f"  - {json.dumps(pattern)}" for pattern in patterns]  # a YAML double-quoted string
    lines += [f"{field}: {value}" for field, value in intents.items()]
    path = tmp_path / "skill-brief.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _map(tmp_path: Path, *, entries=(), file_entries=None) -> Path:
    data: dict = {"entries": [{"export_name": f"e{i}", "source_file": f} for i, f in enumerate(entries)]}
    if file_entries is not None:
        data["file_entries"] = [{"source_file": f} for f in file_entries]
    path = tmp_path / "provenance-map.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _scoped(tmp_path: Path, detected: dict, *, entries=(), file_entries=None, **brief) -> dict:
    prov = _map(tmp_path, entries=entries, file_entries=file_entries)
    tracked, cited = mod.load_map_paths(prov)
    return mod.diff(detected, tracked, cited, mod.load_scope(_brief(tmp_path, **brief), cited))


class TestLoadMapPaths:
    def test_file_entries_and_entries(self, tmp_path: Path) -> None:
        prov = _map(tmp_path, entries=["pkg\\api.py", "pkg/tools/t.py"], file_entries=["scripts/a.sh"])
        assert mod.load_map_paths(prov) == ({"scripts/a.sh"}, {"pkg/api.py", "pkg/tools/t.py"})

    def test_a_legacy_map_tracks_no_file(self, tmp_path: Path) -> None:
        prov = _map(tmp_path, entries=["pkg/api.py"])
        assert mod.load_map_paths(prov) == (set(), {"pkg/api.py"})
        assert mod.load_tracked_source_files(prov) == set()

    def test_paths_are_normalized_as_normalize_rel_path_does(self, tmp_path: Path) -> None:
        prov = _map(tmp_path, entries=["./pkg/tools/t.py", " pkg/a.py "], file_entries=[".\\scripts\\a.sh "])
        tracked, cited = mod.load_map_paths(prov)
        assert (tracked, cited) == ({"scripts/a.sh"}, {"pkg/tools/t.py", "pkg/a.py"})
        result = mod.diff(detect(scripts=["pkg/tools/t.py", "scripts/a.sh", "./scripts/b.sh"]), tracked, cited)
        assert (result["tracked_code"], result["already_tracked"]) == (["pkg/tools/t.py"], ["scripts/a.sh"])
        assert result["new_files"] == [{"source_file": "scripts/b.sh", "kind": "script"}]

    def test_a_bare_array_is_the_file_entries(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps([{"source_file": "scripts/a.py"}]))
        assert mod.load_map_paths(prov) == ({"scripts/a.py"}, set())


class TestTrackedCode:
    def test_code_the_map_cites_is_set_aside(self) -> None:
        # a module of a package's tools/ folder the map already cites is code Category A and B compare
        result = mod.diff(detect(scripts=["pkg/tools/t.py", "pkg/scripts/run.sh"]), set(), {"pkg/tools/t.py"})
        assert result["tracked_code"] == ["pkg/tools/t.py"]
        assert result["new_files"] == [{"source_file": "pkg/scripts/run.sh", "kind": "script"}]
        # set-aside paths are never counted in stats
        assert result["stats"] == {"inventory_total": 2, "new": 1, "skipped_manual": 0, "already_tracked": 0}

    def test_file_entries_win_over_entries(self) -> None:
        result = mod.diff(detect(scripts=["scripts/a.py"]), {"scripts/a.py"}, {"scripts/a.py"})
        assert result["already_tracked"] == ["scripts/a.py"] and result["tracked_code"] == []

    def test_lists_without_a_brief(self) -> None:
        result = mod.diff(detect(scripts=["scripts/a.py"]), set())
        assert (result["tracked_code"], result["out_of_scope"], result["intent_none"]) == ([], [], [])


class TestScope:
    def test_only_in_scope_paths_survive(self, tmp_path: Path) -> None:
        detected = detect(scripts=["pkg/scripts/run.sh", "tools/release.sh", "pkg/cli/main.py"],
                          assets=["pkg/schemas/a.schema.json", "examples/demo.json"])
        result = _scoped(tmp_path, detected, include=["pkg/**"], exclude=["pkg/cli/**"])
        assert result["new_files"] == [{"source_file": "pkg/schemas/a.schema.json", "kind": "asset"},
                                       {"source_file": "pkg/scripts/run.sh", "kind": "script"}]
        assert result["out_of_scope"] == ["examples/demo.json", "pkg/cli/main.py", "tools/release.sh"]
        assert result["stats"]["inventory_total"] == 5 and result["stats"]["new"] == 2

    def test_patterns_are_normalized_as_category_a_does(self, tmp_path: Path) -> None:
        result = _scoped(tmp_path, detect(scripts=["pkg/scripts/run.sh", "pkg/scripts/old.sh"]),
                         include=["./pkg/**"], exclude=[".\\pkg\\scripts\\old.sh"])
        assert result["new_files"] == [{"source_file": "pkg/scripts/run.sh", "kind": "script"}]
        assert result["out_of_scope"] == ["pkg/scripts/old.sh"]

    def test_brief_globs_not_fnmatch(self, tmp_path: Path) -> None:
        # `*` never crosses a `/` in a brief glob (fnmatch's would): scripts/sub/x.sh is outside scripts/*
        result = _scoped(tmp_path, detect(scripts=["scripts/x.sh", "scripts/sub/x.sh"]), include=["scripts/*"])
        assert [r["source_file"] for r in result["new_files"]] == ["scripts/x.sh"]
        assert result["out_of_scope"] == ["scripts/sub/x.sh"]

    def test_an_empty_include_follows_category_a(self, tmp_path: Path) -> None:
        # no include: in scope when no exclude matches and the extension is a cited file's or the language's
        detected = detect(scripts=["scripts/gen.py", "scripts/run.sh", "bin/tool.rb"], assets=["a/b.schema.json"])
        result = _scoped(tmp_path, detected, include=[], exclude=["bin/**"], language="Python")
        assert [r["source_file"] for r in result["new_files"]] == ["scripts/gen.py"]
        assert result["out_of_scope"] == ["a/b.schema.json", "bin/tool.rb", "scripts/run.sh"]
        # a cited file's extension counts too
        result = _scoped(tmp_path, detected, include=[], language="Python", entries=["lib/x.sh"])
        assert [r["source_file"] for r in result["new_files"]] == ["scripts/gen.py", "scripts/run.sh"]
        assert result["out_of_scope"] == ["a/b.schema.json", "bin/tool.rb"]

    def test_the_scope_test_is_category_as(self, tmp_path: Path) -> None:
        """The same verdict as skf-classify-changed-files.py's in-scope test, for the same patterns."""
        spec_ = importlib.util.spec_from_file_location("skf_classify_for_new_file_diff", CLASSIFY_PATH)
        classify = importlib.util.module_from_spec(spec_)
        assert spec_.loader is not None
        spec_.loader.exec_module(classify)
        paths = ["pkg/a.py", "pkg/sub/b.sh", "pkg/cli/c.py", "docs/d.md", "pkg/tests/t.py", "x.py", "pkg/e.json"]
        for include, exclude in ((["pkg/**"], ["pkg/cli/**", "**/tests/**"]), (["pkg/*", "docs/**"], []),
                                 ([], ["pkg/cli/**"])):
            scope = mod.load_scope(_brief(tmp_path, include=include, exclude=exclude), {"lib/m.py"})
            extensions = {".py", ".pyi"}  # the cited file's and Python's
            for path in paths:
                assert scope.takes(path) == classify._in_scope(path, include, exclude, extensions), (include, path)

    @pytest.mark.parametrize("intents, kept", [
        ({"scripts_intent": "none"}, ["asset"]),
        ({"assets_intent": "none"}, ["script"]),
        ({"scripts_intent": "none", "assets_intent": "none"}, []),
        ({"scripts_intent": "'the release helpers'", "assets_intent": "detect"}, ["asset", "script"]),
        ({}, ["asset", "script"]),
    ], ids=["scripts-none", "assets-none", "both-none", "free-text", "absent"])
    def test_intents(self, tmp_path: Path, intents: dict, kept: list) -> None:
        result = _scoped(tmp_path, detect(scripts=["pkg/scripts/run.sh"], assets=["pkg/schemas/a.json"]),
                         include=["pkg/**"], **intents)
        assert sorted(r["kind"] for r in result["new_files"]) == kept
        assert len(result["intent_none"]) == 2 - len(kept)
        assert result["stats"]["new"] == len(kept)

    def test_a_genuine_script_category_a_lists_stays_new(self, tmp_path: Path) -> None:
        # Category A lists every changed in-scope file, a script with a shebang included: it stays a new file
        result = _scoped(tmp_path, detect(scripts=["pkg/scripts/run.sh"]), include=["pkg/**"],
                         entries=["pkg/api.py"])
        assert result["new_files"] == [{"source_file": "pkg/scripts/run.sh", "kind": "script"}]


def _tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


class TestPipe:
    """Category D's documented pipe, end to end: the detector over the whole source into the diff with --brief."""

    def _pipe(self, source: Path, prov: Path, brief: Path | None) -> subprocess.CompletedProcess:
        found = subprocess.run([sys.executable, str(DETECT_PATH), "detect", str(source)], capture_output=True,
                               text=True, check=True)
        return run_args([str(prov)] + (["--brief", str(brief)] if brief else []), found.stdout)

    def test_a_scoped_update_reads_no_repository_script_as_new(self, tmp_path: Path) -> None:
        # the oms-cognee shape: a brief scoped to the package's API, a package `tools/` folder of modules, a
        # repository full of scripts, assets and a cli package the brief excludes
        source = _tree(tmp_path / "src", {
            "cognee/__init__.py": "__version__ = '1'\n",
            "cognee/api/v1/__init__.py": "",
            "cognee/api/v1/tools/__init__.py": "from .tools import TOOLS\n",
            "cognee/api/v1/tools/tools.py": "TOOLS = []\n",
            "cognee/api/v1/scripts/run.sh": "#!/bin/bash\necho run\n",
            "cognee/cli/__init__.py": "",
            "cognee/cli/minimal_cli.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
            "tools/release.sh": "#!/bin/bash\n",
            "scripts/dev.py": "print('dev')\n",
            "examples/demo.json": "{}\n",
            "deployment/helm/templates/x.yaml": "a: 1\n",
        })
        prov = _map(tmp_path, entries=["cognee/__init__.py"])  # the 1.0.0 shape: no file_entries
        brief = _brief(tmp_path, include=["cognee/__init__.py", "cognee/api/v1/**"],
                       exclude=["cognee/cli/**", "examples/**"])
        proc = self._pipe(source, prov, brief)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["new_files"] == [{"source_file": "cognee/api/v1/scripts/run.sh", "kind": "script"}]
        assert out["out_of_scope"] == ["cognee/cli/minimal_cli.py", "deployment/helm/templates/x.yaml",
                                       "examples/demo.json", "scripts/dev.py", "tools/release.sh"]
        everything = {row for key in ("new_files",) for row in (r["source_file"] for r in out[key])}
        everything |= set(out["out_of_scope"]) | set(out["tracked_code"]) | set(out["intent_none"])
        assert not any(path.startswith("cognee/api/v1/tools/") for path in everything)  # modules, not scripts
        # without the brief the same walk reads the whole repository's scripts and assets as new
        out = json.loads(self._pipe(source, prov, None).stdout)
        assert len(out["new_files"]) == 6

    def test_a_missing_or_broken_brief_exit_2(self, tmp_path: Path) -> None:
        prov = _map(tmp_path)
        proc = run_args([str(prov), "--brief", str(tmp_path / "nope.yaml")], json.dumps(detect()))
        assert proc.returncode == 2 and "brief not found" in json.loads(proc.stderr)["error"]
        bad = tmp_path / "bad.yaml"
        bad.write_text("scope: [unclosed\n", encoding="utf-8")
        proc = run_args([str(prov), "--brief", str(bad)], json.dumps(detect()))
        assert proc.returncode == 2 and "not valid YAML" in json.loads(proc.stderr)["error"]

    @pytest.mark.parametrize("value", ["", "  "], ids=["empty", "blank"])
    def test_an_empty_brief_is_a_usage_error(self, tmp_path: Path, value: str) -> None:
        # an unbound {brief_path} must not run unscoped
        proc = run_args([str(_map(tmp_path)), "--brief", value], json.dumps(detect(scripts=["scripts/a.sh"])))
        assert proc.returncode == 2 and proc.stdout == ""
        error = json.loads(proc.stderr)["error"]
        assert error.startswith(mod.USAGE) and "--brief is empty" in error

    def test_a_detector_that_printed_nothing_exit_2(self, tmp_path: Path) -> None:
        # the pipe's failure clause: a detector that fails leaves stdin empty
        proc = run_args([str(_map(tmp_path)), "--brief", str(_brief(tmp_path, include=["**"]))], "")
        assert proc.returncode == 2 and json.loads(proc.stderr)["error"] == "no detect JSON on stdin"



class TestScriptPEP723:
    """--brief loads skf-resolve-authoritative-files.py, which reads the brief with PyYAML: under `uv run` the
    header must declare it."""

    @pytest.fixture
    def header(self) -> str:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        start = text.find("# /// script")
        end = text.find("# ///", start + 1)
        return text[start : end + len("# ///")]

    def test_has_pep723_header(self, header: str) -> None:
        assert "# /// script" in header

    def test_requires_python(self, header: str) -> None:
        assert "requires-python" in header

    def test_pyyaml_dependency(self, header: str) -> None:
        assert "pyyaml" in header.lower()

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
