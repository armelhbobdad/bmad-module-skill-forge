#!/usr/bin/env python3
"""Unit and prose tests for src/skf-audit-skill/scripts/render-drift-tables.py.

#589 (audit part, BMad Builder determinism-5): step 3 §5 and step 5 §3 had
the model copy every row of their drift tables from the JSON the step saved,
where a row can be dropped or mis-matched as in a hand diff. The renderer
prints them from structural-diff.json, file-drift.json and severity.json,
with a mechanical rollup, and the two steps call it once each. These tests:
- feed the renderer what skf-structural-diff.py and skf-severity-classify.py
  really save, so the tables keep up with the helpers' fields;
- check every count comes from the JSON's summary, never from the rows;
- check the rollup: 10 or more rows of one kind that share a file, or,
  for removed rows, a directory (never the top level), become one row;
  added rows across one directory, and the rows it may not touch (moved,
  changed, ambiguous, a changed signature), never do;
- check a saved file-drift.json it cannot read skips only its own table;
- check the cells: a pipe, a backtick or an underscore in a signature or a
  path cannot break the table or the markdown;
- run the steps' own commands, and check the hand-filled templates are gone.

Step 5b determinism-1: step 6 (report.md section 2) had the model open the
whole snapshot and type its Out-of-Scope New Public API rows, which
skf-provenance-gap-dispatch.py then parses back for update-skill. The
`outside-scope` command prints them from the snapshot step 2 wrote, and
these tests check that update-skill reads back every path it prints, that
it prints nothing when there is nothing outside the scope, and that step 6
runs it and keeps no hand-filled row.

#1130: step 4's Semantic Drift tables, step 5a's Documentation Drift
section, step 1c's Constituent Freshness table and step 6's Provenance table
were typed by hand from saved JSON (or the report's frontmatter), with no
cell escaping, so a `|` in a URL, a reason or a path broke the table, and
step 4 wrote five tables, empty ones too. The `semantic`, `doc-drift`,
`constituents` and `provenance` commands print them, and these tests check
each against the matrix of its spec, run each stage's command as written on
saved files and check each stage keeps no hand-filled row.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "src" / "skf-audit-skill"
SCRIPT = AUDIT / "scripts" / "render-drift-tables.py"
STRUCTURAL = AUDIT / "references" / "structural-diff.md"
SEVERITY = AUDIT / "references" / "severity-classify.md"
REPORT = AUDIT / "references" / "report.md"
INIT = AUDIT / "references" / "init.md"
SEMANTIC = AUDIT / "references" / "semantic-diff.md"
DOC_DRIFT = AUDIT / "references" / "doc-drift.md"
COMPOSE = AUDIT / "references" / "constituent-freshness.md"
TIERS = REPO / "src" / "knowledge" / "progressive-capability.md"
TEMPLATE = AUDIT / "assets" / "drift-report-template.md"
SCRIPTS = REPO / "src" / "shared" / "scripts"
DIFF = SCRIPTS / "skf-structural-diff.py"
CLASSIFY = SCRIPTS / "skf-severity-classify.py"
SNAPSHOT = SCRIPTS / "skf-extraction-snapshot.py"
DISPATCH = SCRIPTS / "skf-provenance-gap-dispatch.py"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render = _module("skf_render_drift_tables", SCRIPT)
snapshot_mod = _module("skf_extraction_snapshot_for_render", SNAPSHOT)
dispatch = _module("skf_gap_dispatch_for_render", DISPATCH)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data, indent=2).encode("utf-8"))
    return path


def _section(output: str, heading: str) -> str:
    """The text under one `### ` heading of the output, up to the next."""
    assert output.count(heading) == 1, (heading, output)
    rest = output[output.index(heading) + len(heading):]
    following = rest.find("\n### ")
    return rest if following == -1 else rest[:following]


def _rows(section: str) -> list[str]:
    """The body rows of the table in a section (its header and rule dropped)."""
    lines = [line for line in section.splitlines() if line.startswith("|")]
    return lines[2:]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False, stdin=subprocess.DEVNULL)


def _entry(name: str, file: str, line: int, **extra) -> dict:
    """A provenance-map entry, in the fields create-skill writes."""
    return {"export_name": name, "export_type": "function", "source_file": file, "source_line": line,
            "confidence": "T1", "extraction_method": "ast-grep", **extra}


def _export(name: str, file: str, line: int, **extra) -> dict:
    """A snapshot export, in the fields audit step 2 writes."""
    return {"name": name, "type": "function", "signature": f"def {name}()", "file": file, "line": line,
            "confidence": "T1", "extraction_method": "ast-grep", **extra}


def _diff(tmp_path: Path, entries: list, exports: list, *extra: str, **provenance) -> dict:
    """What skf-structural-diff.py saves, as step 3 §1 runs it."""
    baseline = _write_json(tmp_path / "provenance-map.json", {"entries": entries, **provenance})
    current = _write_json(tmp_path / "extraction-snapshot.json", {"exports": exports})
    out = tmp_path / "structural-diff.json"
    proc = subprocess.run([sys.executable, str(DIFF), str(baseline), str(current), "-o", str(out), *extra],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def _classify(tmp_path: Path, findings: list) -> dict:
    """What skf-severity-classify.py saves, as step 5 §2 runs it."""
    source = _write_json(tmp_path / "findings.json", findings)
    out = tmp_path / "severity.json"
    proc = subprocess.run([sys.executable, str(CLASSIFY), str(source), "-o", str(out)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Cells
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value,cell", [
    ("parse(mode: 'a' | 'b')", "`parse(mode: 'a' \\| 'b')`"),
    ("x`y", "`` x`y ``"),
    ("a``b", "``` a``b ```"),
    (["self", "path"], "`(self, path)`"),
    ("multi\n  line", "`multi line`"),
    (None, "(none)"),
    ("", "(none)"),
], ids=["pipe", "backtick", "two-backticks", "list", "newline", "none", "empty"])
def test_a_code_cell_holds_the_value_as_written(value, cell):
    assert render.code(value) == cell


def test_a_plain_cell_escapes_markdown():
    assert render.text("removed function: def __init__(self) -> A | B") == (
        "removed function: def \\_\\_init\\_\\_(self) -\\> A \\| B")
    assert render.text(None) == "n/a"
    assert render.where("pkg/__init__.py", 3) == "`pkg/__init__.py:3`"
    assert render.where("README.md") == "`README.md`"
    assert render.where(None, 3) == "n/a"


# --------------------------------------------------------------------------
# The rollup plan
# --------------------------------------------------------------------------


def _items(file: str, count: int, key: str = "k") -> list[dict]:
    return [{"file": file, "key": key, "n": f"{file}#{i}"} for i in range(count)]


def _plan(items: list[dict], **kwargs) -> list[tuple]:
    return render.plan_rows(items, key=lambda i: i["key"], path=lambda i: i["file"], **kwargs)


def _shape(plan: list[tuple]) -> list[tuple]:
    return [(row[0], row[1], len(row[2])) if row[0] == "rollup" else ("item", row[1]["n"]) for row in plan]


def test_ten_rows_of_one_file_roll_up_and_nine_do_not():
    assert _shape(_plan(_items("pkg/a.py", 10))) == [("rollup", "pkg/a.py", 10)]
    nine = _plan(_items("pkg/a.py", 9))
    assert [row[0] for row in nine] == ["item"] * 9


def test_the_rows_left_roll_up_by_directory_but_never_at_the_top_level():
    items = _items("pkg/old/a.py", 4) + _items("pkg/old/b.py", 3) + _items("pkg/old/c.py", 3) + _items("x.py", 1)
    assert _shape(_plan(items)) == [("rollup", "pkg/old/", 10), ("item", "x.py#0")]
    top = [{"file": f"f{i}.py", "key": "k", "n": f"f{i}"} for i in range(12)]
    assert [row[0] for row in _plan(top)] == ["item"] * 12


def test_a_file_rollup_comes_first_and_the_directory_takes_what_is_left():
    items = _items("pkg/a.py", 12) + _items("pkg/b.py", 5) + _items("pkg/c.py", 5)
    assert _shape(_plan(items)) == [("rollup", "pkg/a.py", 12), ("rollup", "pkg/", 10)]


def test_a_row_by_directory_refuses_stops_at_the_file_level():
    items = _items("pkg/a.py", 10, key="added") + [{"file": f"pkg/m{i}.py", "key": "added", "n": f"m{i}"}
                                                   for i in range(10)]
    plan = _plan(items, by_directory=lambda i: i["key"] == "removed")
    assert _shape(plan) == [("rollup", "pkg/a.py", 10)] + [("item", f"m{i}") for i in range(10)]


def test_rows_of_another_kind_or_ineligible_rows_never_join_a_rollup():
    items = _items("pkg/a.py", 6, key="added") + _items("pkg/a.py", 6, key="removed")
    assert [row[0] for row in _plan(items)] == ["item"] * 12
    plan = _plan(_items("pkg/a.py", 10), eligible=lambda i: not i["n"].endswith("#3"))
    assert [row[0] for row in plan] == ["item"] * 10


def test_a_rollup_row_takes_the_place_of_its_first_member():
    items = [{"file": "x.py", "key": "k", "n": "first"}] + _items("pkg/a.py", 10) + [
        {"file": "y.py", "key": "k", "n": "last"}]
    assert _shape(_plan(items)) == [("item", "first"), ("rollup", "pkg/a.py", 10), ("item", "last")]


# --------------------------------------------------------------------------
# structural: what skf-structural-diff.py saves
# --------------------------------------------------------------------------


def test_the_structural_tables_follow_the_saved_diff(tmp_path):
    entries = [_entry("keep", "pkg/a.py", 1), _entry("gone", "pkg/a.py", 9, signature="def gone(x: int | None)"),
               _entry("moves", "pkg/a.py", 20), _entry("shifts", "pkg/a.py", 30),
               _entry("retyped", "pkg/a.py", 40, signature="def retyped(a)")]
    exports = [_export("keep", "pkg/a.py", 1), _export("moves", "pkg/util/m.py", 2),
               _export("shifts", "pkg/a.py", 33), _export("retyped", "pkg/a.py", 40, signature="def retyped(a, b)"),
               _export("fresh", "pkg/__init__.py", 5)]
    diff = _diff(tmp_path, entries, exports)
    out = render.render_structural(diff)
    order = [m.group(0) for m in re.finditer(r"^### .+$", out, re.M)]
    assert order == ["### Added Exports (1)", "### Removed Exports (1)", "### Moved Exports (1)",
                     "### Changed Exports (2)", "### Summary"]
    assert _rows(_section(out, "### Added Exports (1)")) == [
        "| `fresh` | function | `def fresh()` | `pkg/__init__.py:5` | T1 |"]
    assert _rows(_section(out, "### Removed Exports (1)")) == [
        "| `gone` | function | `def gone(x: int \\| None)` | `pkg/a.py:9` | T1 |"]
    assert _rows(_section(out, "### Moved Exports (1)")) == ["| `moves` | `pkg/a.py:20` | `pkg/util/m.py:2` | T1 |"]
    changed = _rows(_section(out, "### Changed Exports (2)"))
    assert "| `shifts` | location | `30` | `33` | `pkg/a.py:33` | T1 |" in changed
    assert "| `retyped` | signature | `def retyped(a)` | `def retyped(a, b)` | `pkg/a.py:40` | T1 |" in changed
    summary = _rows(_section(out, "### Summary"))
    assert summary == ["| Added | 1 |", "| Removed | 1 |", "| Moved | 1 |", "| Changed | 2 |",
                       "| **Total Drift Items** | 5 |"]
    # Nothing optional is printed when the diff has none of it.
    for absent in ("Ambiguous Names", "Signatures not compared", "Off the public surface", "By Library",
                   "Script/Asset Drift", "Provenance label differences"):
        assert absent not in out, absent


def test_every_heading_count_comes_from_the_summary():
    """A stack's summary sums its libraries, and a rollup row stands for many
    exports: the headings never count rows."""
    diff = {"summary": {"added": 7, "removed": 5, "changed": 4, "moved": 3, "ambiguous_names": 2,
                        "label_changes": 6, "signature_unverified": 0},
            "added": [{"name": "a", "file": "a.py", "line": 1}], "removed": [], "changed": [], "moved": [],
            "ambiguous_names": [{"name": "GET", "removed": [], "added": []}],
            "label_changes": [{"name": "x", "file": "x.py", "baseline": {}, "current": {}}]}
    out = render.render_structural(diff)
    for heading in ("### Added Exports (7)", "### Removed Exports (5)", "### Moved Exports (3)",
                    "### Changed Exports (4)", "### Ambiguous Names (2)",
                    "### Provenance label differences (not drift) (6)"):
        assert heading in out, heading
    assert "| **Total Drift Items** | 19 |" in out
    result = {"drift_score": "MINOR", "total_items": 9, "by_severity": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0,
                                                                         "LOW": 9},
              "findings": [{"type": "changed", "category": "location", "name": "a", "severity": "LOW", "count": 9}]}
    out = render.render_severity(result)
    assert "### LOW (9)" in out and "| **Total** | 9 |" in out
    assert _rows(_section(out, "### LOW (9)")) == ["| 1 | `a` (×9) | structural | n/a | n/a | n/a |"]


def test_an_empty_table_says_none(tmp_path):
    diff = _diff(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1)])
    out = render.render_structural(diff)
    assert _section(out, "### Added Exports (0)").strip() == "None."
    assert "| **Total Drift Items** | 0 |" in out


def test_ambiguous_names_unverified_signatures_and_labels(tmp_path):
    entries = [_entry("GET", "routes/a.ts", 1), _entry("GET", "routes/b.ts", 1),
               _entry("parse", "p.py", 3, params=["text"], return_type="Tree", signature=None)]
    entries += [_entry(f"f{i}", "lib.py", i + 10) for i in range(10)]
    exports = [_export("GET", "routes/c.ts", 1), _export("GET", "routes/d.ts", 1),
               _export("parse", "p.py", 3, signature="def parse(text) -> Tree")]
    exports += [_export(f"f{i}", "lib.py", i + 10, confidence="T1-low", extraction_method="source-read")
                for i in range(10)]
    diff = _diff(tmp_path, entries, exports)
    assert diff["summary"]["signature_unverified"] == 1 and diff["summary"]["label_changes"] == 10
    out = render.render_structural(diff)
    assert _rows(_section(out, "### Ambiguous Names (1)")) == [
        "| `GET` | `routes/a.ts:1`, `routes/b.ts:1` | `routes/c.ts:1`, `routes/d.ts:1` |"]
    assert ("**Signatures not compared:** 1 matched exports hold their signature in different fields on the two "
            "sides, so a change there cannot be seen.") in out
    labels = _section(out, "### Provenance label differences (not drift) (10)")
    assert "they are excluded from Total Drift Items and are not findings" in labels
    # Ten rows with one baseline and one current label read as one row.
    assert _rows(labels) == ["| 10 exports (rep: `f0`, `f1`, `f2`, …) | T1 / ast-grep | T1-low / source-read |"]


def test_exports_off_the_public_surface_are_a_note_not_added_rows(tmp_path):
    """#702: a public-api snapshot marks its internal exports `public: false`, and the diff lists the ones the map
    lacks under not_public[]: no Added row, no Total Drift Items, one note whose count is the summary's and which
    names the first ten as `name` (`file`), then how many more, as update-skill's not_public warning does."""
    exports = [_export("keep", "pkg/a.py", 1), _export("fresh", "pkg/__init__.py", 4, public=True)]
    exports += [_export(f"inner{i:02}", "pkg/ui.py", i + 1, public=False) for i in range(12)]
    diff = _diff(tmp_path, [_entry("keep", "pkg/a.py", 1)], exports)
    assert (diff["summary"]["added"], diff["summary"]["not_public"]) == (1, 12)
    out = render.render_structural(diff)
    assert _rows(_section(out, "### Added Exports (1)")) == [
        "| `fresh` | function | `def fresh()` | `pkg/__init__.py:4` | T1 |"]
    assert "| **Total Drift Items** | 1 |" in out
    named = ", ".join(f"`inner{i:02}` (`pkg/ui.py`)" for i in range(10))
    assert ("**Off the public surface:** 12 exports the provenance map does not hold are off this public-api "
            "skill's public surface (`not_public[]` in the saved diff), so they are not reported as added and are "
            f"excluded from Total Drift Items: {named} and 2 more.") in _section(out, "### Summary")
    assert "inner10" not in out and "inner11" not in out
    diff["summary"]["not_public"] = 17
    assert "**Off the public surface:** 17 exports" in render.render_structural(diff)
    assert f"{named} and 7 more." in render.render_structural(diff)


def test_one_export_off_the_public_surface_reads_in_the_singular(tmp_path):
    exports = [_export("keep", "pkg/a.py", 1), _export("inner", "pkg/ui.py", 3, public=False)]
    diff = _diff(tmp_path, [_entry("keep", "pkg/a.py", 1)], exports)
    out = render.render_structural(diff)
    assert ("**Off the public surface:** 1 export the provenance map does not hold is off this public-api skill's "
            "public surface (`not_public[]` in the saved diff), so it is not reported as added and is excluded "
            "from Total Drift Items: `inner` (`pkg/ui.py`).") in out
    assert "| **Total Drift Items** | 0 |" in out


def test_a_removed_file_reads_as_one_row(tmp_path):
    entries = [_entry(f"r{i:02}", "pkg/legacy.py", i + 1) for i in range(12)] + [_entry("keep", "pkg/core.py", 1)]
    diff = _diff(tmp_path, entries, [_export("keep", "pkg/core.py", 1)])
    out = render.render_structural(diff)
    assert _rows(_section(out, "### Removed Exports (12)")) == [
        "| 12 exports (rep: `r00`, `r01`, `r02`, …) | function | n/a | `pkg/legacy.py` | T1 |"]
    assert "| Removed | 12 |" in out


def _spread(prefix: str, count: int) -> list[str]:
    """One file per export, all in src/: a flat directory, no shared cause."""
    return [f"src/{prefix}{i}.py" for i in range(count)]


def test_exports_added_across_a_directory_keep_a_row_each(tmp_path):
    """A directory is no shared cause for added exports: 12 new exports in 12
    files of src/ keep their names, signatures and locations, in step 3's
    table and in step 5's."""
    files = _spread("mod", 12)
    diff = _diff(tmp_path, [_entry("keep", "src/core.py", 1)],
                 [_export("keep", "src/core.py", 1)] + [_export(f"fn{i}", f, 1) for i, f in enumerate(files)])
    out = render.render_structural(diff)
    rows = _rows(_section(out, "### Added Exports (12)"))
    assert len(rows) == 12 and "| `fn0` | function | `def fn0()` | `src/mod0.py:1` | T1 |" in rows
    assert not any("exports (rep:" in row for row in rows)
    findings = [{"type": "added", "category": "export", "name": f"fn{i}", "detail": f"new function: def fn{i}()",
                 "file": f, "line": 1, "confidence": "T1"} for i, f in enumerate(files)]
    severity = render.render_severity(_classify(tmp_path, findings))
    rows = _rows(_section(severity, "### HIGH (12)"))
    assert len(rows) == 12 and rows[0] == "| 1 | `fn0` | structural | new function: def fn0() | `src/mod0.py:1` | T1 |"


def test_exports_removed_across_a_directory_roll_up(tmp_path):
    """A removed package tree reads as one row, in step 3's table and in step 5's."""
    files = _spread("old", 12)
    diff = _diff(tmp_path, [_entry(f"fn{i:02}", f, 1) for i, f in enumerate(files)], [])
    out = render.render_structural(diff)
    assert _rows(_section(out, "### Removed Exports (12)")) == [
        "| 12 exports (rep: `fn00`, `fn01`, `fn02`, …) | function | n/a | `src/` | T1 |"]
    findings = [{"type": "removed", "category": "export", "name": f"fn{i:02}", "detail": "removed function",
                 "file": f, "line": 1, "confidence": "T1"} for i, f in enumerate(files)]
    severity = render.render_severity(_classify(tmp_path, findings))
    assert _rows(_section(severity, "### CRITICAL (12)")) == [
        "| 1 | removed in `src/` (×12; rep: `fn00`, `fn01`, `fn02`, …) | structural | removed function | `src/` | T1 |"]


def test_a_stack_names_each_library_and_counts_it(tmp_path):
    entries = [_entry("parse", "a/index.ts", 3, source_library="lib-a"),
               _entry("gone", "b/util.ts", 9, source_library="lib-b")]
    exports = [_export("parse", "a/index.ts", 3, source_library="lib-a"),
               _export("fresh", "b/new.ts", 1, source_library="lib-b")]
    diff = _diff(tmp_path, entries, exports, "--group-by", "source_library", provenance_version="2.0",
                 skill_type="stack", libraries=["lib-a", "lib-b"])
    out = render.render_structural(diff)
    assert _rows(_section(out, "### Added Exports (1)")) == [
        "| lib-b: `fresh` | function | `def fresh()` | `b/new.ts:1` | T1 |"]
    assert _rows(_section(out, "### By Library")) == ["| lib-a | 0 | 0 | 0 | 0 |", "| lib-b | 1 | 1 | 0 | 0 |"]


def test_removed_script_files_roll_up_by_directory_and_added_ones_do_not(tmp_path):
    diff = _diff(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1)])
    file_drift = {"added": [f"assets/new/a{i}.png" for i in range(10)],
                  "removed": [f"scripts/gen/s{i}.sh" for i in range(10)] + ["README.md"],
                  "changed": [{"path": "scripts/run.sh", "stored_hash": "sha256:1", "current_hash": "sha256:2"}],
                  "stats": {"added": 10, "removed": 11, "changed": 1, "unchanged": 4}}
    out = render.render_structural(diff, file_drift)
    rows = _rows(_section(out, "### Script/Asset Drift (added 10, removed 11, changed 1)"))
    assert rows[:10] == [f"| `assets/new/a{i}.png` | added | new file |" for i in range(10)]
    assert rows[10:] == [
        "| `scripts/gen/` (10 files, rep: `s0.sh`, `s1.sh`, `s2.sh`, …) | removed | file removed |",
        "| `README.md` | removed | file removed |",
        "| `scripts/run.sh` | changed | content sha256:1 -\\> sha256:2 |"]
    # It sits after the Summary, before the informational label table.
    assert out.index("### Summary") < out.index("### Script/Asset Drift")


@pytest.mark.parametrize("reason, note", [
    ("no skill brief", "**New files not checked:** no skill brief."),
    ("brief at b.yaml is not valid YAML: `x` | y", "**New files not checked:** brief at b.yaml is not valid YAML: "
                                                   "\\`x\\` \\| y."),
    (None, None), ("", None),
], ids=["no-brief", "unreadable-brief", "checked", "empty"])
def test_new_files_not_checked_is_noted_under_the_table(tmp_path, reason, note):
    """#696: a comparison that looked for no new file says why, under its table."""
    diff = _diff(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1)])
    file_drift = {"added": [], "added_not_checked": reason, "removed": ["scripts/old.sh"], "changed": [],
                  "stats": {"added": 0, "removed": 1, "changed": 0, "unchanged": 2}}
    section = _section(render.render_structural(diff, file_drift),
                       "### Script/Asset Drift (added 0, removed 1, changed 0)")
    if note is None:
        assert "New files not checked" not in section
    else:
        assert section.rstrip().endswith(note + " The tracked files were compared, but no new script, asset or "
                                         "document was looked for, so `added` lists none."), section
        assert section.index("| `scripts/old.sh` | removed | file removed |") < section.index(note)


# --------------------------------------------------------------------------
# severity: what skf-severity-classify.py saves
# --------------------------------------------------------------------------


def test_the_severity_tables_follow_the_saved_classification(tmp_path):
    findings = [
        {"type": "removed", "category": "export", "name": "gone", "detail": "removed function: def gone()",
         "file": "pkg/a.py", "line": 9, "confidence": "T1"},
        {"type": "changed", "category": "location", "name": "shifts", "detail": "line 30 -> 33",
         "file": "pkg/a.py", "line": 33, "confidence": "T1-low"},
        {"type": "changed", "category": "doc_source", "name": "https://x/api.md", "detail": "content a -> b",
         "file": "https://x/api.md", "line": None, "confidence": None},
        {"type": "semantic", "category": "convention", "name": "errors", "detail": "now raises",
         "file": "pkg/a.py", "line": 4, "confidence": "T2"},
    ]
    result = _classify(tmp_path, findings)
    out = render.render_severity(result)
    assert out.startswith("**Overall Drift Score: CRITICAL**\n")
    order = [m.group(0) for m in re.finditer(r"^### .+$", out, re.M)]
    assert order == ["### CRITICAL (1)", "### HIGH (1)", "### MEDIUM (1)", "### LOW (1)", "### Classification Summary"]
    assert _rows(_section(out, "### CRITICAL (1)")) == [
        "| 1 | `gone` | structural | removed function: def gone() | `pkg/a.py:9` | T1 |"]
    assert _rows(_section(out, "### HIGH (1)")) == [
        "| 1 | `https://x/api.md` | doc | content a -\\> b | `https://x/api.md` | n/a |"]
    assert _rows(_section(out, "### MEDIUM (1)")) == [
        "| 1 | `errors` | semantic | now raises | `pkg/a.py:4` | T2 |"]
    assert _rows(_section(out, "### Classification Summary")) == [
        "| CRITICAL | 1 |", "| HIGH | 1 |", "| MEDIUM | 1 |", "| LOW | 1 |", "| **Total** | 4 |"]


def test_a_clean_run_prints_empty_tables(tmp_path):
    out = render.render_severity(_classify(tmp_path, []))
    assert out.startswith("**Overall Drift Score: CLEAN**")
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        assert _section(out, f"### {level} (0)").strip() == "None."
    assert "| **Total** | 0 |" in out


def test_severity_rows_roll_up_only_where_step_3_may(tmp_path):
    """Removed exports of one file roll up; changed signatures of one file,
    which differ by construction, keep a row each."""
    removed = [{"type": "removed", "category": "export", "name": f"r{i}", "detail": f"removed function: def r{i}()",
                "file": "pkg/legacy.py", "line": i + 1, "confidence": "T1"} for i in range(11)]
    changed = [{"type": "changed", "category": "signature", "name": f"c{i}", "detail": f"signature: a -> b{i}",
                "file": "pkg/core.py", "line": i + 1, "confidence": "T1"} for i in range(10)]
    out = render.render_severity(_classify(tmp_path, removed + changed))
    rows = _rows(_section(out, "### CRITICAL (21)"))
    assert rows[0] == ("| 1 | removed in `pkg/legacy.py` (×11; rep: `r0`, `r1`, `r2`, …) | structural | "
                       "Removed or renamed public exports (functions, classes, types) | `pkg/legacy.py` | T1 |")
    assert len(rows) == 11 and rows[1].startswith("| 2 | `c0` | structural | signature: a -\\> b0 |")
    assert "| **Total** | 21 |" in out


def test_a_rollup_counts_each_findings_count(tmp_path):
    files = [{"type": "removed", "category": "file", "name": f"scripts/s{i}.sh", "detail": "file removed",
              "file": f"scripts/s{i}.sh", "line": None, "confidence": None} for i in range(10)]
    files[0]["count"] = 3
    out = render.render_severity(_classify(tmp_path, files))
    level = next(m.group(1) for m in re.finditer(r"^### (\w+) \(12\)$", out, re.M))
    assert _rows(_section(out, f"### {level} (12)")) == [
        "| 1 | removed in `scripts/` (×12; rep: `s0.sh`, `s1.sh`, `s2.sh`, …) | structural | file removed | "
        "`scripts/` | n/a |"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_the_cli_prints_the_tables_and_skips_a_file_drift_that_was_not_saved(tmp_path):
    diff = _diff(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 2)])
    assert diff["summary"]["changed"] == 1
    proc = _run("structural", str(tmp_path / "structural-diff.json"), "--file-drift", str(tmp_path / "none.json"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == render.render_structural(diff)
    proc = _run("severity", str(_write_json(tmp_path / "severity.json", _classify(tmp_path, []))))
    assert proc.returncode == 0 and proc.stdout.startswith("**Overall Drift Score: CLEAN**")


@pytest.mark.parametrize("command,content,needle", [
    ("structural", None, "no such file"),
    ("structural", b"{not json", "is not JSON"),
    ("structural", b'{"added": []}', "not a structural diff"),
    ("severity", b"[]", "not a severity classification"),
    ("outside-scope", None, "no such file"),
    ("outside-scope", b'{"outside_scope": []}', "not an extraction snapshot"),
    ("outside-scope", b'{"exports": [], "outside_scope": {"src/a.ts": ["A"]}}', "not an extraction snapshot"),
], ids=["missing", "not-json", "not-a-diff", "not-a-classification", "snapshot-missing", "snapshot-no-exports",
        "outside-scope-not-a-list"])
def test_an_input_it_cannot_read_exits_1_with_a_json_error(tmp_path, command, content, needle):
    source = tmp_path / "input.json"
    if content is not None:
        source.write_bytes(content)
    proc = _run(command, str(source))
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    # The error starts with the file it could not read, as both steps tell the model.
    assert out["status"] == "error" and out["error"].startswith(f"{source}: ") and needle in out["error"]


@pytest.mark.parametrize("content,needle", [
    (b"", "the file drift result is not JSON"),
    (b'{"added": "x"}', "not a file drift result"),
], ids=["empty", "not-a-file-drift-result"])
def test_a_saved_file_drift_it_cannot_read_skips_only_its_table(tmp_path, content, needle):
    """Step 3 §4b's '>' leaves an empty file when the comparison fails: the
    supplementary check skips its table, and the export tables still print."""
    diff = _diff(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 2)])
    bad = tmp_path / "file-drift.json"
    bad.write_bytes(content)
    proc = _run("structural", str(tmp_path / "structural-diff.json"), "--file-drift", str(bad))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith(render.render_structural(diff).rstrip("\n"))
    skipped = [line for line in proc.stdout.splitlines() if line.startswith("### Script/Asset Drift")]
    assert len(skipped) == 1 and skipped[0].startswith(f"### Script/Asset Drift: skipped ({bad}: "), skipped
    assert needle in skipped[0]


def test_a_usage_error_exits_2():
    assert _run().returncode == 2
    assert _run("structural").returncode == 2
    assert _run("outside-scope").returncode == 2
    assert _run("render", "x.json").returncode == 2
    assert _run("semantic").returncode == 2
    assert _run("constituents").returncode == 2
    # doc-drift needs the run's timestamp and provenance the stage data folder.
    assert _run("doc-drift", "doc-drift.json").returncode == 2
    assert _run("provenance", "report.md").returncode == 2


def test_help_lists_each_tables_columns():
    proc = _run("--help")
    assert proc.returncode == 0
    for columns in ("Export | Type | Signature | Location | Confidence", "Export | From | To | Confidence",
                    "Export | Removed At | Added At", "File | Change | Detail",
                    "# | Finding | Type | Detail | Location |", "Path | Evidence",
                    "Convention | Before | After |", "Export | Original Dependencies |",
                    "Change | Description | Affected Exports |", "Pattern | Documented In Skill |",
                    "URL | Old Hash | New Hash | Detected At", "Constituent | Compose-time Hash |",
                    "Field | Value"):
        assert columns in proc.stdout, columns
    for command in ("semantic FINDINGS", "doc-drift DOC_DRIFT --detected-at WHEN", "constituents FRESHNESS",
                    "provenance REPORT --stage-data DIR"):
        assert command in proc.stdout, command


def test_the_header_declares_python_3_11():
    head = _read(SCRIPT).split('"""', 1)[0]
    assert '# requires-python = ">=3.11"' in head and "# /// script" in head
    # provenance reads the report's frontmatter with yaml.safe_load.
    assert '# dependencies = ["pyyaml"]' in head
    assert re.search(r"^import yaml$", _read(SCRIPT), re.M)


def test_the_embedded_examples_hold():
    """The frontmatter reader, the flag and commit helpers and the semantic
    renderer each carry an example, and every example holds."""
    import doctest

    examples = {test.name.rsplit(".", 1)[-1] for test in doctest.DocTestFinder().find(render) if test.examples}
    assert {"read_frontmatter", "flag", "short_commit", "render_semantic"} <= examples, examples
    assert doctest.testmod(render, verbose=False).failed == 0


def test_the_docstring_names_what_each_stage_keeps():
    """The model keeps only the lines no saved file holds, stage by stage."""
    flow = _flow(render.__doc__)
    assert ("The model keeps only what the files do not hold: each section's heading, the Comparison and Method "
            "lines of steps 1c and 3, step 4's Method and QMD Collection lines, step 1c's Semantic Drift skip and "
            "step 6's Confidence Legend.") in flow


# --------------------------------------------------------------------------
# The steps call it once each, and keep no hand-filled template
# --------------------------------------------------------------------------


STRUCTURAL_CMD = ('uv run {renderDriftTablesScript} structural "{auditDataFolder}/structural-diff.json" '
                  '--file-drift "{auditDataFolder}/file-drift.json"')
SEVERITY_CMD = 'uv run {renderDriftTablesScript} severity "{auditDataFolder}/severity.json"'


def _frontmatter(path: Path) -> str:
    text = _read(path)
    return text[4:text.index("\n---\n", 4)]


def _fenced(text: str, needle: str) -> str:
    lines = [line.strip() for block in re.findall(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)
             for line in block.splitlines() if needle in line]
    assert len(lines) == 1, (needle, lines)
    return lines[0]


@pytest.mark.parametrize("path,section,end,command", [
    (STRUCTURAL, "### 5. Compile Structural Drift Section", "### 6.", STRUCTURAL_CMD),
    (SEVERITY, "### 3. Compile Severity Classification Section", "### 4.", SEVERITY_CMD),
], ids=["structural-diff", "severity-classify"])
def test_each_step_renders_its_tables_with_one_call(path, section, end, command):
    assert "renderDriftTablesScript: 'scripts/render-drift-tables.py'" in _frontmatter(path)
    assert (AUDIT / "scripts" / "render-drift-tables.py").is_file()
    body = _slice(_read(path), section, end)
    assert _fenced(body, "{renderDriftTablesScript}") == command
    flow = _flow(body)
    assert "`{renderDriftTablesScript}` resolves relative to the skill root" in flow
    assert "{what the command printed, unchanged}" in body
    assert "It prints the section's tables (`--help` lists them)." in flow
    assert ("When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could "
            "not read") in flow
    assert "A rollup changes no count: the headings and the summary come from the JSON." in flow


def test_the_hand_filled_templates_are_gone():
    structural = _read(STRUCTURAL)
    for gone in ("| Export | Type | Signature | Location | Confidence |", "| Root Cause | Count |",
                 "| Category | Count |", "| Export | Baseline label | Current label |",
                 "you may collapse them", "Group items by export name and file when compiling the report"):
        assert gone not in structural, gone
    severity = _read(SEVERITY)
    for gone in ("| # | Finding | Type | Detail | Location | Confidence |", "| Severity | Count |",
                 "may collapse"):
        assert gone not in severity, gone
    # The renderer's --help and docstring describe its tables and its rollup: the steps do not narrate them.
    for gone in ("It prints, from the saved diff", "It prints the **Overall Drift Score** line", "**Rollup.**",
                 "§5 renders the three lists as the Structural Drift section's"):
        assert gone not in structural and gone not in severity, gone
    assert "§5's renderer adds a By Library table" in structural


def test_the_steps_own_commands_render_the_saved_files(tmp_path):
    """Step 3 §5's and step 5 §3's commands, run as written on a stage data
    folder that holds what the helpers saved."""
    data = tmp_path / "forge" / "demo" / "1.0.0" / ".skf-audit" / "20260101-000000"
    diff = _diff(data, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1), _export("b", "b.py", 1)])
    _write_json(data / "file-drift.json", {"added": ["scripts/x.sh"], "removed": [], "changed": [],
                                           "stats": {"added": 1, "removed": 0, "changed": 0, "unchanged": 0}})
    _write_json(data / "severity.json", _classify(tmp_path, []))
    for path, needle in ((STRUCTURAL, "structural"), (SEVERITY, "severity")):
        words = shlex.split(_fenced(_read(path), "{renderDriftTablesScript}"))
        assert words[:4] == ["uv", "run", "{renderDriftTablesScript}", needle]
        args = [w.replace("{auditDataFolder}", data.as_posix()) for w in words[3:]]
        proc = _run(*args)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        if needle == "structural":
            assert proc.stdout == render.render_structural(diff, json.loads(
                (data / "file-drift.json").read_text(encoding="utf-8")))
            assert "### Script/Asset Drift (added 1, removed 0, changed 0)" in proc.stdout
        else:
            assert "### Classification Summary" in proc.stdout


# --------------------------------------------------------------------------
# outside-scope: step 6's Out-of-Scope New Public API table
# --------------------------------------------------------------------------


OUTSIDE_SCOPE_CMD = 'uv run {renderDriftTablesScript} outside-scope "{forge_version}/extraction-snapshot.json"'
OUTSIDE_SCOPE_SLOT = "{what the outside-scope command printed, unchanged}"
# The runner's entry_point_diff.outside_scope: two files outside the scope,
# one exporting two names through two entry points.
OUTSIDE = [
    {"name": "Zed", "language": "javascript", "entry": "index.ts", "file": "src/new/z.ts", "line": 1},
    {"name": "Alpha", "language": "javascript", "entry": "index.ts", "file": "src/new/z.ts", "line": 4},
    {"name": "Alpha", "language": "javascript", "entry": "next.ts", "file": "src/new/z.ts", "line": 4},
    {"name": "Beta", "language": "javascript", "entry": "beta.ts", "file": "src/b.ts", "line": 2},
]
OUTSIDE_TABLE = """### Out-of-Scope New Public API

| Path | Evidence |
|------|----------|
| `src/b.ts` | exports `Beta` through `beta.ts` |
| `src/new/z.ts` | exports `Alpha`, `Zed` through `index.ts`, `next.ts` |
"""


def _snapshot(tmp_path: Path, outside: list | None, tier: str = "Forge") -> dict:
    """What skf-extraction-snapshot.py build writes when the runner's
    entry-point diff names `outside` (None: no runner ran, as at Quick tier)."""
    root = tmp_path / "source"
    root.mkdir(parents=True, exist_ok=True)
    runner = None if outside is None else {"status": "ok", "exports": [],
                                           "entry_point_diff": {"outside_scope": outside}}
    return snapshot_mod.build(root, tier, "2026-01-01", None, runner, [], [])


def test_outside_scope_prints_one_row_per_file(tmp_path):
    snapshot = _snapshot(tmp_path, OUTSIDE)
    assert [item["path"] for item in snapshot["outside_scope"]] == ["src/b.ts", "src/new/z.ts"]
    assert render.render_outside_scope(snapshot) == OUTSIDE_TABLE


def test_outside_scope_skips_what_names_no_file_or_export():
    snapshot = {"exports": [], "outside_scope": [
        {"path": "src/a.ts", "names": ["A"], "entries": []}, {"path": "src/none.ts", "names": []},
        {"names": ["B"]}, "src/c.ts", {"path": "src/d.ts", "names": ["D", ""], "entries": [None, "d.ts"]}]}
    assert _rows(render.render_outside_scope(snapshot)) == [
        "| `src/a.ts` | exports `A` |", "| `src/d.ts` | exports `D` through `d.ts` |"]


@pytest.mark.parametrize("outside,tier", [([], "Forge"), (None, "Quick")], ids=["nothing-outside", "quick-tier"])
def test_outside_scope_prints_nothing_when_nothing_is_outside(tmp_path, outside, tier):
    path = _write_json(tmp_path / "extraction-snapshot.json", _snapshot(tmp_path, outside, tier))
    proc = _run("outside-scope", str(path))
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
    # A snapshot written before the key existed reads the same.
    proc = _run("outside-scope", str(_write_json(tmp_path / "old.json", {"exports": []})))
    assert (proc.returncode, proc.stdout) == (0, "")


def test_update_skill_reads_back_every_path_the_report_prints(tmp_path):
    """Step 6 §2's command, run as written on the snapshot step 2 wrote, and
    its output pasted where the Remediation Suggestions template shows it:
    skf-provenance-gap-dispatch.py, which update-skill's scope
    reconciliation runs, reads back each path with the evidence printed."""
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    snapshot = _snapshot(tmp_path, OUTSIDE)
    _write_json(forge_version / "extraction-snapshot.json", snapshot)
    words = shlex.split(_fenced(_read(REPORT), "{renderDriftTablesScript} outside-scope"))
    assert words[:4] == ["uv", "run", "{renderDriftTablesScript}", "outside-scope"]
    proc = _run(*[w.replace("{forge_version}", forge_version.as_posix()) for w in words[3:]])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == OUTSIDE_TABLE
    template = _slice(_read(REPORT), "## Remediation Suggestions\n", "### Workflow Recommendation")
    assert template.count(OUTSIDE_SCOPE_SLOT) == 1
    report = ("# Drift Report\n\n" + template.replace(OUTSIDE_SCOPE_SLOT, proc.stdout)
              + "### Workflow Recommendation\n\n**Optional:** Minor drift detected.\n\n## Provenance\n")
    candidates = dispatch.parse_candidates(dispatch.extract_out_of_scope_section(report))
    assert [c["path"] for c in candidates] == [item["path"] for item in snapshot["outside_scope"]]
    assert [c["evidence"] for c in candidates] == [
        "exports `Beta` through `beta.ts`", "exports `Alpha`, `Zed` through `index.ts`, `next.ts`"]


def test_the_report_renders_the_out_of_scope_table_with_one_call():
    assert "renderDriftTablesScript: 'scripts/render-drift-tables.py'" in _frontmatter(REPORT)
    text = _read(REPORT)
    prose = _slice(text, "**Public API outside the skill's scope.**", "Append to {outputFile}:")
    assert _fenced(prose, "{renderDriftTablesScript}") == OUTSIDE_SCOPE_CMD
    flow = _flow(prose)
    for needle in ("lists in `outside_scope`", "nothing here is judged by eye", "never by hand",
                   "`{renderDriftTablesScript}` resolves relative to the skill root",
                   "Paste its output unchanged under Remediation Suggestions",
                   "A compose-mode stack and a docs-only skill have no snapshot: skip the command.",
                   "When the command exits non-zero, its JSON `error`, else its first stderr line, says what it "
                   "could not read"):
        assert needle in flow, needle
    # No hand-filled row is left: the command prints the heading and the rows.
    for gone in ("### Out-of-Scope New Public API", "| Path | Evidence |", "{outside_scope[].path}",
                 "Write one table row per item"):
        assert gone not in text, gone
    # #1129: report.md's block says where the subsection goes, and the template
    # holds no Remediation Suggestions heading for the stage to write again.
    assert "## Remediation Suggestions" not in _read(TEMPLATE)
    block = _slice(text, "## Remediation Suggestions\n", "### Workflow Recommendation")
    assert block.count(OUTSIDE_SCOPE_SLOT) == 1


# --------------------------------------------------------------------------
# #1130: semantic, step 4's Semantic Drift tables
# --------------------------------------------------------------------------


def _semantic(category: str, name: str, **extra) -> dict:
    """A row of semantic-findings.json, as step 4 §4 saves it."""
    return {"type": "semantic", "category": category, "name": name, "detail": f"{name} changed",
            "file": "src/users.py", "line": 42, "confidence": "T2", **extra}


def _headings(out: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"^### .+$", out, re.M)]


def _cells(row: str) -> list[str]:
    """A table row's cells, split on the pipes no backslash escapes."""
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row.strip())[1:-1]]


def test_semantic_prints_only_the_categories_with_rows():
    """Two convention rows: one table, its Before and After filled, and no
    empty table for the other categories (leanness-3)."""
    rows = [_semantic("convention", "error handling", before="returns None on a miss", after="raises LookupError",
                      exports=["find_user"]),
            _semantic("convention", "logging", before="print()", after="logger.info()", exports=["run", "stop"],
                      line=7)]
    out = render.render_semantic(rows)
    assert _headings(out) == ["### Changed Conventions (2)", "### Summary"]
    assert _rows(_section(out, "### Changed Conventions (2)")) == [
        "| error handling | returns None on a miss | raises LookupError | `find_user` | `src/users.py:42` | T2 |",
        "| logging | print() | logger.info() | `run`, `stop` | `src/users.py:7` | T2 |"]
    assert _rows(_section(out, "### Summary")) == ["| Changed conventions | 2 |", "| **Total Semantic Items** | 2 |"]
    for gone in ("New Patterns", "Dependency Shifts", "Architectural Changes", "Deprecated Patterns"):
        assert gone not in out, gone


def test_semantic_rows_fill_each_categorys_columns():
    """Each table in the mapping's order, whatever order the rows were saved
    in, with the columns b92dfac8's templates had and the optional fields
    filling them."""
    rows = [
        _semantic("deprecated_pattern", "callbacks", detail="async/await everywhere", skill_reference="SKILL.md#usage"),
        _semantic("dependency", "fetch_user", detail="requests replaced by httpx", before="requests", after="httpx"),
        _semantic("architecture", "service layer", detail="handlers call services", exports=["Handler"]),
        _semantic("convention", "errors", before="None", after="raises"),
    ]
    out = render.render_semantic(rows)
    assert _headings(out) == ["### Changed Conventions (1)", "### Dependency Shifts (1)",
                              "### Architectural Changes (1)", "### Deprecated Patterns (1)", "### Summary"]
    for heading, (_, _, header) in zip(_headings(out), render.SEMANTIC_CATEGORIES):
        assert _section(out, heading).strip().splitlines()[0] == "| " + " | ".join(header) + " |", heading
    # A row without an optional field reads n/a there.
    assert _rows(_section(out, "### Changed Conventions (1)")) == [
        "| errors | None | raises | n/a | `src/users.py:42` | T2 |"]
    assert _rows(_section(out, "### Dependency Shifts (1)")) == [
        "| `fetch_user` | requests | httpx | requests replaced by httpx | `src/users.py:42` | T2 |"]
    assert _rows(_section(out, "### Architectural Changes (1)")) == [
        "| service layer | handlers call services | `Handler` | `src/users.py:42` | T2 |"]
    assert _rows(_section(out, "### Deprecated Patterns (1)")) == [
        "| callbacks | SKILL.md#usage | async/await everywhere | `src/users.py:42` | T2 |"]
    assert _rows(_section(out, "### Summary")) == [
        "| Changed conventions | 1 |", "| Dependency shifts | 1 |", "| Architectural changes | 1 |",
        "| Deprecated patterns | 1 |", "| **Total Semantic Items** | 4 |"]


def test_the_design_note_row_renders_as_the_spec_shows():
    row = {"type": "semantic", "category": "convention", "name": "error handling",
           "detail": "raises instead of returning None", "before": "returns None on a miss",
           "after": "raises LookupError", "exports": ["find_user"], "file": "src/users.py", "line": 42,
           "confidence": "T2"}
    out = render.render_semantic([row])
    assert _rows(_section(out, "### Changed Conventions (1)")) == [
        "| error handling | returns None on a miss | raises LookupError | `find_user` | `src/users.py:42` | T2 |"]


def test_a_pipe_in_a_semantic_cell_keeps_the_columns():
    rows = [_semantic("convention", "a | b", before="x | y", after="z", exports=["f|g"]),
            _semantic("dependency", "h|i", before="p | q", after="r"),
            _semantic("deprecated_pattern", "j", skill_reference="SKILL.md | Usage")]
    out = render.render_semantic(rows)
    widths = {heading: [len(_cells(row)) for row in _rows(_section(out, heading))] for heading in _headings(out)}
    assert widths == {"### Changed Conventions (1)": [6], "### Dependency Shifts (1)": [6],
                      "### Deprecated Patterns (1)": [5], "### Summary": [2, 2, 2, 2]}
    assert _cells(_rows(_section(out, "### Changed Conventions (1)"))[0])[:4] == [
        "a \\| b", "x \\| y", "z", "`f\\|g`"]
    assert _cells(_rows(_section(out, "### Dependency Shifts (1)"))[0])[0] == "`h\\|i`"


def test_semantic_with_no_row_prints_the_summary_with_total_0(tmp_path):
    path = _write_json(tmp_path / "semantic-findings.json", [])
    proc = _run("semantic", str(path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _headings(proc.stdout) == ["### Summary"]
    assert proc.stdout.splitlines()[0] == ("No semantic drift: the current source still supports every claim this "
                                           "step checked.")
    assert _rows(_section(proc.stdout, "### Summary")) == ["| **Total Semantic Items** | 0 |"]


@pytest.mark.parametrize("rows,needle", [
    ([_semantic("convention", "a"), _semantic("pattern", "b")],
     "row 1: category 'pattern' is not one of convention, dependency, architecture, deprecated_pattern"),
    ([_semantic("conventions", "a")], "row 0: category 'conventions' is not one of"),
    ([_semantic("convention", "a"), {"type": "changed", "category": "convention"}], "row 1: not a semantic finding"),
    ([_semantic("convention", "a"), "src/a.py"], "row 1: not a semantic finding"),
    ({"findings": []}, "not a semantic findings file"),
], ids=["new-patterns", "misspelled", "not-semantic", "not-an-object", "not-an-array"])
def test_semantic_refuses_a_row_it_cannot_place(tmp_path, rows, needle):
    path = _write_json(tmp_path / "semantic-findings.json", rows)
    proc = _run("semantic", str(path))
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["status"] == "error" and out["error"].startswith(f"{path}: ") and needle in out["error"], out


# --------------------------------------------------------------------------
# #1130: doc-drift, step 5a's Documentation Drift section
# --------------------------------------------------------------------------


DOC_DRIFT_RESULT = {
    "changed": [{"url": "https://docs.x/api.md", "old_hash": "sha256:aa", "new_hash": "sha256:bb"}],
    "unchanged": [{"url": "https://docs.x/ok.md"}],
    "fetch_failed": [{"url": "https://docs.x/gone.md", "old_hash": "sha256:cc", "reason": "HTTP 404"}],
    "skipped_null_hash": [{"url": "https://docs.x/new.md"}],
    "stats": {"total_tracked": 4, "changed": 1, "unchanged": 1, "fetch_failed": 1, "skipped_null_hash": 1},
}


def test_doc_drift_rows_follow_the_one_row_rule():
    """The rule doc-drift.md stated (#600), now the renderer's: each changed
    entry, then each fetch_failed one, then each skipped_null_hash one; an
    unchanged entry gets no row. Detected At is the run's timestamp."""
    out = render.render_doc_drift(DOC_DRIFT_RESULT, "20260101-000000")
    lines = out.splitlines()
    assert lines[0] == "| URL | Old Hash | New Hash | Detected At |"
    assert _rows(out) == [
        "| `https://docs.x/api.md` | `sha256:aa` | `sha256:bb` | 20260101-000000 |",
        "| `https://docs.x/gone.md` | `sha256:cc` | _(fetch failed: HTTP 404)_ | 20260101-000000 |",
        "| `https://docs.x/new.md` | _(not recorded)_ | n/a | n/a |"]
    assert lines[-1] == "**1 of 4 tracked documentation source(s) have changed since compile.**"
    assert "ok.md" not in out
    # The counts come from stats, never from the rows.
    counted = {**DOC_DRIFT_RESULT, "stats": {**DOC_DRIFT_RESULT["stats"], "changed": 3, "total_tracked": 9}}
    assert render.render_doc_drift(counted, "x").splitlines()[-1] == (
        "**3 of 9 tracked documentation source(s) have changed since compile.**")


def test_a_pipe_in_a_url_or_a_reason_keeps_the_columns():
    data = {"changed": [{"url": "https://x/a|b.md", "old_hash": "sha256:1", "new_hash": "sha256:2"}],
            "unchanged": [],
            "fetch_failed": [{"url": "https://x/c|d.md", "old_hash": "sha256:3", "reason": "HTTP 502 | bad_gateway"}],
            "skipped_null_hash": [],
            "stats": {"total_tracked": 2, "changed": 1, "unchanged": 0, "fetch_failed": 1, "skipped_null_hash": 0}}
    rows = _rows(render.render_doc_drift(data, "20260101-000000"))
    assert [len(_cells(row)) for row in rows] == [4, 4]
    assert _cells(rows[0])[0] == "`https://x/a\\|b.md`"
    assert _cells(rows[1]) == ["`https://x/c\\|d.md`", "`sha256:3`", "_(fetch failed: HTTP 502 \\| bad\\_gateway)_",
                               "20260101-000000"]
    clean = {**data, "changed": [], "stats": {**data["stats"], "changed": 0, "unchanged": 1}}
    assert ("**Could not be fetched:** `https://x/c\\|d.md` (HTTP 502 \\| bad\\_gateway)."
            in render.render_doc_drift(clean, "x"))


def test_doc_drift_with_no_change_prints_the_no_drift_line_and_names_the_rest():
    data = {"changed": [], "unchanged": [{"url": "https://docs.x/ok.md"}],
            "fetch_failed": [{"url": "https://docs.x/gone.md", "old_hash": "sha256:cc", "reason": "timed out"}],
            "skipped_null_hash": [],
            "stats": {"total_tracked": 2, "changed": 0, "unchanged": 1, "fetch_failed": 1, "skipped_null_hash": 0}}
    out = render.render_doc_drift(data, "20260101-000000")
    assert "|" not in out and "20260101-000000" not in out
    assert out.strip().split("\n\n") == [
        "No documentation drift detected. 1 of 2 tracked documentation source(s) match their compile-time hashes.",
        "**Could not be fetched:** `https://docs.x/gone.md` (timed out)."]
    unhashed = {**data, "fetch_failed": [], "skipped_null_hash": [{"url": "https://docs.x/new.md"}],
                "stats": {**data["stats"], "fetch_failed": 0, "skipped_null_hash": 1}}
    assert render.render_doc_drift(unhashed, "x").strip().split("\n\n")[1:] == [
        "**No compile-time hash recorded:** `https://docs.x/new.md`."]
    matched = {**data, "fetch_failed": [], "stats": {**data["stats"], "fetch_failed": 0, "total_tracked": 1}}
    assert render.render_doc_drift(matched, "x").strip() == (
        "No documentation drift detected. 1 of 1 tracked documentation source(s) match their compile-time hashes.")


# --------------------------------------------------------------------------
# #1130: constituents, step 1c's Constituent Freshness table
# --------------------------------------------------------------------------


FRESHNESS = {
    "drifted": [{"skill_name": "lib-moved-on", "skill_path": "skills/lib-moved-on/", "stored_hash": "sha256:11",
                 "current_hash": "sha256:22"}],
    "fresh": [{"skill_name": "lib-fresh"}, {"skill_name": "lib-also-fresh"}],
    "missing": [{"skill_name": "lib-gone", "skill_path": "skills/lib-gone/", "stored_hash": "sha256:33",
                 "reason": "metadata-not-found"}],
    "skipped_null_hash": [{"skill_name": "lib-cascade"}],
    "stats": {"total": 5, "drifted": 1, "fresh": 2, "missing": 1, "skipped_null_hash": 1},
}


def test_constituents_count_from_stats_and_print_both_lines():
    out = render.render_constituents(FRESHNESS)
    assert out.splitlines()[0] == "### Constituent Freshness (drifted 1, missing 1, fresh 2)"
    assert _rows(out) == ["| `lib-moved-on` | `sha256:11` | `sha256:22` |"]
    assert out.rstrip().split("\n\n")[-2:] == ["**Missing constituents:** `lib-gone` (metadata-not-found).",
                                               "**Not compared (no compose-time hash):** `lib-cascade`."]
    counted = {**FRESHNESS, "stats": {**FRESHNESS["stats"], "fresh": 7}}
    assert render.render_constituents(counted).splitlines()[0] == (
        "### Constituent Freshness (drifted 1, missing 1, fresh 7)")
    fresh = {"drifted": [], "fresh": [{"skill_name": "a"}], "missing": [], "skipped_null_hash": [],
             "stats": {"total": 1, "drifted": 0, "fresh": 1, "missing": 0, "skipped_null_hash": 0}}
    assert render.render_constituents(fresh).rstrip().split("\n\n") == [
        "### Constituent Freshness (drifted 0, missing 0, fresh 1)", "None.", "**Missing constituents:** none.",
        "**Not compared (no compose-time hash):** none."]


def test_a_missing_constituent_with_no_name_reads_its_path():
    """skf-hash-content.py files a record with no skill_name as missing
    (incomplete-record), its skill_path kept when it has one."""
    data = {**FRESHNESS, "missing": [
        {"skill_name": None, "skill_path": "skills/lib-x/", "stored_hash": None, "reason": "incomplete-record"},
        {"skill_name": None, "skill_path": None, "stored_hash": None, "reason": "incomplete-record"}]}
    assert ("**Missing constituents:** `skills/lib-x/` (incomplete-record), (none) (incomplete-record)."
            in render.render_constituents(data))


@pytest.mark.parametrize("args,content,needle", [
    (("semantic",), b"{}", "not a semantic findings file"),
    (("semantic",), None, "no such file"),
    (("doc-drift", "--detected-at", "x"), b'{"changed": []}', "not a doc drift result"),
    (("doc-drift", "--detected-at", "x"), b"", "the doc drift result is not JSON"),
    (("constituents",), b'{"drifted": []}', "not a constituent freshness result"),
    (("constituents",), b"{not json", "is not JSON"),
], ids=["semantic-object", "semantic-missing", "doc-drift-partial", "doc-drift-empty", "constituents-partial",
        "constituents-not-json"])
def test_the_new_commands_exit_1_with_a_json_error(tmp_path, args, content, needle):
    source = tmp_path / "input.json"
    if content is not None:
        source.write_bytes(content)
    proc = _run(args[0], str(source), *args[1:])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "error" and out["error"].startswith(f"{source}: ") and needle in out["error"], out


# --------------------------------------------------------------------------
# #1130: provenance, step 6's Provenance table
# --------------------------------------------------------------------------


COMMIT_A = "0123456789abcdef0123456789abcdef01234567"
COMMIT_B = "fedcba9876543210fedcba9876543210fedcba98"
PROVENANCE_FIELDS = ["Audit Date", "Audited By", "Forge Tier", "Tools Used", "Source Path", "Skill Path",
                     "Audited Version", "Provenance Map", "Provenance Age", "AST fallback files", "Applied Transforms",
                     "Baseline Ref / Commit", "Audit Ref / Commit", "Upstream Latest", "Upstream Moved", "Stage Data"]
FRONT = {"workflowType": "audit-skill", "stepsCompleted": ["init", "re-index", "structural-diff"],
         "date": "2026-01-02", "skill_name": "demo", "skill_path": "skills/demo/1.0.0/demo", "source_path": "/src/demo",
         "forge_tier": "Forge+", "audited_version": "1.0.0", "audited_version_reason": "active link",
         "manifest_version": None, "provenance_map": "forge/demo/1.0.0/provenance-map.json",
         "provenance_generated_at": "2025-12-01T00:00:00Z", "provenance_age_days": 32, "baseline_ref": "v1.0.0",
         "baseline_commit": COMMIT_A, "audit_ref": "v1.0.0", "audit_ref_source": "baseline", "audit_commit": COMMIT_A,
         "latest_tag": "v1.1.0", "remote_head": COMMIT_B, "upstream_fetch": "ok", "upstream_moved": True,
         "upstream_ref": "v1.1.0", "source_tree": None, "ast_fallback_files": ["src/odd.py"],
         "applied_transforms": [{"transform": "quote_style", "count": 3}, {"transform": "hash_prefix", "count": 1}]}


def _report(path: Path, front: dict, crlf: bool = False, bom: bool = False) -> Path:
    """A drift report whose frontmatter holds `front`."""
    text = "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n# Drift Report: demo\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return path


def _provenance_rows(out: str) -> dict:
    return dict(re.findall(r"^\| \*\*(.+?)\*\* \| (.+) \|$", out, re.M))


def test_provenance_reads_each_row_from_its_keys(tmp_path):
    """A report saved with CRLF line ends and a BOM: every row comes from its
    keys, in report §3's order, and a commit shows 7 characters."""
    path = _report(tmp_path / "drift-report-20260101-000000.md", FRONT, crlf=True, bom=True)
    proc = _run("provenance", str(path), "--stage-data", "forge/demo/1.0.0/.skf-audit/20260101-000000")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.splitlines()[:2] == ["| Field | Value |", "|-------|-------|"]
    rows = _provenance_rows(proc.stdout)
    assert list(rows) == PROVENANCE_FIELDS
    assert rows == {
        "Audit Date": "2026-01-02",
        "Audited By": "Ferris (Audit mode)",
        "Forge Tier": "Forge+",
        "Tools Used": "ast-grep, ccc",
        "Source Path": "`/src/demo`",
        "Skill Path": "`skills/demo/1.0.0/demo`",
        "Audited Version": "`1.0.0` (active link)",
        "Provenance Map": "`forge/demo/1.0.0/provenance-map.json`",
        "Provenance Age": "32 days (generated 2025-12-01T00:00:00Z)",
        "AST fallback files": "`src/odd.py`",
        "Applied Transforms": "`quote_style` ×3, `hash_prefix` ×1",
        "Baseline Ref / Commit": "`v1.0.0` @ `0123456`",
        "Audit Ref / Commit": "`v1.0.0` @ `0123456` (baseline)",
        "Upstream Latest": "`v1.1.0` (fetch: ok)",
        "Upstream Moved": "true: to `v1.1.0`",
        "Stage Data": "`forge/demo/1.0.0/.skf-audit/20260101-000000/`: the JSON this run saved and classified (the "
                      "structural diff, the constituents' freshness or the documents' comparison, the findings and "
                      "their classification)",
    }
    assert COMMIT_A not in proc.stdout and COMMIT_B[:8] not in proc.stdout


def test_provenance_adds_each_tail_when_its_value_is_set(tmp_path):
    front = {**FRONT, "source_tree": "/run/tree-1", "manifest_version": "0.9.0", "latest_tag": None,
             "upstream_moved": "false", "upstream_ref": None, "forge_tier": "Quick", "ast_fallback_files": [],
             "applied_transforms": [], "audit_commit": "(unknown)"}
    rows = _provenance_rows(render.render_provenance(front, "d"))
    assert rows["Source Path"] == "`/src/demo`; read from the private tree `/run/tree-1`"
    assert rows["Audited Version"] == "`1.0.0` (active link); the export manifest names `0.9.0`"
    assert rows["Upstream Latest"] == "`fedcba9` (fetch: ok)"
    assert rows["Upstream Moved"] == "false"
    # Quick tier runs no tool and never reads a file by eye after a failed ast-grep.
    assert (rows["Tools Used"], rows["AST fallback files"], rows["Applied Transforms"]) == ("none", "n/a", "none")
    # Only a commit is cut: init's "(unknown)" reads as written.
    assert rows["Audit Ref / Commit"] == "`v1.0.0` @ `(unknown)` (baseline)"
    assert rows["Stage Data"].startswith("`d/`: ")
    forge = _provenance_rows(render.render_provenance({**FRONT, "forge_tier": "Forge", "ast_fallback_files": []}, "d"))
    assert (forge["Tools Used"], forge["AST fallback files"]) == ("ast-grep", "none")


def test_provenance_reads_n_a_for_a_value_the_run_does_not_have():
    rows = _provenance_rows(render.render_provenance({key: None for key in FRONT}, "d"))
    assert list(rows) == PROVENANCE_FIELDS
    for field in ("Audit Date", "Forge Tier", "Tools Used", "Source Path", "Skill Path", "Audited Version",
                  "Provenance Map", "Provenance Age", "AST fallback files", "Applied Transforms", "Upstream Moved"):
        assert rows[field] == "n/a", field
    assert rows["Baseline Ref / Commit"] == "n/a @ n/a"
    assert rows["Upstream Latest"] == "`(not fetched)` (fetch: n/a)"


def test_a_pipe_in_a_provenance_value_keeps_the_columns():
    out = render.render_provenance({**FRONT, "source_path": "/src/a|b", "upstream_fetch": "failed:x | y"}, "d")
    assert all(len(_cells(row)) == 2 for row in _rows(out)), out
    assert _provenance_rows(out)["Source Path"] == "`/src/a\\|b`"


def test_unquoted_refs_commits_and_dates_read_as_written(tmp_path):
    """The model writes the frontmatter: an unquoted ref such as 1.10, a
    commit of digits or a timestamp stays the text it wrote, and init's
    upstream_fetch values read back when double-quoted."""
    path = tmp_path / "drift-report.md"
    path.write_text("---\nskill_name: demo\ndate: 2026-01-02\nforge_tier: Forge\naudited_version: 1.10\n"
                    "provenance_generated_at: 2025-12-01T00:00:00Z\nprovenance_age_days: 32\nbaseline_ref: 1.10\n"
                    "baseline_commit: 0123456\naudit_ref: 1.10\naudit_commit: 0123456\naudit_ref_source: baseline\n"
                    "upstream_fetch: \"failed:fatal: 'origin' does not appear to be a git repository\"\n"
                    "upstream_moved: true\nupstream_ref: 2.10\napplied_transforms:\n"
                    "  - {transform: quote_style, count: 3}\n---\n\n# Drift Report: demo\n", encoding="utf-8")
    proc = _run("provenance", str(path), "--stage-data", "d")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = _provenance_rows(proc.stdout)
    assert rows["Audit Date"] == "2026-01-02"
    assert rows["Audited Version"] == "`1.10`"
    assert rows["Provenance Age"] == "32 days (generated 2025-12-01T00:00:00Z)"
    assert rows["Applied Transforms"] == "`quote_style` ×3"
    assert rows["Baseline Ref / Commit"] == "`1.10` @ `0123456`"
    assert rows["Audit Ref / Commit"] == "`1.10` @ `0123456` (baseline)"
    assert rows["Upstream Latest"] == ("`(not fetched)` (fetch: failed:fatal: 'origin' does not appear to be a git "
                                       "repository)")
    assert rows["Upstream Moved"] == "true: to `2.10`"
    # Unquoted, the same value is not YAML, and the error says how to write it.
    path.write_text("---\nskill_name: demo\nupstream_fetch: skipped: docs-only skill\n---\n", encoding="utf-8")
    proc = _run("provenance", str(path), "--stage-data", "d")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "write a value that holds `: ` or a quote as a double-quoted string" in json.loads(proc.stdout)["error"]
    # init §6, the writer, says so first, and the line it shows reads back as written.
    record = _flow(_slice(_read(INIT), "- Record the run context in the frontmatter", "\n- Set `stepsCompleted"))
    assert ("Write a value that holds `: `, such as the `skipped: ...` and `failed:...` values of `upstream_fetch`, "
            "as a double-quoted string with each `\\` and `\"` in it escaped") in record
    example = re.search(r"\(`(upstream_fetch: \"[^`]+\")`\)", record).group(1)
    path.write_text(f"---\nskill_name: demo\n{example}\n---\n", encoding="utf-8")
    proc = _run("provenance", str(path), "--stage-data", "d")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _provenance_rows(proc.stdout)["Upstream Latest"] == "`(not fetched)` (fetch: skipped: docs-only skill)"


def test_the_tools_follow_the_tier_table():
    """Tools Used names what knowledge/progressive-capability.md says each tier requires."""
    table = _slice(_read(TIERS), "## Tier Definitions", "### Example 1")
    rows = re.findall(r"^\| (Quick|Forge\+?|Deep) \| ([^|]+?) \|", table, re.M)
    required = {}
    for tier, needs in rows:
        needs = re.sub(r"\s+available$", "", needs.strip())
        required[tier] = () if needs == "No tools required" else tuple(t.strip() for t in needs.split("+"))
    assert required == render.TIER_TOOLS


@pytest.mark.parametrize("content,needle", [
    (b"# Drift Report\n", "no frontmatter"),
    (b"---\nskill_name: [unclosed\n---\n", "not valid YAML"),
    (b"---\n- a\n---\n", "not a YAML mapping"),
    (None, "no such file"),
], ids=["no-frontmatter", "bad-yaml", "a-list", "missing"])
def test_provenance_without_frontmatter_exits_1(tmp_path, content, needle):
    path = tmp_path / "drift-report.md"
    if content is not None:
        path.write_bytes(content)
    proc = _run("provenance", str(path), "--stage-data", "d")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "error" and out["error"].startswith(f"{path}: ") and needle in out["error"], out


# --------------------------------------------------------------------------
# #1130: the stages render these sections with one call each
# --------------------------------------------------------------------------


SLOT = "{what the command printed, unchanged}"
# command: (stage file, section start, section end, the fenced call, the fallback, the paste slot)
STAGE_COMMANDS = {
    "semantic": (SEMANTIC, "### 4. Compile Semantic Drift Section", "### 5.",
                 'uv run {renderDriftTablesScript} semantic "{auditDataFolder}/semantic-findings.json"',
                 "Semantic tables not rendered: {error}", SLOT),
    "doc-drift": (DOC_DRIFT, "### 3. Append to Drift Report", "### 4.",
                  'uv run {renderDriftTablesScript} doc-drift "{auditDataFolder}/doc-drift.json" '
                  '--detected-at "{timestamp}"',
                  "Documentation drift table not rendered: {error}", SLOT),
    "constituents": (COMPOSE, "### 2. Compile the Structural Drift Section", "### 3.",
                     'uv run {renderDriftTablesScript} constituents "{auditDataFolder}/constituent-freshness.json"',
                     "Constituent freshness not rendered: {error}", SLOT),
    "provenance": (REPORT, "### 3. Add Provenance Section", "### 4.",
                   'uv run {renderDriftTablesScript} provenance "{outputFile}" --stage-data "{auditDataFolder}"',
                   "Provenance table not rendered: {error}", "{what the provenance command printed, unchanged}"),
}


@pytest.mark.parametrize("command", list(STAGE_COMMANDS))
def test_each_new_section_is_rendered_with_one_call(command):
    path, start, end, call, fallback, slot = STAGE_COMMANDS[command]
    assert "renderDriftTablesScript: 'scripts/render-drift-tables.py'" in _frontmatter(path)
    body = _slice(_read(path), start, end)
    assert _fenced(body, "{renderDriftTablesScript}") == call
    # The output is pasted once, in the section's markdown fence, which keeps no heading of the renderer's.
    fences = re.findall(r"^```markdown\n(.*?)^```", body, re.M | re.S)
    assert sum(fence.count(slot) for fence in fences) == 1, fences
    assert not any(re.search(r"^### ", fence, re.M) for fence in fences), fences
    flow = _flow(body)
    assert ("When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not "
            f"read: write `{fallback}` in place of its output and go on") in flow
    assert "by hand" in flow and "(`--help` lists" in flow


def test_the_new_sections_keep_no_hand_filled_row():
    for path in (SEMANTIC, DOC_DRIFT, COMPOSE):
        text = _read(path)
        rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
        assert not rows, (path.name, rows)
        assert "{count}" not in text and "{stats." not in text, path.name
    provenance = _slice(_read(REPORT), "### 3. Add Provenance Section", "### 4.")
    assert "| **" not in provenance and "{tool_list" not in provenance
    # The row rules live in the renderer now.
    assert "Rows, in this order" not in _read(DOC_DRIFT)
    assert "for each `missing[]` entry" not in _read(COMPOSE)


def test_the_new_stage_commands_render_the_saved_files(tmp_path):
    """Each stage's command, run as written on a stage data folder that holds
    what the steps saved, prints what the renderer makes of those files."""
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    data = forge_version / ".skf-audit" / "20260101-000000"
    semantic = [_semantic("dependency", "fetch_user", before="requests", after="httpx")]
    _write_json(data / "semantic-findings.json", semantic)
    _write_json(data / "doc-drift.json", DOC_DRIFT_RESULT)
    _write_json(data / "constituent-freshness.json", FRESHNESS)
    report = _report(forge_version / "drift-report-20260101-000000.md", FRONT)
    values = {"{auditDataFolder}": data.as_posix(), "{timestamp}": "20260101-000000",
              "{outputFile}": report.as_posix()}
    expected = {"semantic": render.render_semantic(semantic),
                "doc-drift": render.render_doc_drift(DOC_DRIFT_RESULT, "20260101-000000"),
                "constituents": render.render_constituents(FRESHNESS),
                "provenance": render.render_provenance(FRONT, data.as_posix())}
    for command, (path, start, end, *_) in STAGE_COMMANDS.items():
        words = shlex.split(_fenced(_slice(_read(path), start, end), "{renderDriftTablesScript}"))
        assert words[:4] == ["uv", "run", "{renderDriftTablesScript}", command]
        args = []
        for word in words[3:]:
            for name, value in values.items():
                word = word.replace(name, value)
            assert "{" not in word, word
            args.append(word)
        proc = _run(*args)
        assert proc.returncode == 0, (command, proc.stdout + proc.stderr)
        assert proc.stdout.splitlines() == expected[command].splitlines(), command
