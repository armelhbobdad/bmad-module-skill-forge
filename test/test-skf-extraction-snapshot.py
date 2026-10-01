#!/usr/bin/env python3
"""Tests for skf-extraction-snapshot.py, audit-skill's re-index snapshot.

scan-list writes the provenance map's bounded scan list for the runner's
--files-from; build turns the runner's JSON and the exports read by eye
into extraction-snapshot.json, with a status for every file, a
completeness verdict, the libraries of a stack and the public API outside
the skill's scope, and prints what step 2 acts on (the files to read, the
extraction gaps, the files read after an ast-grep failure) so it never
opens the runner's JSON; relocate adds step 3's relocated exports. One
test runs the real runner (with the pinned ast-grep) over a scan list and
diffs the snapshot with skf-structural-diff.py, as audit-skill's steps 2
and 3 do.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-extraction-snapshot.py"
RUNNER = SCRIPTS / "skf-extract-public-api.py"
DIFF = SCRIPTS / "skf-structural-diff.py"

spec = importlib.util.spec_from_file_location("skf_extraction_snapshot", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((data if isinstance(data, str) else json.dumps(data)).encode("utf-8"))
    return path


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        _write(root / rel, text)
    return root


def _run(*argv: str) -> tuple[int, dict]:
    result = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True,
                            encoding="utf-8", timeout=120, check=False)
    return result.returncode, json.loads(result.stdout)


def _export(name: str, file: str, line: int, **extra) -> dict:
    """A runner export, in the fields skf-extract-public-api.py writes."""
    return {"export_name": name, "source_file": file, "source_line": line, "signature_line": f"def {name}(",
            "signature": f"def {name}(a: int) -> None:", "export_type": "function", "confidence": "T1",
            "extraction_method": "ast-grep", "ast_node_type": "function_definition", **extra}


PROVENANCE = {
    "provenance_version": "2.0",
    "skill_type": "stack",
    "entries": [
        {"export_name": "a", "source_file": "lib-a/a.py", "source_library": "lib-a"},
        {"export_name": "b", "source_file": "lib-b\\b.py", "source_library": "lib-b"},
        {"export_name": "c", "source_file": "lib-b/c.py", "source_library": "lib-b"},
        {"export_name": "gone", "source_file": "lib-a/gone.py", "source_library": "lib-a"},
    ],
    "file_entries": [{"source_file": "scripts/run.sh"}],
}


def test_scan_list_writes_the_bounded_list(tmp_path):
    provenance = _write(tmp_path / "provenance-map.json", PROVENANCE)
    out = tmp_path / "scan-files.json"
    code, line = _run("scan-list", str(provenance), "-o", str(out))
    assert (code, line["status"], line["files"]) == (0, "ok", 5)
    assert json.loads(out.read_text(encoding="utf-8")) == [
        "lib-a/a.py", "lib-a/gone.py", "lib-b/b.py", "lib-b/c.py", "scripts/run.sh"]


def test_every_file_gets_one_status(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": "", "lib-b/b.py": "", "lib-b/c.py": "", "scripts/run.sh": ""})
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1), _export("b", "lib-b/b.py", 3)],
              "file_issues": [{"file": "lib-b/c.py", "issue": "syntax-errors", "count": 1, "line": 2},
                              {"file": "scripts/run.sh", "issue": "no-recipes"}],
              "recipes": [{"id": "python-public-functions", "truncated": False}], "truncated": False}
    snap = mod.build(root, "Forge", "20260101-000000", PROVENANCE, runner, [], [])
    assert [(f["file"], f["status"], f["issue"], f["exports"]) for f in snap["files"]] == [
        ("lib-a/a.py", "extracted", None, 1),
        ("lib-a/gone.py", "missing", None, 0),
        ("lib-b/b.py", "extracted", None, 1),
        ("lib-b/c.py", "parse-failed", "syntax-errors", 0),
        # only file_entries[] names it: step 3 compares its hash, nothing reads it
        ("scripts/run.sh", "hash-tracked", "no-recipes", 0)]
    assert snap["complete"] is False
    assert snap["files_by_status"] == {"extracted": 2, "read-by-eye": 0, "hash-tracked": 1, "missing": 1,
                                       "parse-failed": 1, "unread": 0}
    assert snap["ast_fallback_files"] == ["lib-b/c.py"]
    # Read by eye, the one file completes the snapshot.
    details = [{"name": "c", "file": "lib-b/c.py", "line": 2, "type": "function", "signature": "def c():"}]
    snap = mod.build(root, "Forge", "20260101-000000", PROVENANCE, runner, ["lib-b/c.py"], details)
    assert snap["complete"] is True
    assert snap["files_by_status"]["read-by-eye"] == 1 and snap["files_by_status"]["hash-tracked"] == 1
    assert snap["ast_fallback_files"] == ["lib-b/c.py"]
    by_name = {e["name"]: e for e in snap["exports"]}
    assert (by_name["c"]["confidence"], by_name["c"]["extraction_method"]) == ("T1-low", "source-read")
    assert (by_name["a"]["confidence"], by_name["a"]["signature"]) == ("T1", "def a(a: int) -> None:")
    assert snap["counts"] == {"exports": 3, "by_type": {"function": 3}, "t1": 2, "t1_low": 1}


def test_a_script_only_file_entries_names_adds_no_export(tmp_path):
    """update-skill keeps file_entries[] out of code extraction, so the map
    records no export there: one the runner finds would read as added."""
    root = _tree(tmp_path / "src", {"lib-a/a.py": "", "scripts/tool.py": "", "README.md": ""})
    provenance = {"entries": [{"export_name": "a", "source_file": "lib-a/a.py"}],
                  "file_entries": [{"source_file": "scripts/tool.py"}, {"source_file": "README.md"}]}
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1), _export("main", "scripts/tool.py", 1)],
              "file_issues": [{"file": "README.md", "issue": "no-recipes"}]}
    snap = mod.build(root, "Forge", "t", provenance, runner, [], [])
    assert {f["file"]: f["status"] for f in snap["files"]} == {
        "README.md": "hash-tracked", "lib-a/a.py": "extracted", "scripts/tool.py": "hash-tracked"}
    assert [e["name"] for e in snap["exports"]] == ["a"] and snap["complete"] is True
    assert snap["ast_fallback_files"] == []
    assert any("scripts/tool.py: only file_entries[] names the file" in w for w in snap["warnings"])
    # without a runner (Quick tier), nothing reads them by eye either
    snap = mod.build(root, "Quick", "t", provenance, None, [], [])
    assert [f["file"] for f in snap["files"] if f["status"] == "unread"] == ["lib-a/a.py"]


def test_each_export_carries_its_files_library(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": "", "lib-b/b.py": ""})
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1), _export("b", "lib-b/b.py", 3)]}
    snap = mod.build(root, "Forge", "t", PROVENANCE, runner, [], [])
    assert [(e["name"], e["source_library"]) for e in snap["exports"]] == [("a", "lib-a"), ("b", "lib-b")]
    # a single skill's map names no library, and no export gets one
    single = {"entries": [{"export_name": "a", "source_file": "lib-a/a.py"}]}
    snap = mod.build(root, "Forge", "t", single, runner, [], [])
    assert [e["name"] for e in snap["exports"]] == ["a"]
    assert "source_library" not in snap["exports"][0]
    assert any("lib-b/b.py: the file is outside the files in scope" in w for w in snap["warnings"])


def test_an_incomplete_run_leaves_files_unread(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": "", "lib-b/b.py": "", "lib-b/c.py": ""})
    runner = {"status": "incomplete", "exports": [_export("a", "lib-a/a.py", 1), _export("c", "lib-b/c.py", 1)],
              "errors": [{"reason": "time-limit", "files": 1, "first_file": "lib-b/c.py", "detail": "x",
                          "unread": ["lib-b/c.py"]}]}
    snap = mod.build(root, "Forge+", "t", PROVENANCE, runner, [], [])
    status = {f["file"]: f["status"] for f in snap["files"]}
    # c.py is named unread; b.py has no export, so it may be unread too
    assert (status["lib-a/a.py"], status["lib-b/b.py"], status["lib-b/c.py"]) == ("extracted", "unread", "unread")
    assert snap["complete"] is False and snap["runner_errors"][0]["reason"] == "time-limit"
    # read by eye, they complete it, as files read after an ast-grep failure
    snap = mod.build(root, "Forge+", "t", PROVENANCE, runner, ["lib-b/b.py", "lib-b/c.py"], [])
    assert snap["complete"] is True and snap["ast_fallback_files"] == ["lib-b/b.py", "lib-b/c.py"]


@pytest.mark.parametrize("runner", [None, {"status": "no-ast-grep", "exports": [], "file_issues": []}],
                         ids=["no-runner-result", "no-ast-grep"])
def test_without_a_runner_every_file_is_read_by_eye(runner, tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": ""})
    provenance = {"entries": [{"export_name": "a", "source_file": "lib-a/a.py"}]}
    snap = mod.build(root, "Quick", "t", provenance, runner, [], [])
    assert [f["status"] for f in snap["files"]] == ["unread"] and snap["complete"] is False
    details = [{"export_name": "a", "source_file": "lib-a/a.py", "source_line": 1}]
    snap = mod.build(root, "Quick", "t", provenance, runner, ["lib-a/a.py"], details)
    assert snap["complete"] is True
    assert [(e["name"], e["confidence"]) for e in snap["exports"]] == [("a", "T1-low")]
    # no file is an ast-grep fallback at Quick tier; above it, all of them are
    assert snap["ast_fallback_files"] == [] and not snap["files"][0]["fallback"]
    snap = mod.build(root, "Forge", "t", provenance, runner, ["lib-a/a.py"], details)
    assert snap["ast_fallback_files"] == ["all files (ast-grep unavailable)"]


def test_a_file_read_for_its_gaps_is_no_ast_grep_fallback(tmp_path):
    """A file the runner extracted and the step then read in full, for an
    extraction gap or a Known Limitation #11 form, is read-by-eye but was
    not read after an ast-grep failure."""
    root = _tree(tmp_path / "src", {"lib-a/a.py": ""})
    provenance = {"entries": [{"export_name": "a", "source_file": "lib-a/a.py"}]}
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1)],
              "entry_point_diff": {"extraction_gaps": [
                  {"name": "Hidden", "language": "python", "entry": "lib-a/__init__.py", "file": "lib-a/a.py",
                   "line": 7}]}}
    snap = mod.build(root, "Forge", "t", provenance, runner, [], [])
    assert snap["extraction_gaps"] == [{"name": "Hidden", "file": "lib-a/a.py", "line": 7,
                                        "entry": "lib-a/__init__.py"}]
    details = [{"name": "Hidden", "file": "lib-a/a.py", "line": 7, "type": "const"}]
    snap = mod.build(root, "Forge", "t", provenance, runner, ["lib-a/a.py"], details)
    assert snap["files"][0]["status"] == "read-by-eye" and snap["ast_fallback_files"] == []
    # the name is held now, so no gap is left to read
    assert snap["extraction_gaps"] == []


def test_a_details_export_fills_what_the_runner_lacks(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": ""})
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1, signature=None, signature_line=None)]}
    details = [{"name": "a", "file": "./lib-a/a.py", "signature": "def a(x)", "confidence": "T1-low"},
               {"name": "", "file": "lib-a/a.py"}]
    snap = mod.build(root, "Forge", "t", PROVENANCE, runner, ["lib-a/a.py"], details)
    (record,) = [e for e in snap["exports"] if e["name"] == "a"]
    assert (record["signature"], record["confidence"]) == ("def a(x)", "T1")
    assert any("name no export or no file" in w for w in snap["warnings"])


def test_cap_hits_and_public_api_outside_scope(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": ""})
    runner = {"status": "ok", "exports": [], "truncated": True,
              "recipes": [{"id": "python-public-functions", "truncated": True}, {"id": "x", "truncated": False}],
              "entry_point_diff": {"outside_scope": [
                  {"name": "Zed", "language": "javascript", "entry": "index.ts", "file": "src/new/z.ts", "line": 1},
                  {"name": "Alpha", "language": "javascript", "entry": "index.ts", "file": "src/new/z.ts", "line": 4},
                  {"name": "Beta", "language": "javascript", "entry": "beta.ts", "file": "src/b.ts", "line": 2}]}}
    snap = mod.build(root, "Forge", "t", PROVENANCE, runner, [], [])
    assert (snap["truncated"], snap["cap_hits"]) == (True, ["python-public-functions"])
    assert snap["outside_scope"] == [{"path": "src/b.ts", "names": ["Beta"], "entries": ["beta.ts"]},
                                     {"path": "src/new/z.ts", "names": ["Alpha", "Zed"], "entries": ["index.ts"]}]


def test_degraded_mode_scopes_what_was_read(tmp_path):
    root = _tree(tmp_path / "src", {"a.py": "", "b.py": "", "c.py": ""})
    runner = {"status": "ok", "exports": [_export("a", "a.py", 1)],
              "file_issues": [{"file": "b.py", "issue": "not-utf8"}]}
    snap = mod.build(root, "Forge", "t", None, runner, [], [])
    assert (snap["bounded_scan"], snap["bounded_scan_source"]) == (False, "source-tree-fallback")
    assert [(f["file"], f["status"]) for f in snap["files"]] == [("a.py", "extracted"), ("b.py", "parse-failed")]


def test_degraded_mode_keeps_what_an_incomplete_run_left_unread(tmp_path):
    root = _tree(tmp_path / "src", {"a.py": "", "b.py": ""})
    runner = {"status": "incomplete", "exports": [_export("a", "a.py", 1)],
              "errors": [{"reason": "time-limit", "files": 1, "first_file": "b.py", "detail": "x",
                          "unread": ["b.py"]}]}
    snap = mod.build(root, "Forge", "t", None, runner, [], [])
    assert [(f["file"], f["status"]) for f in snap["files"]] == [("a.py", "extracted"), ("b.py", "unread")]
    assert snap["complete"] is False


def test_the_cli_writes_the_snapshot_and_reports_errors(tmp_path):
    root = _tree(tmp_path / "src", {"lib-a/a.py": ""})
    provenance = _write(tmp_path / "provenance-map.json", {"entries": [{"export_name": "a",
                                                                        "source_file": "lib-a/a.py"}]})
    runner = _write(tmp_path / "extraction.json", {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1)]})
    out = tmp_path / "extraction-snapshot.json"
    code, line = _run("build", "--source-root", str(root), "--tier", "Forge", "--date", "20260101-000000",
                      "--provenance-map", str(provenance), "--extraction", str(runner), "-o", str(out))
    assert (code, line["status"], line["complete"], line["runner_status"]) == (0, "ok", True, "ok")
    assert (line["to_read"], line["extraction_gaps"], line["ast_fallback_files"]) == ([], [], [])
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert (snap["extraction_date"], snap["confidence_tier"], snap["files_scanned"]) == ("20260101-000000", "Forge", 1)
    assert snap["source_root"] == str(root)
    bad = _write(tmp_path / "details.json", {"files": "lib-a/a.py"})
    code, line = _run("build", "--source-root", str(root), "--tier", "Forge", "--date", "t",
                      "--details", str(bad), "-o", str(out))
    assert (code, line["status"]) == (2, "error") and "`files` must be a list" in line["error"]
    code, line = _run("build", "--source-root", str(tmp_path / "none"), "--tier", "Forge", "--date", "t",
                      "-o", str(out))
    assert code == 2 and "source root not found" in line["error"]
    code, line = _run("scan-list", str(tmp_path / "missing.json"), "-o", str(out))
    assert code == 2 and "cannot read provenance map" in line["error"]


def test_the_build_line_lists_what_to_read_and_takes_one_details_file_per_worker(tmp_path):
    """Step 2 acts on the printed line alone: the files to read, with their
    status and issue, and the extraction gaps; each worker's file is passed
    with its own --details, and the recorded source root is kept."""
    root = _tree(tmp_path / "tree", {"pkg/a.py": "", "pkg/b.py": "", "pkg/c.py": ""})
    provenance = _write(tmp_path / "provenance-map.json", {"entries": [
        {"export_name": n, "source_file": f"pkg/{n}.py"} for n in ("a", "b", "c")]})
    runner = _write(tmp_path / "extraction.json", {
        "status": "incomplete", "exports": [_export("a", "pkg/a.py", 1)],
        "file_issues": [{"file": "pkg/b.py", "issue": "syntax-errors", "count": 1, "line": 3}],
        "errors": [{"reason": "time-limit", "files": 1, "first_file": "pkg/c.py", "detail": "x",
                    "unread": ["pkg/c.py"]}],
        "entry_point_diff": {"extraction_gaps": [{"name": "G", "language": "python", "entry": "pkg/__init__.py",
                                                  "file": "pkg/a.py", "line": 9}]}})
    out = tmp_path / "extraction-snapshot.json"
    base = ["build", "--source-root", str(root), "--source-path", "/recorded/src", "--tier", "Forge",
            "--date", "t", "--provenance-map", str(provenance), "--extraction", str(runner), "-o", str(out)]
    code, line = _run(*base)
    assert (code, line["runner_status"], line["complete"]) == (0, "incomplete", False)
    assert line["to_read"] == [{"file": "pkg/b.py", "status": "parse-failed", "issue": "syntax-errors"},
                               {"file": "pkg/c.py", "status": "unread", "issue": None}]
    assert [g["name"] for g in line["extraction_gaps"]] == ["G"]
    one = _write(tmp_path / "export-details-1.json", {"files": ["pkg/b.py"], "exports": [
        {"name": "b", "file": "pkg/b.py", "line": 1, "type": "function"}]})
    two = _write(tmp_path / "export-details-2.json", {"files": ["pkg/c.py"], "exports": [
        {"name": "c", "file": "pkg/c.py", "line": 1, "type": "function"},
        {"name": "G", "file": "pkg/a.py", "line": 9, "type": "const"}]})
    code, line = _run(*base, "--details", str(one), "--details", str(two))
    assert (code, line["complete"], line["to_read"], line["extraction_gaps"]) == (0, True, [], [])
    assert line["ast_fallback_files"] == ["pkg/b.py", "pkg/c.py"]
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert snap["source_root"] == "/recorded/src"
    assert sorted(e["name"] for e in snap["exports"]) == ["G", "a", "b", "c"]


def test_relocate_adds_a_removed_name_found_outside_the_scope(tmp_path):
    """Step 3's relocation check: the runner's exports over the candidate
    files join the snapshot only under a removed name, from a file outside
    the scope, with the removed entry's library, and the counts follow."""
    root = _tree(tmp_path / "src", {"lib-a/a.py": "", "lib-b/b.py": "", "lib-b/c.py": ""})
    runner = {"status": "ok", "exports": [_export("a", "lib-a/a.py", 1), _export("b", "lib-b/b.py", 3),
                                          _export("c", "lib-b/c.py", 1)]}
    snapshot = _write(tmp_path / "extraction-snapshot.json", mod.build(root, "Forge+", "t", PROVENANCE, runner, [], []))
    diff = _write(tmp_path / "structural-diff.json", {"removed": [
        {"name": "gone", "file": "lib-a/gone.py", "line": 1, "source_library": "lib-a"}]})
    found = _write(tmp_path / "relocations.json", {"status": "ok", "exports": [
        _export("gone", "lib-a/util/moved.py", 4), _export("other", "lib-a/util/moved.py", 9),
        _export("gone", "lib-b/b.py", 7)]})
    code, line = _run("relocate", str(snapshot), "--diff", str(diff), "--extraction", str(found))
    assert (code, line["added"], line["names"]) == (0, 1, ["gone"])
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    (moved,) = [e for e in snap["exports"] if e["name"] == "gone"]
    assert (moved["file"], moved["line"], moved["source_library"], moved["confidence"]) == (
        "lib-a/util/moved.py", 4, "lib-a", "T1")
    assert snap["counts"]["exports"] == 4 and snap["relocations"] == [
        {"name": "gone", "file": "lib-a/util/moved.py", "line": 4}]
    # run again, it finds the export already there and writes nothing
    code, line = _run("relocate", str(snapshot), "--diff", str(diff), "--extraction", str(found))
    assert (code, line["added"]) == (0, 0)
    code, line = _run("relocate", str(snapshot), "--diff", str(diff), "--extraction", str(tmp_path / "none.json"))
    assert code == 2 and "cannot read runner result" in line["error"]


def _pinned_ast_grep() -> bool:
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_the_runner_snapshot_diffs_against_the_map(tmp_path):
    """Steps 2 and 3 end to end: the scan list, the runner over it, the
    snapshot, and the diff, which finds the one changed signature and
    reports the deleted file's export removed."""
    root = _tree(tmp_path / "src", {
        "pkg/api.py": "def fetch(\n    url: str,\n    retries: int = 3,\n) -> bytes:\n    return b''\n",
        "pkg/util.py": "def helper(x: int) -> int:\n    return x\n\n\ndef added() -> None:\n    pass\n",
        "pkg/extra.py": "def outside() -> None:\n    pass\n",
    })
    provenance = _write(tmp_path / "forge" / "provenance-map.json", {"entries": [
        {"export_name": "fetch", "export_type": "function", "source_file": "pkg/api.py", "source_line": 1,
         "signature": "def fetch(url: str, retries: int = 3) -> bytes:", "confidence": "T1",
         "extraction_method": "ast-grep"},
        {"export_name": "helper", "export_type": "function", "source_file": "pkg/util.py", "source_line": 1,
         "signature": "def helper(x: str) -> int:", "confidence": "T1", "extraction_method": "ast-grep"},
        {"export_name": "old", "export_type": "function", "source_file": "pkg/old.py", "source_line": 1,
         "signature": "def old():", "confidence": "T1", "extraction_method": "ast-grep"},
    ]})
    data = tmp_path / "forge" / ".skf-audit" / "20260101-000000"
    scan = data / "scan-files.json"
    data.mkdir(parents=True)
    assert _run("scan-list", str(provenance), "-o", str(scan))[0] == 0
    extraction = data / "extraction.json"
    runner = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(root),
                             "--files-from", str(scan), "--head-cap", "0", "-o", str(extraction)],
                            capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert runner.returncode == 0, runner.stderr
    snapshot = tmp_path / "forge" / "extraction-snapshot.json"
    code, line = _run("build", "--source-root", str(root), "--tier", "Forge", "--date", "20260101-000000",
                      "--provenance-map", str(provenance), "--extraction", str(extraction), "-o", str(snapshot))
    assert code == 0 and line["files_by_status"]["missing"] == 1 and line["complete"] is True
    diff = subprocess.run([sys.executable, str(DIFF), str(provenance), str(snapshot)], capture_output=True,
                          text=True, encoding="utf-8", timeout=120, check=False)
    assert diff.returncode == 1, diff.stdout
    result = json.loads(diff.stdout)
    assert [(c["name"], c["field"]) for c in result["changed"]] == [("helper", "signature")]
    assert [r["name"] for r in result["removed"]] == ["old"]
    assert [a["name"] for a in result["added"]] == ["added"]
