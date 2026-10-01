#!/usr/bin/env python3
"""Tests for skf-new-file-diff.py (skf-update-skill detect-changes Category D).

Covers the NEW_FILE set-difference: inventory source_files minus provenance
file_entries, with [MANUAL] paths set aside and kind carried through.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-update-skill" / "scripts" / "skf-new-file-diff.py"

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

    def test_provenance_missing_file_entries_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"something_else": []}))
        proc = run_cli(str(prov), json.dumps(detect()))
        assert proc.returncode == 2


class TestArgparse:
    """argparse documents the CLI (#601); arguments, output and exit 2 stay as they were."""

    def test_help_documents_the_cli(self) -> None:
        proc = run_args(["--help"])
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.startswith("usage: skf-new-file-diff.py [-h] provenance-map-path")
        for token in ("detect JSON on stdin", '"new_files"', '"skipped_manual"', '"already_tracked"',
                      "Exit codes:", "2  bad input"):
            assert token in proc.stdout, token

    def test_help_is_ascii(self) -> None:
        # No _force_utf8 needed: --help prints only ASCII, so a cp1252 console prints it as is.
        proc = run_args(["--help"])
        assert proc.returncode == 0 and proc.stdout and proc.stdout.isascii(), proc.stderr

    @pytest.mark.parametrize("args", [[], ["a.json", "b.json"], ["--provenance", "a.json"]],
                             ids=["no-argument", "two-arguments", "unknown-flag"])
    def test_usage_error_is_a_json_error_with_exit_2(self, args: list[str]) -> None:
        proc = run_args(args, json.dumps(detect()))
        assert proc.returncode == 2
        assert proc.stdout == ""
        error = json.loads(proc.stderr)["error"]
        assert error.startswith("usage: skf-new-file-diff.py <provenance-map-path>  (detect JSON on stdin): ")

    def test_one_positional_argument(self) -> None:
        parser = mod._build_parser()
        positionals = [a for a in parser._actions if not a.option_strings]
        assert [a.dest for a in positionals] == ["provenance_map"]
        assert {s for a in parser._actions for s in a.option_strings} == {"-h", "--help"}

    def test_main_reads_its_own_argv(self, tmp_path: Path, monkeypatch, capsys) -> None:
        prov = tmp_path / "prov.json"
        prov.write_bytes(json.dumps({"file_entries": [{"source_file": "scripts/old.py"}]}).encode("utf-8"))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(detect(scripts=["scripts/old.py", "scripts/new.py"]))))
        assert mod.main(["skf-new-file-diff.py", str(prov)]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["new_files"] == [{"source_file": "scripts/new.py", "kind": "script"}]
        assert out["already_tracked"] == ["scripts/old.py"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
