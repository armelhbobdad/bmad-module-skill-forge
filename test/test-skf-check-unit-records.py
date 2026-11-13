#!/usr/bin/env python3
"""Tests for skf-check-unit-records.py, which skf-analyze-source's step 4 runs.

Each subagent of map-and-detect section 2 writes its record as a file and
returns only its path; the script strips a wrapping fence, parses and checks
every record against the contract, so the parent neither copies a record
nor checks one by hand (#592, analyze-source determinism-11).

#1125 (analyze-source determinism-2 and -5): `from-extract` writes each
unit's record from the extractor's output, the recipe run's -o file or the
parser's stdout, so the model maps no extractor JSON into a record: every
I/O row of the spec (exit 0 with a namespace, 1, 3, no recipe,
files_in_scope 0, the parser, the input errors) writes a record the check
passes with no problem, and `parser` is a strategy the contract accepts.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-check-unit-records.py"
MAP = REPO / "src" / "skf-analyze-source" / "references" / "map-and-detect.md"
UNIT_EXPORTS = REPO / "src" / "skf-analyze-source" / "references" / "map-unit-exports.md"

spec = importlib.util.spec_from_file_location("skf_check_unit_records", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GOOD = {
    "unit_name": "auth",
    "files_count": 12,
    "exports_count": 7,
    "export_pattern": "barrel: 5 functions, 2 classes",
    "api_surface": ["login", "logout"],
    "ccc_signals": {"top_files": [], "available": False},
    "strategy_used": "ast-grep",
    "confidence": "T1",
    "warnings": ["extraction gap: refresh at src/token.ts:40"],
}


def _folder(tmp_path: Path, replies: dict[str, str]) -> Path:
    folder = tmp_path / "unit-records"
    folder.mkdir()
    for name, text in replies.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    return folder


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=60)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(json.dumps(GOOD), id="plain"),
        pytest.param("```json\n" + json.dumps(GOOD, indent=2) + "\n```\n", id="json-fence"),
        pytest.param("```\r\n" + json.dumps(GOOD) + "\r\n```", id="bare-fence-crlf"),
        pytest.param("Here is the record:\n" + json.dumps(GOOD) + "\nDone.", id="prose-around"),
        pytest.param("﻿" + json.dumps(GOOD), id="byte-order-mark"),
    ],
)
def test_a_good_reply_gives_its_record_unchanged(tmp_path, text):
    out = mod.check_folder(_folder(tmp_path, {"auth.json": text}))
    assert out["records"] == [GOOD]
    assert (out["problems"], out["unreadable"]) == ([], [])
    assert out["warnings"] == ["auth: extraction gap: refresh at src/token.ts:40"]


def test_a_missing_or_wrong_key_degrades_the_record_and_names_the_problem(tmp_path):
    record = {k: v for k, v in GOOD.items() if k != "exports_count"}
    record.update({"confidence": "T2", "api_surface": "login", "extra": 1})
    out = mod.check_folder(_folder(tmp_path, {"auth.json": json.dumps(record)}))
    [checked] = out["records"]
    assert (checked["exports_count"], checked["confidence"], checked["api_surface"]) == (0, "T1-low", [])
    assert checked["extra"] == 1, "a key the contract does not name is kept"
    problems = [p["problem"] for p in out["problems"]]
    assert problems[0] == "missing key exports_count"
    assert any(p.startswith("key api_surface has the wrong type") for p in problems)
    assert any(p.startswith("key confidence has the wrong type") for p in problems)
    assert {p["unit_name"] for p in out["problems"]} == {"auth"}


def test_a_record_with_the_retired_scripts_assets_key_is_kept_as_it_came(tmp_path):
    """The contract no longer asks for a scripts/assets survey: a record that
    still carries one is neither a problem nor rewritten."""
    assert "scripts_assets" not in mod.CONTRACT
    record = {**GOOD, "scripts_assets": {"scripts": ["bin/cli.js"], "assets": []}}
    out = mod.check_folder(_folder(tmp_path, {"auth.json": json.dumps(record)}))
    assert out["records"] == [record]
    assert out["problems"] == []


def test_counts_reject_booleans_and_negatives(tmp_path):
    out = mod.check_folder(_folder(tmp_path, {"a.json": json.dumps({**GOOD, "files_count": True,
                                                                     "exports_count": -1})}))
    assert (out["records"][0]["files_count"], out["records"][0]["exports_count"]) == (0, 0)
    assert len(out["problems"]) == 2


def test_a_reply_with_no_object_is_unreadable(tmp_path):
    folder = _folder(tmp_path, {"a.json": json.dumps(GOOD), "b.json": "I could not read the unit.",
                                "c.json": "[1, 2]", "d.json": ""})
    out = mod.check_folder(folder)
    assert [r["unit_name"] for r in out["records"]] == ["auth"]
    assert out["unreadable"] == ["b.json", "c.json", "d.json"]


def test_records_come_in_file_name_order(tmp_path):
    folder = _folder(tmp_path, {f"{n}.json": json.dumps({**GOOD, "unit_name": n}) for n in ("zeta", "alpha", "mid")})
    assert [r["unit_name"] for r in mod.check_folder(folder)["records"]] == ["alpha", "mid", "zeta"]


def test_the_cli_prints_the_result_and_refuses_a_missing_folder(tmp_path):
    folder = _folder(tmp_path, {"auth.json": "```json\n" + json.dumps({**GOOD, "unit_name": "café"}) + "\n```"})
    proc = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(folder)], capture_output=True, timeout=60,
                          env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8"))["records"][0]["unit_name"] == "café"
    missing = _run("--dir", str(tmp_path / "absent"))
    assert missing.returncode == 2 and b"is not a folder" in missing.stderr


def test_map_and_detect_runs_the_check_instead_of_stripping_fences_by_hand():
    # map-and-detect resolves the helper; the export mapping it loads (as the
    # [D] file does) runs it.
    assert ("checkUnitRecordsProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-check-unit-records.py'"
            in MAP.read_text(encoding="utf-8"))
    text = UNIT_EXPORTS.read_text(encoding="utf-8")
    assert 'uv run {checkUnitRecordsHelper} --dir "{run_dir}/unit-records"' in text
    assert "Strip any wrapping markdown fences" not in text
    assert "Validate each payload against the contract" not in text
    # The contract the script checks is the one the prose shows the subagents.
    block = text.split("## 3. Record Contract", 1)[1].split("```json\n", 1)[1].split("```", 1)[0]
    keys = re.findall(r'^\s*"([a-z_]+)":', block, re.M)
    assert keys == list(mod.CONTRACT)


# --------------------------------------------------------------------------
# from-extract: a unit's record from the extractor's output (#1125)
# --------------------------------------------------------------------------


def _full(**over) -> dict:
    """A --mode full output: public login, logout and namespace ns (a, b), a
    gap, a file issue, four public names, a barrel, capped."""
    out = {
        "mode": "full",
        "status": "ok",
        "files_in_scope": 6,
        "files_without_recipes": {},
        "file_issues": [{"file": "src/x.ts", "issue": "syntax-errors", "count": 1, "line": 3}],
        "truncated": True,
        "aggregates": {"exports": 4, "by_type": {"class": 1, "function": 3}, "t1": 4, "t1_low": 0},
        "entry_points": {"status": "barrel", "files": [{"language": "javascript", "file": "src/index.ts",
                                                       "package": "auth", "subpath": ".", "resolution": "file",
                                                       "in_scope": True}]},
        "entry_point_diff": {
            "public": [
                {"name": "login", "language": "javascript", "entry": "src/index.ts", "via": "declaration",
                 "file": "src/index.ts", "line": 1},
                {"name": "logout", "language": "javascript", "entry": "src/index.ts", "via": "declaration",
                 "file": "src/index.ts", "line": 2},
                {"name": "ns", "language": "javascript", "entry": "src/index.ts", "via": "namespace",
                 "file": "src/ns.ts", "line": None,
                 "members": [{"name": "a", "local": None, "file": "src/ns.ts", "line": 1},
                             {"name": "b", "local": None, "file": "src/ns.ts", "line": 2}]},
                {"name": "login", "language": "javascript", "entry": "src/other.ts", "via": "re-export",
                 "file": "src/index.ts", "line": 1},
            ],
            "extraction_gaps": [{"name": "refresh", "language": "javascript", "entry": "src/index.ts",
                                 "file": "src/token.ts", "line": 40}],
        },
        "counts": {"exports_public_api": 4},
        "errors": [],
    }
    out.update(over)
    return out


def _from_extract(tmp_path: Path, data, exit_code: int, language: str = "typescript", unit: str = "auth",
                  files_count: int = 9) -> tuple[subprocess.CompletedProcess, Path]:
    extract = tmp_path / "extract" / "unit.json"
    extract.parent.mkdir(exist_ok=True)
    extract.write_bytes(data if isinstance(data, bytes) else json.dumps(data, indent=2).encode("utf-8"))
    folder = tmp_path / "unit-records"
    proc = _run("from-extract", "--extract", str(extract), "--exit-code", str(exit_code), "--unit-name", unit,
                "--files-count", str(files_count), "--language", language, "--dir", str(folder))
    return proc, folder


def _written(tmp_path: Path, data, exit_code: int, **kw) -> tuple[dict, dict]:
    """(the printed line, the record written), the record passing the check with no problem."""
    proc, folder = _from_extract(tmp_path, data, exit_code, **kw)
    assert proc.returncode == 0, proc.stderr
    line = json.loads(proc.stdout.decode("utf-8"))
    checked = mod.check_folder(folder)
    assert (checked["problems"], checked["unreadable"]) == ([], [])
    [record] = checked["records"]
    assert list(record) == list(mod.CONTRACT), "every contract key, in order"
    assert Path(line["record"]) == folder / f"{record['unit_name']}.json"
    assert (line["strategy_used"], line["exports_count"]) == (record["strategy_used"], record["exports_count"])
    return line, record


GAP = {"why": "extraction-gap", "name": "refresh", "file": "src/token.ts", "line": 40}
ISSUE = {"why": "file-issue", "file": "src/x.ts", "issue": "syntax-errors"}


def test_a_recipe_run_gives_the_whole_record_and_leaves_only_the_gaps_to_read(tmp_path):
    line, record = _written(tmp_path, _full(), 0)
    assert record == {
        "unit_name": "auth",
        "files_count": 9,
        "exports_count": 4,
        "export_pattern": "barrel: function 3, class 1, capped",
        "api_surface": ["login", "logout", "a", "b"],
        "ccc_signals": {"top_files": [], "available": False},
        "strategy_used": "ast-grep",
        "confidence": "T1",
        "warnings": ["extraction gap: refresh at src/token.ts:40", "file issue: src/x.ts (syntax-errors)"],
    }
    assert line["to_read"] == [GAP, ISSUE]


def test_an_incomplete_run_adds_a_warning_per_error(tmp_path):
    error = {"reason": "ast-grep-timeout", "files": 12, "first_file": "src/big.ts", "detail": "x",
             "unread": ["src/big.ts"]}
    line, record = _written(tmp_path, _full(status="incomplete", errors=[error]), 1)
    assert (record["strategy_used"], record["confidence"], record["exports_count"]) == ("ast-grep", "T1", 4)
    assert record["warnings"] == ["extraction gap: refresh at src/token.ts:40", "file issue: src/x.ts (syntax-errors)",
                                  "ast-grep run incomplete: ast-grep-timeout (12 files, first src/big.ts)"]
    assert line["to_read"] == [GAP, ISSUE]


def test_a_namespace_the_trace_cannot_read_counts_as_its_own_name_and_a_gap_may_have_no_file(tmp_path):
    data = _full(truncated=False)
    data["entry_point_diff"]["public"][2]["members"] = None
    data["entry_point_diff"]["extraction_gaps"][0].update(file=None, line=None)
    line, record = _written(tmp_path, data, 0)
    assert record["api_surface"] == ["login", "logout", "ns"]
    assert record["export_pattern"] == "barrel: function 3, class 1"
    assert record["warnings"][0] == "extraction gap: refresh (no file)"
    assert line["to_read"][0] == {"why": "extraction-gap", "name": "refresh", "file": None, "line": None}


def test_no_ast_grep_leaves_the_entry_points_to_read(tmp_path):
    data = _full(status="no-ast-grep", entry_point_diff={}, counts={}, aggregates={}, file_issues=[])
    data["entry_points"]["status"] = None
    line, record = _written(tmp_path, data, 3)
    assert (record["strategy_used"], record["confidence"], record["exports_count"]) == ("source-read", "T1-low", 0)
    assert (record["api_surface"], record["export_pattern"], record["warnings"]) == ([], "", [])
    assert line["to_read"] == [{"why": "entry-point", "file": "src/index.ts"}]
    # No entry point listed: the unit's sources are read instead.
    data["entry_points"]["files"] = []
    line, _ = _written(tmp_path, data, 3)
    assert line["to_read"] == [{"why": "unit-sources"}]


@pytest.mark.parametrize(
    "language,over",
    [
        pytest.param("csharp", {"files_in_scope": 0, "files_without_recipes": {".cs": 7}}, id="no-recipe"),
        pytest.param("typescript", {"files_in_scope": 0}, id="no-file-in-scope"),
        pytest.param("ruby", {}, id="a-language-without-a-recipe"),
    ],
)
def test_a_run_that_counted_no_export_of_the_unit_leaves_its_sources_to_read(tmp_path, language, over):
    line, record = _written(tmp_path, _full(**over), 0, language=language)
    assert (record["strategy_used"], record["confidence"], record["exports_count"]) == ("source-read", "T1-low", 0)
    assert (record["api_surface"], record["warnings"]) == ([], [])
    assert line["to_read"] == [{"why": "unit-sources"}]


PARSER = {
    "language": "java",
    "package_name": None,
    "exports": [{"name": "Api", "type": "class", "source_file": "src/main/java/com/acme/Api.java"},
                {"name": "Store", "type": "interface", "source_file": "src/main/java/com/acme/Store.java"},
                {"name": "Api", "type": "class", "source_file": "src/main/java/com/acme/v2/Api.java"}],
    "warnings": ["no manifest content provided; metadata will be empty", "src/x.java: a note"],
    "unlisted": [],
}


def test_the_parser_gives_a_parser_record_with_nothing_to_read(tmp_path):
    assert "parser" in mod.STRATEGIES
    line, record = _written(tmp_path, PARSER, 0, language="java")
    assert record == {
        "unit_name": "auth",
        "files_count": 9,
        "exports_count": 3,
        "export_pattern": "parser: class 2, interface 1",
        "api_surface": ["Api", "Store"],
        "ccc_signals": {"top_files": [], "available": False},
        "strategy_used": "parser",
        "confidence": "T1",
        "warnings": ["src/x.java: a note"],
    }
    assert line["to_read"] == []


def test_a_parser_run_that_found_no_source_file_leaves_the_sources_to_read(tmp_path):
    """A Kotlin unit built with Maven reads as java: --all-sources finds no .java file and exits 0 with no
    export. That run read nothing, so the record is source-read with its warning, never a T1 zero."""
    unit = tmp_path / "unit"
    for rel, text in {"pom.xml": "<project/>\n", "src/main/kotlin/acme/Api.kt": "package acme\nclass Api\n"}.items():
        (unit / rel).parent.mkdir(parents=True, exist_ok=True)
        (unit / rel).write_bytes(text.encode("utf-8"))
    extractor = SCRIPT.parent / "skf-extract-public-api.py"
    run = subprocess.run([sys.executable, str(extractor), "--mode", "quick", "--language", "java", "--source-root",
                          str(unit), "--all-sources"], capture_output=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["exports"] == []
    line, record = _written(tmp_path, run.stdout, 0, language="java")
    assert (record["strategy_used"], record["confidence"], record["exports_count"]) == ("source-read", "T1-low", 0)
    assert [w for w in record["warnings"] if w.startswith(mod.ALL_SOURCES_FOUND_NONE)] == record["warnings"] != []
    assert line["to_read"] == [{"why": "unit-sources"}]


def test_the_runs_own_warnings_reach_the_record(tmp_path):
    """The extractor's own warnings come first, in the ast-grep record and in a source-read one."""
    warning = "src/legacy.py: this Python cannot parse it (invalid syntax, line 3); its names are read from its text"
    _, record = _written(tmp_path, _full(warnings=[warning, warning]), 0)
    assert record["warnings"] == [warning, "extraction gap: refresh at src/token.ts:40",
                                  "file issue: src/x.ts (syntax-errors)"]
    data = _full(status="no-ast-grep", warnings=["ast-grep is not on PATH: no recipe ran; extract by source reading"])
    _, record = _written(tmp_path, data, 3)
    assert (record["strategy_used"], record["warnings"]) == (
        "source-read", ["ast-grep is not on PATH: no recipe ran; extract by source reading"])


def test_the_checks_help_names_from_extract():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, timeout=60,
                          env={**os.environ, "COLUMNS": "200"})
    assert proc.returncode == 0 and b"from-extract --help" in proc.stdout


def test_a_parser_error_leaves_the_sources_to_read(tmp_path):
    line, record = _written(tmp_path, {"_error": "unknown language: 'cobol'"}, 1, language="cobol")
    assert (record["strategy_used"], record["exports_count"], line["to_read"]) == ("source-read", 0,
                                                                                  [{"why": "unit-sources"}])


@pytest.mark.parametrize(
    "data,exit_code,unit,message",
    [
        pytest.param(_full(), 2, "auth", b"exited 2", id="extractor-input-error"),
        pytest.param(_full(), 0, "a/b", b"--unit-name must name one file", id="slash"),
        pytest.param(_full(), 0, "a\\b", b"--unit-name must name one file", id="backslash"),
        pytest.param(_full(), 0, "..", b"--unit-name must name one file", id="dot-dot"),
        pytest.param(b"", 0, "auth", b"is empty", id="empty"),
        pytest.param(b"{not json", 0, "auth", b"is not JSON", id="not-json"),
        pytest.param({"mode": "entries", "entry_files": []}, 0, "auth", b"neither", id="another-mode"),
        pytest.param([1, 2], 0, "auth", b"neither", id="a-list"),
    ],
)
def test_an_input_error_exits_2_and_writes_nothing(tmp_path, data, exit_code, unit, message):
    proc, folder = _from_extract(tmp_path, data, exit_code, unit=unit)
    assert (proc.returncode, proc.stdout) == (2, b"")
    assert message in proc.stderr
    assert not folder.exists()


def test_a_missing_extract_exits_2(tmp_path):
    folder = tmp_path / "unit-records"
    proc = _run("from-extract", "--extract", str(tmp_path / "absent.json"), "--exit-code", "0", "--unit-name", "a",
                "--files-count", "1", "--language", "go", "--dir", str(folder))
    assert proc.returncode == 2 and b"does not exist" in proc.stderr
    assert not folder.exists()


def test_the_record_keeps_a_non_ascii_name_on_a_cp1252_console(tmp_path):
    data = _full()
    data["entry_point_diff"]["public"][0]["name"] = "café"
    extract = tmp_path / "x.json"
    extract.write_bytes(json.dumps(data).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "from-extract", "--extract", str(extract), "--exit-code", "0",
                           "--unit-name", "café", "--files-count", "1", "--language", "typescript",
                           "--dir", str(tmp_path / "records")],
                          capture_output=True, timeout=60, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8"))["exports_count"] == 4
    [record] = mod.check_folder(tmp_path / "records")["records"]
    assert (record["unit_name"], record["api_surface"][0]) == ("café", "café")


def test_map_unit_exports_runs_from_extract_after_each_extraction():
    text = UNIT_EXPORTS.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "{checkUnitRecordsHelper} from-extract" in line]
    assert len(lines) == 2, lines
    for line in lines:
        extraction, _, record = line.partition("; ")
        assert record == ('uv run {checkUnitRecordsHelper} from-extract --extract "{run_dir}/extract/{unit_name}.json" '
                          '--exit-code $? --unit-name "{unit_name}" --files-count {files_count} '
                          '--language {language} --dir "{run_dir}/unit-records"')
        assert extraction.endswith('"{run_dir}/extract/{unit_name}.json"')
    assert '"strategy_used": "ast-grep|parser|source-read"' in text
    for gone in ("`exports_count` ← `counts.exports_public_api`", "`api_surface` ← the names in"):
        assert gone not in text, gone
