#!/usr/bin/env python3
"""Tests for skf-extraction-snapshot.py, audit-skill's re-index snapshot.

scan-list writes the provenance map's bounded scan list for the runner's
--files-from; build turns the runner's JSON and the exports read by eye
into extraction-snapshot.json, with a status for every file, a
completeness verdict, the libraries of a stack and the public API outside
the skill's scope, and prints what step 2 acts on (the files to read, the
extraction gaps, the files read after an ast-grep failure) so it never
opens the runner's JSON; relocation-candidates lists the files outside the
scan list that hold a removed name, with one git grep or ccc search per
name (#1131), and relocate adds step 3's relocated exports. The extraction
gaps add the map's entries the runner leaves out (an underscore name)
while their file still declares them (#682), by the verifier's declaration
rule, which a build cannot go without; a module or package entry so
declared is an export of the snapshot instead, its signature read from its
path (#1131). With
--scope-type public-api the build marks each export `public` by the
public-surface rule skf-extraction-inventory.py keeps for create-skill and
update-skill (#702): every export stays, the one problem the rule gives
when it reads no surface is kept, and any other scope type marks nothing
and never loads that helper. Three tests run the real runner (with the
pinned ast-grep) over a scan list and diff the snapshot with
skf-structural-diff.py, as audit-skill's steps 2 and 3 do. No fixture
holds a namespace re-export (`via: namespace`), so a change to how the
rule reads one cannot flip them.
"""

from __future__ import annotations

import importlib.util
import json
import os
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
_diff_spec = importlib.util.spec_from_file_location("skf_structural_diff_for_snapshot", DIFF)
diff_mod = importlib.util.module_from_spec(_diff_spec)
_diff_spec.loader.exec_module(diff_mod)


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


# --------------------------------------------------------------------------
# Baseline gaps: map entries the runner leaves out (#682)
# --------------------------------------------------------------------------

# oms-cognee 1.0.0's shape against cognee v1.6.2: the runner drops underscore
# names and module entries, and its own entry-point diff already lists Drop.
COGNEE = {
    "cognee/__init__.py": "from .version import get_cognee_version\n\n__version__ = get_cognee_version()\n",
    "cognee/api/v1/__init__.py": "from cognee.api.v1.visualize import visualize_graph as visualize\n",
    "cognee/api/v1/session/session.py": "def get_session():\n    pass\n",
    "cognee/modules/pipelines/__init__.py": "from .tasks import Task\n",
    "cognee/pipelines/types.py": "class _Drop:\n    pass\n\n\nDrop = _Drop()\n",
    "cognee/run_migrations.py": "def run_migrations():\n    pass\n",
}


def _entry(name: str, file: str, export_type: str, line: int = 1, **extra) -> dict:
    return {"export_name": name, "export_type": export_type, "source_file": file, "source_line": line, **extra}


COGNEE_MAP = {"entries": [
    _entry("__version__", "cognee/__init__.py", "variable", 6),
    _entry("visualize", "cognee/api/v1/__init__.py", "alias", 6),
    _entry("session", "cognee/api/v1/session/session.py", "module"),
    _entry("pipelines", "cognee/modules/pipelines/__init__.py", "module"),
    _entry("Drop", "cognee/pipelines/types.py", "sentinel", 32),
    _entry("run_startup_migrations", "cognee/run_migrations.py", "async_function", 80),
    _entry("run_migrations", "cognee/run_migrations.py", "function"),
]}
COGNEE_RUNNER = {"status": "ok", "exports": [_export("run_migrations", "cognee/run_migrations.py", 1)],
                 "entry_point_diff": {"extraction_gaps": [
                     {"name": "Drop", "language": "python", "entry": "cognee/__init__.py",
                      "file": "cognee/pipelines/types.py", "line": 5}]}}


def test_a_map_entry_the_source_still_declares_is_a_gap(tmp_path):
    """Each entry the snapshot lacks whose file still declares it is a gap
    at its declaration, with the map's export_type: a dunder and an alias
    that renames. A module and a package are exports instead (#1131). A
    name the source no longer declares is a real removal, and Drop, which
    the runner lists, is listed once."""
    root = _tree(tmp_path / "src", COGNEE)
    snap = mod.build(root, "Deep", "t", COGNEE_MAP, COGNEE_RUNNER, [], [])
    assert snap["extraction_gaps"] == [
        {"name": "Drop", "file": "cognee/pipelines/types.py", "line": 5, "entry": "cognee/__init__.py"},
        {"name": "__version__", "file": "cognee/__init__.py", "line": 3, "entry": None, "export_type": "variable"},
        {"name": "visualize", "file": "cognee/api/v1/__init__.py", "line": 1, "entry": None,
         "export_type": "alias"},
    ]
    modules = {e["name"]: (e["signature"], e["line"]) for e in snap["exports"] if e["type"] == "module"}
    assert modules == {"session": ("module cognee.api.v1.session.session", 1),
                       "pipelines": ("module cognee.modules.pipelines", 1)}
    # read by eye with the gaps' types, they are held and no gap is left
    details = [{"name": g["name"], "file": g["file"], "line": g["line"], "type": g.get("export_type", "sentinel")}
               for g in snap["extraction_gaps"]]
    snap = mod.build(root, "Deep", "t", COGNEE_MAP, COGNEE_RUNNER, [], details)
    assert snap["extraction_gaps"] == [] and snap["complete"] is True


def test_a_gap_needs_a_read_file_that_declares_the_name(tmp_path):
    """No gap for a missing or parse-failed file, a file outside the Python
    and TS/JS families, a dotted name, or a name the snapshot holds at that
    file under its own name or its reexported_as target; one gap per name
    and file, however the map spells the file. A file read by eye is
    checked as an extracted one."""
    root = _tree(tmp_path / "src", {
        "pkg/__init__.py": "__all__ = []\n",
        "pkg/broken.py": "__version__ = '1'\n",
        "pkg/x.go": "package pkg\n\nfunc _hidden() {}\n",
        "pkg/app.py": "class App:\n    def update(self):\n        pass\n",
        "pkg/impl.py": "class _Impl:\n    pass\n\n\nclass _Other:\n    pass\n",
        "pkg/eye.py": "_SECRET = 1\n",
        "pkg/twice.py": "_TOKEN = 1\n",
    })
    provenance = {"reexport_map": {"_Other": "Other"}, "entries": [
        _entry("__version__", "pkg/gone.py", "variable"),
        _entry("__version__", "pkg/broken.py", "variable"),
        _entry("_hidden", "pkg/x.go", "function"),
        _entry("App.update", "pkg/app.py", "method"),
        _entry("App", "pkg/app.py", "class"),
        _entry("_Impl", "pkg/impl.py", "class", reexported_as="Public"),
        _entry("_Other", "pkg/impl.py", "class"),
        _entry("_SECRET", "pkg/eye.py", "constant"),
        _entry("_TOKEN", "pkg/twice.py", "constant"),
        _entry("_TOKEN", "./pkg/twice.py", "constant"),
        _entry("_TOKEN", "pkg\\twice.py", "constant"),
    ]}
    runner = {"status": "ok",
              "exports": [_export("App", "pkg/app.py", 1), _export("Public", "pkg/impl.py", 1),
                          _export("Other", "pkg/impl.py", 5)],
              "file_issues": [{"file": "pkg/broken.py", "issue": "syntax-errors", "count": 1, "line": 1}]}
    snap = mod.build(root, "Forge", "t", provenance, runner, ["pkg/eye.py"], [])
    statuses = {f["file"]: f["status"] for f in snap["files"]}
    assert (statuses["pkg/gone.py"], statuses["pkg/broken.py"], statuses["pkg/eye.py"]) == (
        "missing", "parse-failed", "read-by-eye")
    assert [(g["name"], g["file"], g["line"], g["export_type"]) for g in snap["extraction_gaps"]] == [
        ("_SECRET", "pkg/eye.py", 1, "constant"), ("_TOKEN", "pkg/twice.py", 1, "constant")]
    # no rule reads a Go file: the entry is named in one warning, never dropped in silence
    assert [w for w in snap["warnings"] if "neither Python nor TS/JS" in w] == [
        "1 map entry the snapshot lacks that no rule can check (in a file neither Python nor TS/JS, a file the "
        "declaration lookup does not read, or a dotted module name), so step 3 may report it removed: "
        "_hidden (pkg/x.go)"]


def test_an_entry_the_lookup_will_not_read_is_named_in_the_warning(tmp_path):
    """A test-named file the declaration lookup skips and a dotted module name have no declaring line it can
    give: each is named in the unchecked warning, never dropped in silence (#687 review)."""
    root = _tree(tmp_path / "src", {"pkg/test_util.py": "_helper = 1\n", "pkg/api/v1/__init__.py": ""})
    provenance = {"entries": [_entry("_helper", "pkg/test_util.py", "variable"),
                              _entry("api.v1", "pkg/api/v1/__init__.py", "module")]}
    snap = mod.build(root, "Forge", "t", provenance, {"status": "ok", "exports": []}, [], [])
    assert snap["extraction_gaps"] == []
    (warning,) = [w for w in snap["warnings"] if "no rule can check" in w]
    assert warning.startswith("2 map entries the snapshot lacks that no rule can check")
    assert warning.endswith("may report them removed: _helper (pkg/test_util.py), api.v1 (pkg/api/v1/__init__.py)")


def test_the_module_rule_is_for_a_module_or_package_entry(tmp_path):
    """A function or class removed from the file named after it is a real
    removal: only a `module` or `package` entry is declared by its file's
    name. An entry with no export_type gives a gap without the key."""
    root = _tree(tmp_path / "src", {
        "pkg/__init__.py": "",
        "pkg/widget.py": "def other():\n    pass\n",
        "pkg/gadget.py": "def other():\n    pass\n",
        "pkg/tools/__init__.py": "",
        "pkg/consts.py": "import os\n\n_LIMIT = 10\n",
    })
    provenance = {"entries": [
        _entry("widget", "pkg/widget.py", "function"),
        _entry("gadget", "pkg/gadget.py", "module"),
        _entry("tools", "pkg/tools/__init__.py", "Package"),
        {"export_name": "_LIMIT", "source_file": "pkg/consts.py", "source_line": 3},
    ]}
    runner = {"status": "ok", "exports": [_export("other", "pkg/widget.py", 1), _export("other", "pkg/gadget.py", 1)]}
    snap = mod.build(root, "Forge", "t", provenance, runner, [], [])
    assert snap["extraction_gaps"] == [{"name": "_LIMIT", "file": "pkg/consts.py", "line": 3, "entry": None}]
    # #1131: the module and the package the map records are exports, their type as the map writes it
    assert [(e["name"], e["type"], e["signature"], e["line"]) for e in snap["exports"] if e["name"] != "other"] == [
        ("gadget", "module", "module pkg.gadget", 1), ("tools", "Package", "module pkg.tools", 1)]


@pytest.mark.parametrize("files,entry,signature", [
    ({"pkg/pipelines/__init__.py": "from .tasks import Task\n"}, ("pipelines", "pkg/pipelines/__init__.py", "module"),
     "module pkg.pipelines"),
    ({"src/utils/index.ts": "export const x = 1;\n"}, ("utils", "src/utils/index.ts", "module"), "module src/utils"),
    ({"src/helpers.ts": "export const y = 1;\n"}, ("helpers", "src/helpers.ts", "MODULE "), "module src/helpers"),
    ({"pkg/io.py": "def read():\n    pass\n"}, ("io", "pkg/io.py", "package"), "module pkg.io"),
], ids=["python-package", "ts-index-module", "ts-module-any-case", "python-module"])
def test_a_module_or_package_gap_is_an_export(tmp_path, files, entry, signature):
    """#1131: the build records a module or package entry its file still
    declares as an export, the signature read from the path (dotted for
    Python, with forward slashes for TS/JS), at line 1, T1-low and read
    from source, with its file's library; the counts and the file's export
    count include it, and no gap is left for a by-eye reader."""
    root = _tree(tmp_path / "src", files)
    name, file, kind = entry
    provenance = {"entries": [_entry(name, file, kind, source_library="lib")]}
    snap = mod.build(root, "Forge", "t", provenance, {"status": "ok", "exports": []}, [], [])
    assert snap["extraction_gaps"] == []
    assert snap["exports"] == [{"name": name, "type": kind, "signature": signature, "file": file, "line": 1,
                                "confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
                                "source_library": "lib"}]
    assert snap["counts"] == {"exports": 1, "by_type": {kind: 1}, "t1": 0, "t1_low": 1}
    assert [(f["file"], f["status"], f["exports"]) for f in snap["files"]] == [(file, "extracted", 1)]
    # the map entry it stands for diffs unchanged
    result = diff_mod.diff_inventories(provenance["entries"], snap["exports"])
    assert (result["removed"], result["added"], result["changed"]) == ([], [], [])


def test_a_module_export_sorts_among_the_runner_exports(tmp_path):
    root = _tree(tmp_path / "src", {"pkg/__init__.py": "def a():\n    pass\n", "pkg/z.py": "def b():\n    pass\n"})
    provenance = {"entries": [_entry("a", "pkg/__init__.py", "function", 1), _entry("pkg", "pkg/__init__.py", "package"),
                              _entry("b", "pkg/z.py", "function", 1)]}
    runner = {"status": "ok", "exports": [_export("a", "pkg/__init__.py", 1), _export("b", "pkg/z.py", 1)]}
    snap = mod.build(root, "Forge", "t", provenance, runner, [], [])
    assert [(e["name"], e["file"]) for e in snap["exports"]] == [
        ("a", "pkg/__init__.py"), ("pkg", "pkg/__init__.py"), ("b", "pkg/z.py")]
    assert [f["exports"] for f in snap["files"]] == [2, 1]
    assert snap["counts"]["exports"] == 3 and snap["extraction_gaps"] == []


@pytest.mark.parametrize("files,entry,line", [
    ({"pkg/__init__.py": "", "pkg/v1/__init__.py": "from .x import y\n\n\n\napi = make_api()\n"},
     ("api", "pkg/v1/__init__.py", "module"), 5),
    ({"types/foo.d.ts": "export declare function foo(): void;\n"}, ("foo", "types/foo.d.ts", "module"), 1),
], ids=["declared-at-line-5", "not-its-files-module"])
def test_a_module_gap_found_elsewhere_stays_a_gap(tmp_path, files, entry, line):
    """#1131 review 1: only a gap at line 1 of the file that is its module
    or package is recorded; one found at a declaration on another line, or
    in a file whose module has another name (`types/foo.d.ts` is `foo.d`),
    stays a gap for the by-eye reader, never the wrong module at line 1."""
    root = _tree(tmp_path / "src", files)
    name, file, kind = entry
    snap = mod.build(root, "Forge", "t", {"entries": [_entry(name, file, kind)]}, {"status": "ok", "exports": []},
                     [], [])
    assert snap["extraction_gaps"] == [{"name": name, "file": file, "line": line, "entry": None, "export_type": kind}]
    assert snap["exports"] == [] and snap["counts"]["exports"] == 0


def test_a_file_an_incomplete_run_left_unread_is_not_checked(tmp_path):
    root = _tree(tmp_path / "src", {"pkg/a.py": "def a():\n    pass\n", "pkg/slow.py": "__version__ = '1'\n"})
    provenance = {"entries": [_entry("a", "pkg/a.py", "function"), _entry("__version__", "pkg/slow.py", "variable")]}
    runner = {"status": "incomplete", "exports": [_export("a", "pkg/a.py", 1)],
              "errors": [{"reason": "time-limit", "files": 1, "first_file": "pkg/slow.py", "detail": "x",
                          "unread": ["pkg/slow.py"]}]}
    snap = mod.build(root, "Forge", "t", provenance, runner, [], [])
    assert [f["status"] for f in snap["files"]] == ["extracted", "unread"]
    assert snap["extraction_gaps"] == []


def test_without_a_runner_a_file_read_by_eye_is_checked(tmp_path):
    """At Quick tier every file is read by eye: an entry the reader left out
    while the file declares it is a gap there too."""
    root = _tree(tmp_path / "src", {"pkg/__init__.py": "__version__ = '1.0'\n\n\ndef run():\n    pass\n"})
    provenance = {"entries": [_entry("__version__", "pkg/__init__.py", "variable"),
                              _entry("run", "pkg/__init__.py", "function", 4)]}
    details = [{"name": "run", "file": "pkg/__init__.py", "line": 4, "type": "function"}]
    snap = mod.build(root, "Quick", "t", provenance, None, ["pkg/__init__.py"], details)
    assert snap["extraction_gaps"] == [{"name": "__version__", "file": "pkg/__init__.py", "line": 1, "entry": None,
                                        "export_type": "variable"}]
    # an unread file is not checked before it is read
    snap = mod.build(root, "Quick", "t", provenance, None, [], [])
    assert snap["extraction_gaps"] == []


def test_the_runners_gaps_are_one_per_name_and_file(tmp_path):
    root = _tree(tmp_path / "src", {"pkg/a.py": ""})
    runner = {"status": "ok", "exports": [], "entry_point_diff": {"extraction_gaps": [
        {"name": "G", "language": "python", "entry": "pkg/__init__.py", "file": "pkg/a.py", "line": 3},
        {"name": "G", "language": "python", "entry": "pkg/sub/__init__.py", "file": "pkg/a.py", "line": 3}]}}
    snap = mod.build(root, "Forge", "t", {"entries": []}, runner, [], [])
    assert snap["extraction_gaps"] == [{"name": "G", "file": "pkg/a.py", "line": 3, "entry": "pkg/__init__.py"}]


@pytest.mark.parametrize("verifier", [
    None, "raise RuntimeError('broken install')\n", "def other():\n    pass\n",
    "def baseline_gaps(*args):\n    return [], []\ndef declared_line(*args):\n    return None\n"],
    ids=["missing", "raises", "no-declared-line", "no-module-name"])
def test_a_verifier_that_cannot_load_is_a_build_error(tmp_path, verifier):
    """The declaration rule is the verifier's: a snapshot helper installed
    without it beside it, with one that fails to load whatever it raises,
    or with one that has no declared_line or (#1131 review 2) no
    _module_name stops with exit 2 and the error JSON instead of listing
    no baseline gap."""
    alone = tmp_path / "scripts"
    alone.mkdir()
    for name in ("skf-extraction-snapshot.py", "skf-load-provenance.py"):
        shutil.copy2(SCRIPTS / name, alone / name)
    if verifier is not None:
        _write(alone / "skf-verify-provenance-completeness.py", verifier)
    root = _tree(tmp_path / "src", COGNEE)
    provenance = _write(tmp_path / "provenance-map.json", COGNEE_MAP)
    runner = _write(tmp_path / "extraction.json", COGNEE_RUNNER)
    out = tmp_path / "extraction-snapshot.json"
    result = subprocess.run([sys.executable, str(alone / "skf-extraction-snapshot.py"), "build", "--source-root",
                             str(root), "--tier", "Forge", "--date", "t", "--provenance-map", str(provenance),
                             "--extraction", str(runner), "-o", str(out)],
                            capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    line = json.loads(result.stdout)
    assert (result.returncode, line["status"]) == (2, "error"), result.stdout + result.stderr
    assert line["error"].startswith("cannot load skf-verify-provenance-completeness.py beside "
                                    "skf-extraction-snapshot.py: ")
    assert "Traceback" not in result.stderr and not out.exists()


# --------------------------------------------------------------------------
# Public surface: a public-api skill's exports marked by the shared rule (#702)
# --------------------------------------------------------------------------

INVENTORY = SCRIPTS / "skf-extraction-inventory.py"
_inv_spec = importlib.util.spec_from_file_location("skf_extraction_inventory_for_snapshot", INVENTORY)
inventory = importlib.util.module_from_spec(_inv_spec)
_inv_spec.loader.exec_module(inventory)

# A public-api package: its entry point re-exports `connect` and exports `logger`, a name no recipe finds (read by
# eye at the gap); `helper`, `legacy` and `main` are internal, and the map, written before create-skill kept a
# public-api map to the surface, holds `legacy`. The runner names `main`'s file with a backslash and gives its
# language, the only way to know an extension-less file's family.
SURFACE_TREE = {"pkg/__init__.py": "", "pkg/client.py": "", "pkg/util.py": "", "pkg/cli": ""}
SURFACE_MAP = {"entries": [
    _entry("connect", "pkg/client.py", "function"), _entry("legacy", "pkg/util.py", "function", 9),
    _entry("run", "pkg/cli", "function"), _entry("version", "pkg/__init__.py", "function")]}
SURFACE_RUNNER = {
    "status": "ok", "scope": {"type": None, "include": []},
    "exports": [_export("connect", "pkg/client.py", 1, language="python"),
                _export("helper", "pkg/util.py", 5, language="python"),
                _export("legacy", "pkg/util.py", 9, language="python"),
                _export("main", "pkg\\cli", 2, language="python")],
    "entry_points": {"status": "barrel", "by_language": {"python": "barrel"}, "unresolved": []},
    "entry_point_diff": {
        "public": [{"name": "connect", "language": "python", "entry": "pkg/__init__.py", "via": "re-export",
                    "from": ".client", "local": None, "file": "pkg/client.py", "line": 1}],
        "internal": [{"name": n, "language": "python", "source_file": f, "source_line": 1}
                     for n, f in (("helper", "pkg/util.py"), ("legacy", "pkg/util.py"), ("main", "pkg/cli"))],
        "extraction_gaps": [{"name": "logger", "language": "python", "entry": "pkg/__init__.py",
                             "file": "pkg/__init__.py", "line": 3}],
        "outside_scope": []},
}
LOGGER = {"name": "logger", "file": "pkg/__init__.py", "line": 3, "type": "variable", "signature": "logger = log()"}


def _surface_build(tmp_path, runner=SURFACE_RUNNER, scope_type="public-api", tier="Forge", details=(LOGGER,)):
    root = _tree(tmp_path / "src", SURFACE_TREE)
    return mod.build(root, tier, "t", SURFACE_MAP, runner, [], list(details), scope_type=scope_type)


def test_public_api_marks_each_export_by_the_public_surface_rule(tmp_path):
    """The marks are the rule's: a re-exported name and a gap read by eye (no language: the family of its file's
    extension) are public, the rest of a barrel family is not, an extension-less file is marked by the language
    the runner gave its export, and every export stays, a map-held one off the surface (`legacy`) too."""
    snap = _surface_build(tmp_path)
    assert {e["name"]: e["public"] for e in snap["exports"]} == {
        "connect": True, "helper": False, "legacy": False, "logger": True, "main": False}
    assert snap["public_surface"] == {"problem": None, "marked_not_public": 3}
    # the marks change nothing else: the same exports, counts and statuses as a build with no scope type
    plain = _surface_build(tmp_path, scope_type=None)
    assert plain["public_surface"] is None
    for export in snap["exports"]:
        export.pop("public")
    snap["public_surface"] = None
    assert snap == plain
    assert plain["counts"] == {"exports": 5, "by_type": {"function": 4, "variable": 1}, "t1": 4, "t1_low": 1}


def test_a_family_with_no_barrel_is_left_unmarked_and_reads_as_added(tmp_path):
    """The rule marks only a family whose entry points are a barrel: a Go export beside the Python barrel carries
    no `public` key, so the not-public count is the barrel family's and the diff still reports it added."""
    tree = {**SURFACE_TREE, "pkg/ext.go": ""}
    provenance = {"entries": [*SURFACE_MAP["entries"], _entry("Old", "pkg/ext.go", "function")]}
    runner = {**SURFACE_RUNNER, "exports": [*SURFACE_RUNNER["exports"], _export("Old", "pkg/ext.go", 1, language="go"),
                                            _export("Fresh", "pkg/ext.go", 5, language="go")]}
    snap = mod.build(_tree(tmp_path / "src", tree), "Forge", "t", provenance, runner, [], [LOGGER],
                     scope_type="public-api")
    by_name = {e["name"]: e for e in snap["exports"]}
    assert "public" not in by_name["Fresh"] and "public" not in by_name["Old"]
    assert snap["public_surface"] == {"problem": None, "marked_not_public": 3}
    result = diff_mod.diff_inventories(provenance["entries"], snap["exports"])
    assert [a["name"] for a in result["added"]] == ["Fresh", "logger"]
    assert [n["name"] for n in result["not_public"]] == ["helper", "main"]


def test_a_module_record_is_marked_like_any_export(tmp_path):
    """#1131: the build marks the module records it adds by the same rule:
    `client` is no name the barrel exports, so it is marked not public, and
    counted, yet it pairs with its map entry and the diff reports nothing."""
    provenance = {"entries": [*SURFACE_MAP["entries"], _entry("client", "pkg/client.py", "module")]}
    snap = mod.build(_tree(tmp_path / "src", SURFACE_TREE), "Forge", "t", provenance, SURFACE_RUNNER, [], [LOGGER],
                     scope_type="public-api")
    (client,) = [e for e in snap["exports"] if e["name"] == "client"]
    assert (client["signature"], client["public"]) == ("module pkg.client", False)
    assert snap["public_surface"] == {"problem": None, "marked_not_public": 4}
    result = diff_mod.diff_inventories(provenance["entries"], snap["exports"])
    assert "client" not in {r["name"] for bucket in ("added", "removed", "changed", "not_public")
                            for r in result[bucket]}


@pytest.mark.parametrize("scope_type", [None, "full-library", "component-library", "specific-modules"])
def test_any_other_scope_type_marks_nothing(tmp_path, scope_type):
    snap = _surface_build(tmp_path, scope_type=scope_type)
    assert snap["public_surface"] is None
    assert not any("public" in e for e in snap["exports"])


def _no_surface(case: str) -> dict | None:
    if case == "quick":
        return None
    if case == "no-ast-grep":
        return {"status": "no-ast-grep", "exports": [], "scope": {"type": None},
                "entry_points": {"status": None, "by_language": {}, "unresolved": []}, "entry_point_diff": None}
    runner = json.loads(json.dumps(SURFACE_RUNNER))
    error = {"reason": "time-limit", "files": 1, "first_file": "pkg/util.py", "detail": "x", "unread": []}
    if case == "incomplete":
        runner.update(status="incomplete", errors=[error])
    elif case == "errors":
        runner["errors"] = [error]
    else:
        runner["entry_points"]["unresolved"] = [{"entry": "pkg/__init__.py", "name": "gone", "from": ".gone",
                                                 "file": None}]
    return runner


@pytest.mark.parametrize("case", ["quick", "no-ast-grep", "incomplete", "errors", "unresolved"])
def test_with_no_surface_nothing_is_marked_and_the_rule_says_why(tmp_path, case):
    """No runner JSON (Quick tier), a runner that could not run, an incomplete run, one with errors, or an entry
    point the runner could not trace: the rule reads no surface, so every export is kept unmarked (step 3 then
    reports each one the map lacks as added), and `public_surface.problem` is the rule's own reason."""
    runner = _no_surface(case)
    snap = _surface_build(tmp_path, runner=runner, tier="Quick" if case == "quick" else "Forge")
    assert not any("public" in e for e in snap["exports"])
    _surface, problem = inventory.public_surface({**(runner or {}), "scope": {"type": "public-api"}})
    assert problem and snap["public_surface"] == {"problem": problem, "marked_not_public": 0}
    if case in ("quick", "no-ast-grep"):
        assert problem.startswith("the recipe runner gave no entry-point diff")


def test_the_build_line_carries_the_public_surface(tmp_path):
    """Step 2 reads the surface state from the line it prints; the scope type compares in any case."""
    root = _tree(tmp_path / "src", SURFACE_TREE)
    provenance = _write(tmp_path / "provenance-map.json", SURFACE_MAP)
    runner = _write(tmp_path / "extraction.json", SURFACE_RUNNER)
    details = _write(tmp_path / "export-details-1.json", {"files": [], "exports": [LOGGER]})
    out = tmp_path / "extraction-snapshot.json"
    base = ["build", "--source-root", str(root), "--tier", "Forge", "--date", "t", "--provenance-map", str(provenance),
            "--details", str(details), "-o", str(out)]
    code, line = _run(*base, "--extraction", str(runner), "--scope-type", "Public-API")
    assert (code, line["public_surface"]) == (0, {"problem": None, "marked_not_public": 3})
    assert json.loads(out.read_text(encoding="utf-8"))["public_surface"] == line["public_surface"]
    # Quick tier: no runner JSON, so the rule's own problem, and no mark
    code, line = _run(*base, "--scope-type", "public-api")
    assert code == 0 and line["public_surface"]["problem"].startswith("the recipe runner gave no entry-point diff")
    assert not any("public" in e for e in json.loads(out.read_text(encoding="utf-8"))["exports"])
    code, line = _run(*base, "--extraction", str(runner))
    assert (code, line["public_surface"]) == (0, None)


def test_only_public_api_loads_the_inventory_helper(tmp_path):
    """A snapshot helper installed without skf-extraction-inventory.py beside it builds any other scope type as
    before; a public-api build cannot mark without the rule, so it stops with exit 2 and the error JSON."""
    alone = tmp_path / "scripts"
    alone.mkdir()
    for name in ("skf-extraction-snapshot.py", "skf-load-provenance.py", "skf-verify-provenance-completeness.py"):
        shutil.copy2(SCRIPTS / name, alone / name)
    root = _tree(tmp_path / "src", SURFACE_TREE)
    provenance = _write(tmp_path / "provenance-map.json", SURFACE_MAP)
    runner = _write(tmp_path / "extraction.json", SURFACE_RUNNER)
    out = tmp_path / "extraction-snapshot.json"
    for scope_type, code in (("component-library", 0), ("public-api", 2)):
        result = subprocess.run([sys.executable, str(alone / "skf-extraction-snapshot.py"), "build", "--source-root",
                                 str(root), "--tier", "Forge", "--date", "t", "--provenance-map", str(provenance),
                                 "--extraction", str(runner), "--scope-type", scope_type, "-o", str(out)],
                                capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        line = json.loads(result.stdout)
        assert result.returncode == code, result.stdout + result.stderr
        if code:
            assert line["error"].startswith("cannot load skf-extraction-inventory.py beside skf-extraction-snapshot.py")
        else:
            assert line["public_surface"] is None


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


# --------------------------------------------------------------------------
# relocation-candidates: step 3's search for a removed name elsewhere (#1131)
# --------------------------------------------------------------------------


def _git_tree(root: Path, files: dict[str, str]) -> Path:
    """A git work tree at `root` whose files are all tracked."""
    _tree(root, files)
    for args in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True, timeout=60)
    return root


REMOVED = {"added": [], "changed": [], "moved": [], "removed": [
    {"name": "parse", "file": "pkg/a.py", "line": 9}, {"name": "gone", "file": "pkg/a.py", "line": 20},
    {"name": "parse", "file": "pkg/b.py", "line": 2}]}


def _candidates(tmp_path: Path, root: Path, diff: dict = REMOVED, scan: list | None = None, *flags: str):
    diff_file = _write(tmp_path / "data" / "structural-diff.json", diff)
    scan_file = _write(tmp_path / "data" / "scan-files.json", ["a.py"] if scan is None else scan)
    out = tmp_path / "data" / "relocation-candidates.json"
    code, line = _run("relocation-candidates", "--diff", str(diff_file), "--source-root", str(root),
                      "--scan-list", str(scan_file), *flags, "-o", str(out))
    return code, line, out


def test_relocation_candidates_lists_the_files_outside_the_scan_list(tmp_path):
    """One git grep over a subfolder of a repository: the files that hold a
    removed name as a word, relative to the source root, sorted, less the
    scan list's; a longer word that holds the name and a file outside the
    root are no candidates."""
    repo = _git_tree(tmp_path / "repo", {
        "lib/a.py": "def parse():\n    pass\n",
        "lib/sub/x.py": "from ..a import parse\n",
        "lib/z.py": "parser = None\n",
        "other/y.py": "parse = 1\n",
    })
    code, line, out = _candidates(tmp_path, repo / "lib")
    assert (code, line) == (0, {"status": "ok", "output": str(out), "names": 2, "candidates": 1,
                                "searched_with": "git grep"})
    assert json.loads(out.read_text(encoding="utf-8")) == ["sub/x.py"]
    # a second name's file sorts in among the first's
    _git_tree(repo, {"lib/sub/w.py": "x = 1  # gone\n"})
    code, line, out = _candidates(tmp_path, repo / "lib")
    assert (code, line["candidates"]) == (0, 2)
    assert json.loads(out.read_text(encoding="utf-8")) == ["sub/w.py", "sub/x.py"]


def test_relocation_candidates_ignore_a_full_name_setting(tmp_path):
    """#1131 review 1: with `grep.fullName` set in the repository, git grep
    would print paths from the repository root; the helper asks for paths
    relative to the source root, so the scan list's drop still holds."""
    repo = _git_tree(tmp_path / "repo", {"lib/a.py": "def parse():\n    pass\n", "lib/sub/x.py": "parse\n"})
    subprocess.run(["git", "-C", str(repo), "config", "grep.fullName", "true"], capture_output=True, check=True,
                   timeout=60)
    code, line, out = _candidates(tmp_path, repo / "lib")
    assert (code, line["candidates"]) == (0, 1), line
    assert json.loads(out.read_text(encoding="utf-8")) == ["sub/x.py"]


@pytest.mark.parametrize("returncode", [2, 128, -9])
def test_a_git_grep_that_ends_other_than_0_or_1_fails(tmp_path, monkeypatch, returncode):
    """A git grep killed by a signal (a negative code) or one that errs is
    a failed search, never a partial list."""
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, returncode, b"sub/x.py\0", b"fatal: stopped\n")

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(mod.SnapshotError, match=rf"^git grep failed in .* \(exit {returncode}\): fatal: stopped$"):
        mod.relocation_candidates(REMOVED, tmp_path.resolve(), [], ccc=False)
    assert seen[0][:5] == ["git", "-C", str(tmp_path.resolve()), "grep", "--no-full-name"]


def test_relocation_candidates_without_a_removed_name_searches_nothing(tmp_path):
    """No removed name writes [] without a search, so a folder that is not
    a repository is no error then."""
    plain = _tree(tmp_path / "plain", {"a.py": "parse = 1\n"})
    code, line, out = _candidates(tmp_path, plain, {**REMOVED, "removed": []})
    assert (code, line["names"], line["candidates"]) == (0, 0, 0)
    assert json.loads(out.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("case", ["not-a-repo", "no-root", "bad-scan-list", "no-ccc-index"])
def test_a_relocation_search_that_cannot_run_writes_nothing(tmp_path, case):
    plain = _tree(tmp_path / "plain", {"a.py": "parse = 1\n"})
    # ccc's user settings folder holds no settings.yml: no index root
    _write(tmp_path / ".cocoindex_code" / "global_settings.yml", "")
    flags = ("--ccc",) if case == "no-ccc-index" else ()
    root = tmp_path / "absent" if case == "no-root" else plain
    scan = {"x": 1} if case == "bad-scan-list" else None
    code, line, out = _candidates(tmp_path, root, REMOVED, scan, *flags)
    assert (code, line["status"]) == (2, "error"), line
    assert not out.exists()
    expected = {"not-a-repo": "git grep failed in ", "no-root": "source root not found: ",
                "bad-scan-list": "scan list ", "no-ccc-index": "ccc search failed: no .cocoindex_code index at or above "}
    assert line["error"].startswith(expected[case]), line


def test_ccc_results_are_rebased_onto_the_source_root(tmp_path, monkeypatch):
    """--ccc runs one search per name in the source root; ccc names each
    file from its index folder, here above the source root, so a path is
    rebased onto the root and one outside it is dropped."""
    index = tmp_path / "project"
    _write(index / ".cocoindex_code" / "settings.yml", "")
    # a folder named like an index, without ccc's settings.yml, is none
    _write(index / "pkg" / ".cocoindex_code" / "global_settings.yml", "")
    root = _tree(index / "pkg" / "src", {"a.py": ""})
    searched = []

    def search(name, where):
        searched.append((name, where))
        return {"gone": [{"file_path": "pkg/src/util/moved.py"}, {"file_path": "docs/gone.md"}],
                "parse": [{"file_path": "pkg/src/a.py"}, {"file_path": "pkg\\src\\io\\parse.py"},
                          {"file_path": "pkg/src/util/moved.py"}, {"file_path": "../elsewhere.py"}, {}]}[name]

    monkeypatch.setattr(mod, "_ccc_search", search)
    candidates, names = mod.relocation_candidates(REMOVED, root.resolve(), ["a.py"], ccc=True)
    assert (candidates, names) == (["io/parse.py", "util/moved.py"], 2)
    assert searched == [("gone", root.resolve()), ("parse", root.resolve())]


def _fake_ccc(tmp_path: Path, response: str, code: int, stderr: str = "") -> tuple[dict, Path]:
    """A `ccc` on PATH that records each call's argv and working folder,
    prints `response` (nothing when it is empty) and `stderr` on stderr,
    and exits `code`; the environment to run it with."""
    bin_dir = tmp_path / "bin"
    log = tmp_path / "ccc-calls.txt"
    out = f"printf '%s\\n' '{response}'\n" if response else ""
    err = f"printf '%s\\n' '{stderr}' >&2\n" if stderr else ""
    _write(bin_dir / "ccc", f"#!/bin/sh\nprintf '%s|' \"$@\" >> '{log}'\npwd -P >> '{log}'\n"
                            f"{out}{err}exit {code}\n")
    (bin_dir / "ccc").chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}, log


def _candidates_with(env: dict, tmp_path: Path, root: Path) -> tuple[int, dict, Path]:
    diff_file = _write(tmp_path / "data" / "structural-diff.json", REMOVED)
    scan_file = _write(tmp_path / "data" / "scan-files.json", ["a.py"])
    out = tmp_path / "data" / "relocation-candidates.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "relocation-candidates", "--diff", str(diff_file),
                             "--source-root", str(root), "--scan-list", str(scan_file), "--ccc", "-o", str(out)],
                            capture_output=True, text=True, encoding="utf-8", timeout=120, check=False, env=env)
    return result.returncode, json.loads(result.stdout), out


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
def test_ccc_search_runs_once_per_name_and_its_json_is_read(tmp_path):
    """#1131 review 1: the real call, against a `ccc` that prints what
    `ccc search --json` prints: one `search --json --limit 5 NAME` per
    name, run in the source root, each `file_path` rebased from the index
    root above it."""
    index = _tree(tmp_path / "project", {".cocoindex_code/settings.yml": ""})
    root = _tree(index / "pkg" / "src", {"a.py": ""})
    env, log = _fake_ccc(tmp_path, '{"success": true, "results": [{"file_path": "pkg/src/util/moved.py", '
                                   '"score": 0.9}, {"file_path": "pkg/src/a.py"}, {"file_path": "docs/x.md"}], '
                                   '"message": null}', 0)
    code, line, out = _candidates_with(env, tmp_path, root)
    assert (code, line) == (0, {"status": "ok", "output": str(out), "names": 2, "candidates": 1,
                                "searched_with": "ccc"}), line
    assert json.loads(out.read_text(encoding="utf-8")) == ["util/moved.py"]
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls == [f"search|--json|--limit|5|gone|{root.resolve()}", f"search|--json|--limit|5|parse|{root.resolve()}"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
def test_a_ccc_search_that_fails_writes_nothing(tmp_path):
    index = _tree(tmp_path / "project", {".cocoindex_code/settings.yml": ""})
    root = _tree(index / "src", {"a.py": ""})
    env, log = _fake_ccc(tmp_path, '{"success": false, "results": [], "message": "index is still building"}', 1)
    code, line, out = _candidates_with(env, tmp_path, root)
    assert (code, line["status"]) == (2, "error"), line
    assert line["error"] == "ccc search failed for gone (exit 1): index is still building"
    assert not out.exists() and len(log.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
def test_a_ccc_search_that_prints_no_json_fails_with_its_stderr(tmp_path):
    """#1131 review 2: ccc's CLI fails with nothing on stdout and `Error:`
    on stderr when its daemon cannot start; the helper names that line."""
    index = _tree(tmp_path / "project", {".cocoindex_code/settings.yml": ""})
    root = _tree(index / "src", {"a.py": ""})
    env, _ = _fake_ccc(tmp_path, "", 1, "Error: daemon failed to start")
    code, line, out = _candidates_with(env, tmp_path, root)
    assert (code, line) == (2, {"status": "error",
                                "error": "ccc search failed for gone (exit 1): Error: daemon failed to start"}), line
    assert not out.exists()


@pytest.mark.parametrize("raised,error", [
    (subprocess.TimeoutExpired(["git"], 600), r"^git grep failed in .*: no answer in 600s$"),
    (FileNotFoundError("git"), r"^cannot run git: git$"),
], ids=["no-answer", "no-git"])
def test_a_git_grep_that_hangs_or_cannot_start_fails(tmp_path, monkeypatch, raised, error):
    """#1131 review 2: a git grep with no answer is a failed search, and no
    git executable is `cannot run git`. #1131 review 3: the search runs
    under SEARCH_TIMEOUT."""
    def run(argv, **kwargs):
        assert kwargs.get("timeout") == mod.SEARCH_TIMEOUT
        raise raised

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(mod.SnapshotError, match=error):
        mod.relocation_candidates(REMOVED, tmp_path.resolve(), [], ccc=False)


def test_a_ccc_search_that_hangs_fails(tmp_path, monkeypatch):
    """#1131 review 3: each ccc search runs under SEARCH_TIMEOUT, and one
    with no answer (ccc waits for its index to build) is a failed search,
    not `cannot run ccc`."""
    root = _tree(tmp_path / "src", {"a.py": "", ".cocoindex_code/settings.yml": ""})
    monkeypatch.setattr(mod.shutil, "which", lambda exe: "ccc")

    def run(argv, **kwargs):
        assert kwargs.get("timeout") == mod.SEARCH_TIMEOUT
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(mod.SnapshotError, match=r"^ccc search failed for gone: no answer in 600s$"):
        mod.relocation_candidates(REMOVED, root.resolve(), [], ccc=True)


def test_removed_names_are_each_name_once_and_never_a_line_break():
    """#1131 review 3: a name holding a line break would be two git grep
    patterns, one maybe empty, which matches every line; a blank name or one
    that is not a string is no name."""
    diff = {"removed": [{"name": "parse"}, {"name": "gone"}, {"name": "parse"}, {"name": "two\nlines"},
                        {"name": "cr\r"}, {"name": "  "}, {"name": 7}, {"name": None}, "parse", {}]}
    assert mod.removed_names(diff) == ["gone", "parse"]


def test_ccc_at_the_index_root_and_its_failures(tmp_path, monkeypatch):
    root = _tree(tmp_path / "src", {"a.py": "", ".cocoindex_code/settings.yml": ""})
    monkeypatch.setattr(mod, "_ccc_search", lambda name, where: [{"file_path": f"lib/{name}.py"}])
    assert mod.relocation_candidates(REMOVED, root.resolve(), [], ccc=True) == (["lib/gone.py", "lib/parse.py"], 2)
    monkeypatch.undo()
    monkeypatch.setattr(mod.shutil, "which", lambda exe: None)
    with pytest.raises(mod.SnapshotError, match="^cannot run ccc: "):
        mod.relocation_candidates(REMOVED, root.resolve(), [], ccc=True)


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


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_the_runner_leaves_dunders_and_modules_to_the_baseline_gaps(tmp_path):
    """#680 and #682 end to end: the runner leaves out `__version__`, an
    alias, a module and an underscore name the map records, which the build
    lists as gaps with their map types; read by eye at those lines, they
    are held, and the diff reports no removal and no kind change for the
    by-eye `async_function` the runner records as a `function`, while the
    name the map records as a `variable` and the source now declares with
    a `def` is a real kind change."""
    root = _tree(tmp_path / "src", {
        "pkg/__init__.py": ("from .version import get_version\nfrom .api import session\n"
                            "from .api.visualize import visualize_graph as visualize\n\n__version__ = get_version()\n"),
        "pkg/version.py": "def get_version():\n    return '1'\n\n\ndef _registry():\n    return {}\n",
        "pkg/api/__init__.py": "",
        "pkg/api/session.py": "def get_session():\n    pass\n",
        "pkg/api/visualize.py": "async def visualize_graph(path: str | None = None):\n    pass\n",
    })
    by_eye = {"confidence": "T1-low", "extraction_method": "source-read"}
    provenance = _write(tmp_path / "forge" / "provenance-map.json", {"entries": [
        _entry("__version__", "pkg/__init__.py", "variable", 5, **by_eye),
        _entry("visualize", "pkg/__init__.py", "alias", 3, **by_eye),
        _entry("session", "pkg/api/session.py", "module", **by_eye),
        _entry("visualize_graph", "pkg/api/visualize.py", "async_function", params=["path: str | None = None"],
               **by_eye),
        _entry("get_version", "pkg/version.py", "function", confidence="T1", extraction_method="ast-grep"),
        _entry("_registry", "pkg/version.py", "variable", 5, **by_eye),
    ]})
    data = tmp_path / "forge" / ".skf-audit" / "20260101-000000"
    data.mkdir(parents=True)
    scan, extraction = data / "scan-files.json", data / "extraction.json"
    assert _run("scan-list", str(provenance), "-o", str(scan))[0] == 0
    runner = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(root),
                             "--files-from", str(scan), "--head-cap", "0", "-o", str(extraction)],
                            capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert runner.returncode == 0, runner.stderr
    snapshot = tmp_path / "forge" / "extraction-snapshot.json"
    build = ["build", "--source-root", str(root), "--tier", "Forge", "--date", "t", "--provenance-map",
             str(provenance), "--extraction", str(extraction), "-o", str(snapshot)]
    code, line = _run(*build)
    assert code == 0 and line["complete"] is True
    gaps = line["extraction_gaps"]
    assert [(g["name"], g["file"], g["line"], g["export_type"]) for g in gaps] == [
        ("__version__", "pkg/__init__.py", 5, "variable"), ("visualize", "pkg/__init__.py", 3, "alias"),
        ("_registry", "pkg/version.py", 5, "variable")]
    # #1131: the build records the module itself, as a by-eye reader would have
    (session,) = [e for e in json.loads(snapshot.read_text(encoding="utf-8"))["exports"] if e["name"] == "session"]
    assert session == {"name": "session", "type": "module", "signature": "module pkg.api.session",
                       "file": "pkg/api/session.py", "line": 1, "confidence": "T1-low",
                       "extraction_method": "source-read", "ast_node_type": None}
    # read by eye as re-index.md item 3 says: the map's kind while the declaration keeps it, else the kind it
    # has now; the import line for a renaming alias
    read = {
        "__version__": ("variable", "__version__ = get_version()"),
        "visualize": ("alias", "from .api.visualize import visualize_graph as visualize"),
        "_registry": ("function", "def _registry():"),
    }
    details = _write(data / "export-details-1.json", {"files": [], "exports": [
        {"name": g["name"], "file": g["file"], "line": g["line"], "type": read[g["name"]][0],
         "signature": read[g["name"]][1], "confidence": "T1-low", "extraction_method": "source-read",
         "ast_node_type": None} for g in gaps]})
    code, line = _run(*build, "--details", str(details))
    assert (code, line["extraction_gaps"]) == (0, [])
    diff = subprocess.run([sys.executable, str(DIFF), str(provenance), str(snapshot)], capture_output=True,
                          text=True, encoding="utf-8", timeout=120, check=False)
    result = json.loads(diff.stdout)
    # nothing reads as removed, the by-eye async kind is the runner's function, and the real kind change shows
    assert result["removed"] == []
    assert [(c["name"], c["field"], c["baseline_value"], c["current_value"]) for c in result["changed"]] == [
        ("_registry", "type", "variable", "function")]
    assert [a["name"] for a in result["added"]] == ["get_session"]
    assert {"transform": "export-type", "count": 1} in result["applied_transforms"]


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_a_public_api_audit_reports_no_internal_export_as_added(tmp_path):
    """#702 end to end: the runner and the build with --scope-type public-api, then the diff. An internal export
    the map lacks is listed off the surface, not added; one the map holds stays unchanged; a mapped export moved
    into an internal file is a move. Without the flag the same internal export reads as added, as before."""
    root = _tree(tmp_path / "src", {
        "pkg/__init__.py": "from .client import connect\n",
        "pkg/client.py": "def connect(url: str) -> None:\n    pass\n",
        "pkg/util.py": ("def helper(x: int) -> int:\n    return x\n\n\ndef legacy() -> None:\n    pass\n\n\n"
                        "def relocated() -> None:\n    pass\n"),
    })
    provenance = _write(tmp_path / "forge" / "provenance-map.json", {"entries": [
        {"export_name": name, "export_type": "function", "source_file": file, "source_line": line,
         "signature": signature, "confidence": "T1", "extraction_method": "ast-grep"}
        for name, file, line, signature in (
            ("connect", "pkg/client.py", 1, "def connect(url: str) -> None:"),
            ("legacy", "pkg/util.py", 5, "def legacy() -> None:"),
            ("relocated", "pkg/old.py", 1, "def relocated() -> None:"))]})
    data = tmp_path / "forge" / ".skf-audit" / "20260101-000000"
    data.mkdir(parents=True)
    scan = data / "scan-files.json"
    assert _run("scan-list", str(provenance), "-o", str(scan))[0] == 0
    results = {}
    for flag in (["--scope-type", "public-api"], []):
        extraction, snapshot = data / f"extraction{len(flag)}.json", tmp_path / "forge" / f"snapshot{len(flag)}.json"
        runner = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(root),
                                 "--files-from", str(scan), "--head-cap", "0", *flag, "-o", str(extraction)],
                                capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
        assert runner.returncode == 0, runner.stderr
        code, line = _run("build", "--source-root", str(root), "--tier", "Forge", "--date", "t", "--provenance-map",
                          str(provenance), "--extraction", str(extraction), *flag, "-o", str(snapshot))
        assert code == 0 and line["complete"] is True
        diff = subprocess.run([sys.executable, str(DIFF), str(provenance), str(snapshot)], capture_output=True,
                              text=True, encoding="utf-8", timeout=120, check=False)
        results[bool(flag)] = (line, json.loads(diff.stdout))
    line, result = results[True]
    assert line["public_surface"] == {"problem": None, "marked_not_public": 3}
    assert (result["added"], [e["name"] for e in result["not_public"]], result["removed"]) == ([], ["helper"], [])
    assert [(m["name"], m["previous_file"], m["current_file"]) for m in result["moved"]] == [
        ("relocated", "pkg/old.py", "pkg/util.py")]
    assert result["summary"]["unchanged"] == 3 and result["changed"] == []
    line, result = results[False]
    assert line["public_surface"] is None
    assert ([e["name"] for e in result["added"]], result["not_public"]) == (["helper"], [])


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_a_typescript_barrel_off_the_scan_list_still_marks_the_surface(tmp_path):
    """#702: the map cites only the file that defines the exports; the package's barrel (package.json `main` ->
    src/index.ts) is not on the scan list, yet the runner's entry-point trace marks the re-exported `connect`
    public and `helper` not, so the diff lists `helper` off the surface."""
    root = _tree(tmp_path / "src", {
        "pkg/package.json": '{"name": "pkg", "version": "1.0.0", "main": "src/index.ts"}\n',
        "pkg/src/index.ts": 'export { connect } from "./client";\n',
        "pkg/src/client.ts": ("export function connect(url: string): void {}\n\n"
                              "export function helper(x: number): number {\n  return x;\n}\n"),
    })
    provenance = _write(tmp_path / "forge" / "provenance-map.json", {"entries": [
        {"export_name": "connect", "export_type": "function", "source_file": "pkg/src/client.ts", "source_line": 1,
         "confidence": "T1", "extraction_method": "ast-grep"}]})
    data = tmp_path / "forge" / ".skf-audit" / "20260101-000000"
    data.mkdir(parents=True)
    scan, extraction = data / "scan-files.json", data / "extraction.json"
    assert _run("scan-list", str(provenance), "-o", str(scan))[0] == 0
    assert json.loads(scan.read_text(encoding="utf-8")) == ["pkg/src/client.ts"]
    runner = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(root),
                             "--files-from", str(scan), "--head-cap", "0", "--scope-type", "public-api",
                             "-o", str(extraction)],
                            capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert runner.returncode == 0, runner.stderr
    snapshot = tmp_path / "forge" / "extraction-snapshot.json"
    code, line = _run("build", "--source-root", str(root), "--tier", "Forge", "--date", "t", "--provenance-map",
                      str(provenance), "--extraction", str(extraction), "--scope-type", "public-api",
                      "-o", str(snapshot))
    assert (code, line["complete"], line["public_surface"]) == (0, True, {"problem": None, "marked_not_public": 1})
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    assert {e["name"]: e["public"] for e in snap["exports"]} == {"connect": True, "helper": False}
    diff = subprocess.run([sys.executable, str(DIFF), str(provenance), str(snapshot)], capture_output=True,
                          text=True, encoding="utf-8", timeout=120, check=False)
    result = json.loads(diff.stdout)
    assert (diff.returncode, result["added"], [n["name"] for n in result["not_public"]]) == (0, [], ["helper"])
