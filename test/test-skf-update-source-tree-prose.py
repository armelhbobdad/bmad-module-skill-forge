#!/usr/bin/env python3
"""Prose pins: update-skill reads a remote skill at the commit it tracks.

A skill forged from a remote repository records, as its `source_root`, the
clone SKF keeps for that repository, which every SKF run moves. These tests
keep update-skill's step files on the contract of skf-source-tree.py:

- init.md reads the source fields from metadata.json, runs the helper's
  `open` before change detection in every mode but gap-driven, binds every
  field it consumes, halts `blocked` (`init:source-tree`) when no commit
  can be read, releases the run lock only when the run took it, and shows
  the commit change in the baseline;
- detection takes modified files from git's file list, re-extraction reads
  only the tree (never the gh contents API, zread or deepwiki) and skips ccc
  ranking there, merge and write copy files from the tree;
- write records the commit it read, never writes the tree's path, and moves
  the workspace clone with the helper's `advance` (never a halt);
- the report, the health check, SKILL.md, the envelope schema, the docs and
  the knowledge files say the same, and remote-source-resolution.md, the
  update-skill copy of create-skill's clone steps, is gone;
- a gap-driven spot-check under `--allow-workspace-drift` with HEAD off the
  pinned commit moves or pins no line, every new or modified export halts in
  step 3 before merge (its line, signature, parameters and return type could
  only come from HEAD), write.md §2 runs no ast-grep recipe there, and a
  cited new export whose spot-check pins a line gets its provenance entry.

They also pin how a gap-driven run routes a test report's gaps and records
what it did:

- a split-body consistency finding (a `Source:` inside the skill package) is
  a structural fix that edits the reference file, never a modified export;
- a blocking gap with no citation that pins a line and no path to scan halts
  in step 3 with `halted-for-remediation-path`, `--dry-run` included, one
  severity rule holds in detect-changes, re-extract and write, and write's
  defensive halt has a documented status;
- the update bookkeeping has one home in provenance-map.json, with an
  `update_type` for each mode, and an update removes the copy an older SKF
  version left in metadata.json;
- a reference app's stats are recomputed with `--shape reference-app`, and
  both documented stats calls run through the helper as written.

And they pin the helpers update-skill hands its deterministic work to:

- skf-run-lock.py takes the run lock in init.md, renews it before merge.md
  and write.md write the skill (halting when this run no longer holds it,
  even when the renewal took the lock again), and releases it at every exit
  after it (init.md §1b's release contract, SKILL.md's Workflow Rules and the
  health check), by the owner acquire printed; no step keeps a PID, `kill -0`
  or `rm -f` lock, and the documented calls run against the helper;
- skf-skill-inventory.py `version` compares the source's version in init.md
  and gives merge.md the next patch version;
- the verifier's `definition-lines` finds the spot-check's definition lines,
  its `kind-at` looks up node kinds in write.md §2 and §6a, its `fix`
  applies §6a's citation and line fixes, and §6a skips the export set diff
  for a reference app, both through the helper and in the by-hand fallback;
- every path a documented helper call passes sits in double quotes;
- re-extract's Forge tier runs the recipe runner (skf-extract-public-api.py
  --mode full) over the changed files, and §0a over its file set without the
  brief's scope; the per-file workers take their exports from its output;
- under the drift override, write.md §2 keeps the public API counts
  metadata.json records, and a rescope halts at the drift gate, naming the
  amendment step 2 left in the skill brief.

And how a run reads a test report and detects drift through scripts:

- init.md finds the test report with skf-find-test-report.py (a result file
  naming a deleted report is no input), and a normal run offers a FAIL or
  PASS_WITH_DRIFT report newer than the skill and not yet applied ([G]/[S],
  the default by verdict, an `unconsumed-test-report` warning headless),
  which the no-change report then points to; write.md stamps
  generation_date to the second and records the report a repair applied;
- detect-changes §0 reads the gaps through skf-parse-gaps.py, a hard-gate
  blocked report through its ledger, and routes each by its ledger category,
  every category exactly once, warning for each gap it does not route;
  re-extract §0a scans the paths the helper resolved, and a Medium missing
  export gets targeted re-extraction without halting the run;
- Category A comes from skf-classify-changed-files.py (no brief and no
  provenance map included), Category B from one recipe runner run, which
  step 3 reuses, and skf-structural-diff.py, in order A, B, C, and §3's
  build maps them; §1b comes from skf-resolve-authoritative-files.py resolve
  --provenance-map; the helpers pass their JSON through one run folder,
  which step 8 removes, and every documented call runs as written.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
UPDATE = SRC / "skf-update-skill"
REFS = UPDATE / "references"
INIT = REFS / "init.md"
DETECT = REFS / "detect-changes.md"
RE_EXTRACT = REFS / "re-extract.md"
MERGE = REFS / "merge.md"
WRITE = REFS / "write.md"
REPORT = REFS / "report.md"
HEALTH = REFS / "health-check.md"
SKILL = UPDATE / "SKILL.md"
HELPER = SRC / "shared" / "scripts" / "skf-source-tree.py"
STATS_HELPER = SRC / "shared" / "scripts" / "skf-render-metadata-stats.py"
SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-update-result-envelope.v1.json"
INSTALL_TEST = REPO_ROOT / "test" / "test-installation-components.js"

TREE_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py",
    "{project-root}/src/shared/scripts/skf-source-tree.py",
]
DRIFT_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py",
    "{project-root}/src/shared/scripts/skf-check-workspace-drift.py",
]
READ_ONLY_RELEASE = "run §1b's release (the read-only modes took no lock)"
OPEN_BINDINGS = {
    "{source_tree_status}": "status",
    "{source_tree_reason}": "reason",
    "{source_tree_message}": "message",
    "{source_tree}": "tree",
    "{workspace_clone}": "clone",
    "{target_ref}": "target_ref",
    "{target_commit}": "target_commit",
    "{source_moved}": "moved",
    "{source_diff_status}": "diff_status",
    "{source_changed_files}": "changed_files",
    "{source_changed_counts}": "changed_counts",
    "{source_tree_warnings}": "warnings",
}
ADVANCE_BINDINGS = {
    "{advance_status}": "status",
    "{advance_skip_reason}": "skip_reason",
    "{advance_head}": "head_sha",
    "{advance_log}": "log_message",
    "{advance_warnings}": "warnings",
}
NEW_WARNINGS = ("source-tree:", "source-not-fetched", "source-version-lower", "file-diff-unavailable",
                "workspace-clone-not-updated", "target-ref-not-recorded")
# The envelope enums as they stood before this change: no new status or gate.
STATUS_ENUM = ["success", "no-changes", "detect-only", "dry-run", "halted-for-workspace-drift",
               "halted-for-brief-refinement", "halted-for-audit", "halted-for-remediation-path",
               "halted-for-manual-mismatch", "halted-for-write-failure", "halted-for-concurrent-run", "blocked"]
GATE_ENUM = ["init.update-confirmation", "detect-changes.promoted-doc-prompt", "detect-changes.scope-expansion",
             "detect-changes.deletion-ratio", "merge.clean-merge-gate"]
FLAG_RE = re.compile(r"--[a-z][a-z-]*")
GIT_MOVE_RE = re.compile(r"^\s*git\b.*\b(fetch|checkout|clone|worktree)\b")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "no frontmatter"
    return text[4:text.index("\n---\n", 4) + 1]


def _comment_before(frontmatter: str, key: str) -> str:
    lines = frontmatter.splitlines()
    index = lines.index(f"{key}:")
    comment = []
    for line in reversed(lines[:index]):
        if not line.startswith("#"):
            break
        comment.insert(0, line)
    assert comment, f"no comment above {key}"
    return "\n".join(comment)


def _fence(text: str, start: str) -> str:
    """The fenced block that holds `start`."""
    i = text.index(start)
    open_ = text.rindex("```", 0, i)
    body = text.index("\n", open_) + 1
    block = text[body:text.index("```", body)]
    assert start in block, f"{start!r} is not inside a fenced block"
    return block


_MODULE = None


def _helper():
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_source_tree_prose", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _subparser_flags(name: str) -> set[str]:
    parser = _helper()._build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {s for a in sub.choices[name]._actions for s in a.option_strings if s not in ("-h", "--help")}


def _init_6b() -> str:
    return _slice(_read(INIT), "### 6b. Prepare the Source Tree", "### 6c.")


def _write_6b() -> str:
    return _slice(_read(WRITE), "### 6b. Move the Workspace Clone", "### 7.")


# --------------------------------------------------------------------------
# init.md
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path, halts", [(INIT, True), (WRITE, False), (HEALTH, False)],
                         ids=["init", "write", "health"])
def test_probe_orders_declared(path, halts):
    frontmatter = _frontmatter(_read(path))
    assert yaml.safe_load(frontmatter)["sourceTreeProbeOrder"] == TREE_PATHS
    comment = _comment_before(frontmatter, "sourceTreeProbeOrder")
    if halts:
        assert "HALT if neither resolves" in comment
    else:
        assert "skip the call" in comment and "HALT" not in comment
    if path == WRITE:
        assert yaml.safe_load(frontmatter)["checkWorkspaceDriftProbeOrder"] == DRIFT_PATHS
        drift = _comment_before(frontmatter, "checkWorkspaceDriftProbeOrder")
        assert "HALT" not in drift
        # §6b passes --drift-helper only when it resolved; the advance still runs.
        assert "run the advance without `--drift-helper`" in drift and "skip the advance" not in drift


def test_init_section_order():
    text = _read(INIT)
    marks = ["### 6. Resolve the Source", "### 6b. Prepare the Source Tree", "### 6c. Detect the Source Version",
             "### 7. Present Baseline Summary"]
    for mark in marks:
        assert text.count(mark) == 1, mark
    assert [text.index(m) for m in marks] == sorted(text.index(m) for m in marks)


def test_init_6_reads_metadata():
    text = _read(INIT)
    six = _slice(text, "### 6. Resolve the Source", "### 6b.")
    assert "from the `metadata.json` loaded in §2" in six
    for field in ("source_root", "source_repo", "source_ref", "source_commit"):
        assert f"`{{{field}}}` ← `{field}`" in six, field
    assert "**Docs-only skill**" in six and "**Gap-driven mode**" in six and "run §6b" in six
    assert "From provenance map" not in text and "Source path from provenance map" not in text


def test_init_6b_flags_match_parser():
    open_flags = set(FLAG_RE.findall(_fence(_init_6b(), "uv run {sourceTreeHelper} open")))
    assert open_flags == _subparser_flags("open")
    advance_flags = set(FLAG_RE.findall(_fence(_write_6b(), "uv run {sourceTreeHelper} advance")))
    assert advance_flags <= _subparser_flags("advance")
    assert _subparser_flags("advance") - advance_flags == {"--lock-timeout"}
    health = _read(HEALTH)
    call = re.search(r"`uv run \{sourceTreeHelper\} close ([^`]*)`", health)
    assert call, "health-check runs no close"
    assert set(FLAG_RE.findall(call.group(1))) == _subparser_flags("close")


def test_init_6b_binds_every_consumed_field(tmp_path):
    six_b = _init_6b()
    helper = _helper()
    code, out = helper.open_tree(helper._build_parser().parse_args(["open", "--source-repo", "./x"]))
    assert code == 0 and out["status"] == "skipped"
    for flag, field in OPEN_BINDINGS.items():
        assert f"`{flag}` ← `{field}`" in six_b, flag
        assert field in out, field
    consumers = {
        DETECT: ["{source_changed_files}", "{source_diff_status}"],
        WRITE: ["{workspace_clone}", "{target_commit}", "{source_tree}"],
        REPORT: ["{source_moved}"],
        HEALTH: ["{source_tree}"],
        RE_EXTRACT: ["{source_tree_status}"],
    }
    for path, flags in consumers.items():
        text = _read(path)
        for flag in flags:
            assert flag in text, (path.name, flag)
    write_6b = _write_6b()
    result = helper.advance(helper._build_parser().parse_args(
        ["advance", "--clone", str(tmp_path / "c"), "--source-repo", "acme/lib", "--target", "xyz"]))
    assert result["skip_reason"] == "invalid-target"
    for flag, field in ADVANCE_BINDINGS.items():
        assert f"`{flag}` ← `{field}`" in write_6b, flag
        assert field in result, field


def test_init_6b_dispatch_and_halt_contract():
    six_b = _init_6b()
    for token in ("**`ready`**", "**`offline`**", "**`skipped`**", "**`unavailable`**",
                  'phase: "init:source-tree"', "source-not-fetched: {source_tree_message}",
                  "target-ref-needs-remote-source", "helper-failed", READ_ONLY_RELEASE,
                  "No `headless_decisions[]` entry", "never writes to the shared clone",
                  "bind `{source_root}` ← `{source_tree}`"):
        assert token in six_b, token


def test_init_6b_reasons_and_time_limit():
    """The reasons init.md lists are the helper's, and both calls pass one time limit."""
    six_b = _init_6b()
    unavailable = _slice(six_b, "- **`unavailable`** (exit 3):", "\n")
    start = unavailable.index("(`{source_tree_reason}` is ")
    listed = re.findall(r"`([a-z]+(?:-[a-z]+)+)`", unavailable[start:unavailable.index(")", start)])
    assert listed == list(_helper().OPEN_REASONS)
    assert "When it is `timed-out`" in unavailable and "run the command once more" in unavailable
    assert "Bind `{tree_timeout}`" in six_b and "`100`" in six_b
    assert "longest timeout your shell tool allows" not in _read(INIT)
    assert '--timeout "{tree_timeout}"' in _fence(six_b, "uv run {sourceTreeHelper} open")
    assert '--timeout "{tree_timeout}"' in _fence(_write_6b(), "uv run {sourceTreeHelper} advance")
    assert "skf-source-tree.py did not finish" in six_b and "did not run" not in six_b
    assert "whatever the letter case of those folder names" in six_b
    assert "letter case does not matter" not in six_b
    trouble = _slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                     "### Update Skill stops with `blocked` before detecting changes", "\n### ")
    for reason in (*_helper().OPEN_REASONS, "helper-failed", "target-ref-needs-remote-source"):
        assert f"`{reason}`" in trouble, reason
    assert "`--target-ref` was passed (it always needs the network)" in trouble


def test_init_rules_release_contract_and_read_only_promise():
    text = _read(INIT)
    rules = _slice(text, "## Rules", "## Steps")
    assert "except the flat-to-versioned migration" in rules and "§6b" in rules
    guard = _slice(text, "### 1b. Concurrency Guard", "### 2.")
    assert "never writes to the shared workspace clone" in guard
    assert "source-resolution-protocols.md:" not in text
    assert guard.count("**Release contract:**") == 1
    release = guard[guard.index("**Release contract:**"):]
    assert "§6b source tree" in release
    assert "The private source tree §6b prepares has its own contract" in release
    four = _slice(text, "### 4. Load Provenance Map", "### 5.")
    six = _slice(text, "### 6. Resolve the Source", "### 6b.")
    for section in (four, six):
        assert READ_ONLY_RELEASE in section
        assert "rm -f" not in section


def test_init_target_ref_flag():
    text = _read(INIT)
    request = _slice(text, "### 1. Request Skill Path", "**Skill:**")
    assert "`--target-ref <tag|branch|HEAD|commit>`" in request
    assert "set `{target_ref_override}` to its value" in text
    assert "`--target-ref` has no effect with `--from-test-report`" in text
    # The mode decides, not the flag: a missing test report leaves a normal run, which honours the ref.
    flag = _slice(text, "**If `--target-ref` was provided:**", "\n")
    assert "when `update_mode` is `gap-driven` it has no effect" in flag
    assert "When `--from-test-report` found no report, the run continues in normal mode and keeps " \
           "`{target_ref_override}`" in flag
    assert "With `--from-test-report` it has no effect" not in flag
    report = text.index("**If `--from-test-report` was provided")
    assert report < text.index("warn that no test report was found") < text.index("continue in normal source drift mode") \
        < text.index("**If `--target-ref` was provided:**")
    # init §4b can still switch a normal run to gap-driven mode, and unsets the ref then
    assert "when §4b switches a run to gap-driven mode, it unsets it with the same warning" in flag
    assert "give §1's `--target-ref` warning and unset it" in _slice(text, "### 4b.", "### 5.")


def test_version_detection_moved_to_init():
    six_c = _slice(_read(INIT), "### 6c. Detect the Source Version", "### 7.")
    assert "bind `{source_version_detected}`" in six_c and "higher semantic version" in six_c
    # SKF's own patch bumps put the skill ahead of a source that did not raise its version: no warning then.
    lower = six_c[six_c.index("- **Otherwise** leave `{source_version_detected}` unset"):]
    assert "When `major_minor` is `lower`, add `source-version-lower:" in lower
    assert "when the source's version is lower," not in lower
    assert "A source version lower only in its patch number is expected" in lower
    merge = _read(MERGE)
    assert "step 1 §6c recorded" in merge and "detected during step 3" not in merge
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    assert "step 1 §6c recorded `source_version_detected`" in two
    assert "during re-extraction" not in two and "detected during step 3" not in two


def test_baseline_shows_source_commit():
    seven = _slice(_read(INIT), "### 7. Present Baseline Summary", "### 8.")
    assert "| **Source commit** | {source_commit_line} |" in seven
    assert "| **Source** | {source_display} |" in seven
    for case in ("- `ready` and `{source_moved}` true:", "- `ready` and `{source_moved}` false:",
                 "- `ready` and `{source_moved}` null:", "- `offline`:", "- any other source:"):
        assert case in seven, case


# --------------------------------------------------------------------------
# detect-changes, re-extract, merge
# --------------------------------------------------------------------------


def test_detect_changes_uses_git_file_list():
    text = _read(DETECT)
    one = _slice(text, "### 1. Scan Current Source State", "### 1b.")
    assert "detect-changes:source-tree-missing" in one
    # the hand-built inventory is gone: the helpers walk the source themselves (#589)
    assert "§2.1's helpers walk `{source_root}` themselves: build no file inventory here." in one
    assert "record path, file size, last modified timestamp" not in text
    category_a = _slice(text, "**Category A: file-level changes.**", "**Category B")
    assert ("In a tree it takes the changed files from git's list at `{source_changed_files}`, never from file "
            "times or sizes, which a checkout rewrites") in category_a
    assert "Add each of its `warnings[]` to `warnings[]`" in category_a  # file-diff-unavailable among them
    assert "Files in both but with different timestamps/sizes → MODIFIED" not in text
    call = _fence(category_a, "uv run {classifyChangedFilesHelper} classify")
    for token in ('--tree-status "{source_tree_status}"', '--diff-status "{source_diff_status}"',
                  '--changed-files "{source_changed_files}"', '[--provenance-map "{provenance_map_path}"]',
                  '[--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"]', '--lists-dir "{run_dir}"',
                  '> "{run_dir}/category-a.json"'):
        assert token in call, token
    # it reads the brief §1c may just have amended, and a skill without one has none to pass
    assert "`--brief` (as §1c left it) when that file exists" in category_a
    rename = _slice(text, "**Category C: rename detection.**", "**Category D")
    ccc = rename[rename.index("Forge+/Deep: use CCC semantic similarity"):]
    assert "except when `{source_tree_status}` is `ready` or `offline`" in ccc
    assert "keep the ast-grep comparison" in ccc
    bridge = _read(SRC / "knowledge" / "ccc-bridge.md")
    assert "so it runs no ccc search there" in bridge and "rename detection keeps its ast-grep comparison" in bridge


CLASSIFY_HELPER = SRC / "shared" / "scripts" / "skf-classify-changed-files.py"


def _run_script(script: Path, argv: list[str]) -> tuple[int, dict]:
    """Run a helper as the step files do, in a process of its own, and parse its JSON."""
    proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, encoding="utf-8")
    assert proc.stdout.strip(), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _call_args(call: str, helper: str, values: dict, placeholders: dict | None = None,
               optional: bool = True) -> list[str]:
    """A documented call's arguments, cut at its first redirection and filled in, `<...>` values included."""
    call = re.split(r"\s>\s", call.replace("\\\n", " "), maxsplit=1)[0]
    for text, value in (placeholders or {}).items():
        call = call.replace(text, value)
    return _argv(call, helper, values, optional)


def _without(argv: list[str], flag: str) -> list[str]:
    """argv less one `flag value` pair: the call as made when the step passes no such flag."""
    i = argv.index(flag)
    return argv[:i] + argv[i + 2:]


def test_category_a_takes_every_file_change_from_git_in_a_tree(tmp_path):
    """A live run read an unchanged in-scope `__init__.py` as ADDED: it exports nothing, so the map never named it.

    Category A is the classify helper's (#589): run the documented call on git's file list, with the brief and
    without one (a quick skill after its degraded update), and with no provenance map (degraded mode).
    """
    category_a = _slice(_read(DETECT), "**Category A: file-level changes.**", "**Category B")
    one_c = _slice(_read(DETECT), "### 1c. Major-Version Scope Reconciliation", "### 2. Compare Against")
    assert "§2 Category A will pick up matching files as ADDED" in one_c and "`category: \"scope-expansion\"`" in one_c
    assert "no `--exclude`" in one_c
    excludes = _slice(_read(DETECT), "#### 2.0 Change-Detection Excludes", "#### 2.1")
    assert "Category A leaves each of them out with `--exclude`" in excludes
    assert "change_detection_excludes" not in _read(DETECT)  # one input the helper reads, no set built by hand
    for rule in ("The categories by hand", "A tracked file with an `M` or `A` row is MODIFIED"):
        assert rule not in category_a, rule  # the helper's rules, never restated

    src = tmp_path / "source tree"
    for rel, body in (("pkg/api.py", b"def search(q):\n    return q\n"), ("pkg/__init__.py", b""),
                      ("pkg/new.py", b"def fresh():\n    pass\n"), ("plugins/extra.py", b"def x():\n    pass\n"),
                      ("pkg/hidden.py", b"def rescoped():\n    pass\n"),
                      ("docs/AGENTS.md", b"# agents\n"), ("tests/test_api.py", b"def test():\n    pass\n")):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_bytes(body)
    forge = tmp_path / "forge"
    (forge / "lib").mkdir(parents=True)
    provenance = forge / "lib" / "provenance-map.json"
    provenance.write_bytes(json.dumps({"generated_at": "2026-01-01T00:00:00Z", "entries": [
        {"export_name": "search", "source_file": "pkg/api.py", "source_line": 1},
        {"export_name": "kept", "source_file": "pkg/hidden.py", "source_line": 1},
        {"export_name": "gone", "source_file": "pkg/gone.py", "source_line": 1}]}).encode("utf-8"))
    # rule R1 excluded a rescoped export's file, while the file's other exports stay tracked
    (forge / "lib" / "skill-brief.yaml").write_bytes(yaml.safe_dump({"scope": {
        "include": ["pkg/**", "docs/**", "plugins/**"], "exclude": ["tests/**", "pkg/hidden.py"],
        "amendments": [{"action": "promoted", "category": "scope-expansion", "path": "plugins/**"}]}}).encode("utf-8"))
    changed = tmp_path / "changed-files.json"
    changed.write_bytes(json.dumps({"base": "", "target": "", "files": [
        {"status": "M", "path": "pkg/api.py"}, {"status": "D", "path": "pkg/gone.py"},
        {"status": "A", "path": "pkg/new.py"}, {"status": "A", "path": "docs/AGENTS.md"},
        {"status": "M", "path": "pkg/hidden.py"}, {"status": "A", "path": "tests/test_api.py"}]}).encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    call = _fence(category_a, "uv run {classifyChangedFilesHelper} classify")
    argv = _call_args(call, "classifyChangedFilesHelper", {
        "source_root": str(src), "provenance_map_path": str(provenance), "forge_data_folder": str(forge),
        "skill_name": "lib", "language": "python", "source_tree_status": "ready", "source_diff_status": "ok",
        "source_changed_files": str(changed), "run_dir": str(run_dir)}, {"<promoted document path>": "docs/AGENTS.md"})
    code, out = _run_script(CLASSIFY_HELPER, argv)
    assert code == 0 and out["mode"] == "diff", out
    # the unchanged `__init__.py` is not ADDED; the promoted glob's file is, changed or not; the excluded
    # document and the out-of-scope test file are not; a tracked file the scope now excludes is still MODIFIED
    assert out["category_a"] == {"modified": ["pkg/api.py", "pkg/hidden.py"],
                                 "added": ["pkg/new.py", "plugins/extra.py"], "deleted": ["pkg/gone.py"]}, out
    assert json.loads((run_dir / "modified-files.json").read_bytes()) == ["pkg/api.py", "pkg/hidden.py"]
    assert json.loads((run_dir / "extract-files.json").read_bytes()) == [
        "pkg/api.py", "pkg/hidden.py", "pkg/new.py", "plugins/extra.py"]
    # no brief (a quick skill after its degraded update): the tracked files' extensions scope the walk
    code, out = _run_script(CLASSIFY_HELPER, _without(argv, "--brief"))
    assert code == 0 and out["category_a"]["added"] == ["pkg/new.py", "tests/test_api.py"], out
    # degraded mode, no provenance map: every in-scope file is modified, for step 3 to re-extract
    code, out = _run_script(CLASSIFY_HELPER, _without(argv, "--provenance-map"))
    assert code == 0 and out["mode"] == "full", out
    assert out["category_a"] == {"modified": ["pkg/__init__.py", "pkg/api.py", "pkg/new.py", "plugins/extra.py"],
                                 "added": [], "deleted": []}, out
    degraded = _slice(_read(DETECT), "**In degraded mode (no provenance map),**", "\n")
    for token in ("run Category A without `--provenance-map`", "lists every in-scope file as MODIFIED",
                  "Run Category B's step 1 only", "Category D and §2.2"):
        assert token in degraded, token
    assert "All source files are treated as MODIFIED" not in _read(DETECT)


def test_re_extract_reads_only_the_tree():
    text = _read(RE_EXTRACT)
    frontmatter = _frontmatter(text)
    assert "remoteSourceResolutionData" not in frontmatter
    assert "cccGitHygieneProbeOrder" not in frontmatter
    one_b = _slice(text, "### 1b.", "### 2.")
    for gone in ("gh api", "get_repo_structure", "ask_question", "MCP source access"):
        assert gone not in one_b, gone
    assert "Do not fetch changed files through the gh contents API, zread or deepwiki" in one_b
    assert "read every changed file from `{source_root}`" in one_b
    assert "re-extract:source-tree-missing" in one_b
    zero_a = _slice(text, "### 0a.", "### 1.")
    assert "MCP-fallback" not in zero_a
    two_b = _slice(text, "### 2b.", "### 3.")
    skip = "**Skip this section when `{source_tree_status}` is `ready` or `offline`:**"
    assert skip in two_b and two_b.index(skip) < two_b.index("ccc_bridge.search")
    assert "against the same HEAD" not in text


def test_retired_file_gone():
    assert not (REFS / "remote-source-resolution.md").exists()
    for path in sorted(UPDATE.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".toml", ".py"):
            text = _read(path)
            for gone in ("remote-source-resolution", "remoteSourceResolution", "target_version"):
                assert gone not in text, (path.relative_to(REPO_ROOT), gone)
    assert "remote-source-resolution" not in _read(INSTALL_TEST)


def test_update_fences_run_no_git_fetch_or_checkout():
    """Only the helper moves or fetches a clone; no step prose runs git for it."""
    scanned = 0
    for path in sorted(UPDATE.rglob("*.md")):
        in_fence = False
        for number, line in enumerate(_read(path).splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                scanned += 1
                assert not GIT_MOVE_RE.match(line), f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}"
    assert scanned > 50


def test_copies_come_from_the_tree():
    priority6 = _slice(_read(MERGE), "**Priority 6", "**Priority 7")
    assert "queue file for re-copy from `{source_root}`" in priority6
    assert "queue file for copy from `{source_root}`" in priority6
    three = _slice(_read(WRITE), "### 3. Write Updated provenance-map.json", "### 4.")
    assert "MODIFIED_FILE: copy the file from `{source_root}`" in three
    assert "NEW_FILE: copy the file from `{source_root}`" in three


# --------------------------------------------------------------------------
# write, report, health check
# --------------------------------------------------------------------------


def test_write_records_commit_and_never_writes_tree():
    text = _read(WRITE)
    two = _slice(text, "### 2. Write Updated metadata.json", "### 3.")
    for token in ("set `source_commit` to `{target_commit}`", "`source_ref` to `{target_ref}`", "Leave `source_root`",
                  "never write `{source_tree}`"):
        assert token in two, token
    three = _slice(text, "### 3. Write Updated provenance-map.json", "### 4.")
    assert "top-level `source_commit` and `source_ref`" in three
    four = _slice(text, "### 4. Write Updated evidence-report.md", "### 5.")
    assert "**Source commit:** {source_commit_line}" in four


def test_write_6b_advance_contract():
    text = _read(WRITE)
    marks = [text.index("### 6a."), text.index("### 6b. Move the Workspace Clone"), text.index("### 7.")]
    assert marks == sorted(marks)
    six_b = _write_6b()
    command = _fence(six_b, "uv run {sourceTreeHelper} advance")
    for token in ('--expect-commit "{source_commit}"', '--target "{target_commit}"',
                  '--hygiene-helper "{cccGitHygieneHelper}"', '--drift-helper "{checkWorkspaceDriftHelper}"',
                  '--clone "{workspace_clone}"', '--tree "{source_tree}"'):
        assert token in command, token
    assert "workspace-clone-not-updated" in six_b and "never halts" in six_b
    assert "`{source_tree_status}` is `ready` and `{workspace_clone}` is not null" in six_b


def test_report_surfaces_source_commit():
    text = _read(REPORT)
    for start, end in (("### 1. Handle No-Change Shortcut", "### 1a."), ("### 1a.", "### 1b."),
                       ("### 1b.", "### 2."), ("### 2. Present Change Summary", "### Changes Applied")):
        assert "{source_commit_line}" in _slice(text, start, end), start
    one = _slice(text, "### 1. Handle No-Change Shortcut", "### 1a.")
    assert "target-ref-not-recorded" in one
    assert 'carries `status: "no-changes"`, `files_written: []` and `warnings[]`' in one
    two = _slice(text, "### 2. Present Change Summary", "### Changes Applied")
    for token in ("(upstream not reached: compared the pinned commit only)",
                  "(file list unavailable: every tracked file re-checked)",
                  "(source clone not moved: {advance_skip_reason})", "Several fired"):
        assert token in two, token
    five_b = _slice(text, "### 5b. Result Contract", "### 6.")
    for token in NEW_WARNINGS:
        assert token in five_b, token


def test_clone_not_updated_names_commands_that_work():
    """test-skill's suggested checkout of source_ref never reaches a new branch or HEAD commit."""
    five = _slice(_read(REPORT), "### 5. Workflow Chaining Recommendations", "### 5b.")
    note = _slice(five, "When `warnings[]` holds `workspace-clone-not-updated`", "\n")
    assert '`git -C "{workspace_clone}" fetch --depth 1 origin {target_commit}`' in note
    assert '`git -C "{workspace_clone}" checkout --detach {target_commit}`' in note
    assert "`not-a-clone` or `clone-failed`" in note
    assert "shows how to re-sync" not in note
    # The limit stopped the helper's own checkout part way: a plain checkout stops on its files.
    interrupted = note[note.index("When that reason is `checkout-interrupted`"):]
    assert '`git -C "{workspace_clone}" checkout --force --detach {target_commit}`' in interrupted
    # advance deleted the ref that kept the target, so git may prune it: the fetch must stay.
    assert "keep the fetch and name" in interrupted and "in place of the plain checkout" in interrupted
    assert "in place of the two commands" not in interrupted
    assert "the fetch and the forced checkout that finish it" in _read(HELPER)
    assert "checkout-interrupted" in _helper().ADVANCE_SKIP_REASONS
    trouble = _slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                     "### Update Skill stops with `blocked` before detecting changes", "\n### ")
    assert "gives the `git` commands that move it there" in trouble and "the two commands" not in trouble
    assert "shows how to re-sync" not in trouble
    verifying = _read(REPO_ROOT / "docs" / "verifying-a-skill.md")
    assert "command that re-syncs the source" not in verifying
    assert "its report says why and how to move it" in verifying


def test_health_check_removes_tree_every_mode(tmp_path):
    text = _read(HEALTH)
    step1b = _slice(text, "1b. **Remove the private source tree**", "2. Load")
    assert 'uv run {sourceTreeHelper} close --tree "{source_tree}"' in step1b
    assert "in every mode" in step1b
    # A live run passed the run folder, close refused it, and the step read nothing from its output.
    result = _helper().close(_helper()._build_parser().parse_args(["close", "--tree", str(tmp_path / "x")]))
    assert result["status"] == "refused"
    for flag, field in (("{source_tree_close}", "status"), ("{source_tree_close_warnings}", "warnings")):
        assert f"`{flag}` ← `{field}`" in step1b and field in result, flag
    assert "Read nothing from its output" not in step1b and "never stop on the result" in step1b
    for case in ("- `removed` or `missing`: continue.", "- `refused`: run the command once more",
                 "the exact `tree` value `open` printed", "- `left`, `refused` again"):
        assert case in step1b, case
    assert "close also takes the run folder that holds it" in step1b
    marks = [text.index("1. **Release the concurrency lock**"), text.index("1b. **Remove the private source tree**"),
             text.index("2. Load `{nextStepFile}`")]
    assert marks == sorted(marks)
    assert "and the private source tree" in _slice(text, "## STEP GOAL:", "## Steps")


def test_skill_md_contract():
    text = _read(SKILL)
    flags = _slice(text, "| **Flags** |", "\n")
    assert "`--target-ref <ref>`" in flags
    # One sentence for the caller: init.md §1b holds the lock's owner, stale time, renewals and releases.
    concurrency = _slice(text, "| **Concurrency** |", "\n")
    for token in ("A second real update of the same skill halts `halted-for-concurrent-run` while the first holds "
                  "its run lock (init.md §1b)", "`--detect-only` and `--dry-run` take no lock"):
        assert token in concurrency, token
    for gone in ("PID", "self-heal", "minutes", "renews", "\u2014"):
        assert gone not in concurrency, gone
    assert "no mode writes to the shared workspace clone before write.md §6b" in concurrency
    rules = _slice(text, "## Workflow Rules", "## Stages")
    assert 'close --tree "{source_tree}"' in rules and "source-tree-missing" in rules
    assert "reads nothing from its output" not in rules
    # A halt in steps 1-7 must not read a later step file: the rule carries every case itself.
    halt = _slice(rules, "every HALT or ABORT after it", "\n")
    assert "health-check.md` step 1b" not in halt and "acts on its status as" not in halt
    for case in ("binds `{source_tree_close}` ← `status` and never stops on the result",
                 "on `removed` or `missing` it goes on",
                 "on `refused` it runs the command once more with `--tree` set to the exact `tree` value the "
                 "helper's `open` printed, and binds that result the same way",
                 "on `left`, `refused` again, or a command that fails or prints no JSON, it adds "
                 "`source-tree-not-removed: {source_tree} ({source_tree_close})`"):
        assert case in halt, case
    statuses = re.search(r'\{"status": ((?:"[a-z]+"(?: \| )?)+),', _read(HELPER))
    assert statuses and set(re.findall(r'"([a-z]+)"', statuses.group(1))) == {"removed", "missing", "left", "refused"}
    coupling = _slice(text, "- **Cross-skill data coupling:**", "\n")
    assert "skf-source-tree.py" in coupling and "remote-source-resolution" not in coupling
    assert "four shared assets" not in coupling


def test_schema_descriptions():
    schema = json.loads(_read(SCHEMA))
    props = schema["properties"]["skf_update"]["properties"]
    status = props["status"]["description"]
    assert "init:source-tree" in status and "source-tree-missing" in status
    warnings = props["warnings"]["description"]
    for token in ("source-tree:", "source-not-fetched", "source-version-lower", "file-diff-unavailable",
                  "workspace-clone-not-updated", "target-ref-not-recorded", "source-tree-not-removed"):
        assert token in warnings, token
    assert props["status"]["enum"] == STATUS_ENUM
    assert props["headless_decisions"]["items"]["properties"]["gate"]["enum"] == GATE_ENUM


# --------------------------------------------------------------------------
# The run lock: skf-run-lock.py takes, renews and releases it (#588)
# --------------------------------------------------------------------------

RUN_LOCK_HELPER = SRC / "shared" / "scripts" / "skf-run-lock.py"
INVENTORY_HELPER = SRC / "shared" / "scripts" / "skf-skill-inventory.py"
VERIFIER = SRC / "shared" / "scripts" / "skf-verify-provenance-completeness.py"
HASH_CONTENT = SRC / "shared" / "scripts" / "skf-hash-content.py"
RUN_LOCK_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py",
    "{project-root}/src/shared/scripts/skf-run-lock.py",
]
INVENTORY_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py",
    "{project-root}/src/shared/scripts/skf-skill-inventory.py",
]
VERIFIER_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py",
    "{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py",
]
LOCK_FILE = "{forge_data_folder}/{skill_name}/.skf-update.lock"
VERIFY_JSON = "{forge_data_folder}/{skill_name}/.skf-update-verify.json"


def _module(path: Path, name: str):
    assert path.is_file(), f"missing helper: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(call: str, helper: str, values: dict, optional: bool = False) -> list[str]:
    """The arguments of one documented helper call, split as a shell splits them and then filled in.

    Split first, fill after: POSIX shlex.split would drop the backslashes of a Windows path. A line ending in
    a backslash goes on in the next, as in a shell. A `[--flag ...]` synopsis group is kept, without its
    brackets, when `optional`, and dropped otherwise.
    """
    rest = call.split("uv run {" + helper + "}", 1)[1].replace("\\\n", " ")
    rest = re.sub(r"\[(--[^\]]*)\]", lambda m: m.group(1) if optional else "", rest)
    argv = []
    for arg in shlex.split(rest):
        for key, value in values.items():
            arg = arg.replace("{" + key + "}", value)
        assert "{" not in arg, arg
        argv.append(arg)
    return argv


def _lock_calls() -> dict[str, str]:
    """Each documented run-lock call: init's acquire and release, the renewals in merge and write, and the releases
    in SKILL.md's Workflow Rules and the health check."""
    rule = _slice(_slice(_read(SKILL), "## Workflow Rules", "## Stages"),
                  "- Once `references/init.md` §1b has bound `{lock_owner}`", "\n")
    inline = re.search(r"`(uv run \{runLockHelper\} release [^`]*)`", rule)
    assert inline, "SKILL.md's release rule runs no release"
    guard = _slice(_read(INIT), "### 1b. Concurrency Guard", "### 2.")
    return {
        "acquire": _fence(guard, "uv run {runLockHelper} acquire"),
        "init-release": _fence(guard, "uv run {runLockHelper} release"),
        "renew": _fence(_slice(_read(MERGE), "**Renew the run lock**", "**Choose the version this update writes**"),
                        "uv run {runLockHelper} acquire"),
        "renew-write": _fence(_slice(_read(WRITE), "**Renew the run lock first:**", "`{lock_recovery}` is"),
                              "uv run {runLockHelper} acquire"),
        "halt-release": inline.group(1),
        "release": _fence(_slice(_read(HEALTH), "1. **Release the concurrency lock**", "1b. **"),
                          "uv run {runLockHelper} release"),
    }


def test_run_lock_replaces_the_pid_guard():
    """init takes the lock through skf-run-lock.py, merge and write renew it, every exit releases it by owner (#588).

    A PID written by one Bash call is dead by the next, so the old guard never saw a live run. A renewal that
    exits 0 has taken the lock again even when this run had lost it, so only `refreshed` true lets the run write.
    """
    for path, halts in ((INIT, True), (HEALTH, False)):
        frontmatter = _frontmatter(_read(path))
        assert yaml.safe_load(frontmatter)["runLockProbeOrder"] == RUN_LOCK_PATHS, path.name
        assert ("HALT if neither" in _comment_before(frontmatter, "runLockProbeOrder")) is halts, path.name
    calls = _lock_calls()
    for name, call in calls.items():
        assert f'--lock "{LOCK_FILE}"' in call, name  # the full path, never a shell variable of an earlier call
    assert '--owner "update-skill:{skill_name}"' in calls["acquire"]
    for name in ("renew", "renew-write", "init-release", "halt-release", "release"):
        assert '--owner "{lock_owner}"' in calls[name], name
    # the stale time is stated once, as the flag every acquire passes, never restated in the prose
    for name in ("acquire", "renew", "renew-write"):
        assert "--stale-after 60" in calls[name], name
    assert calls["renew"] == calls["renew-write"]
    released = {name: " ".join(calls[name].replace("\\\n", " ").split())
                for name in ("init-release", "halt-release", "release")}
    assert len(set(released.values())) == 1, released
    for path in sorted(UPDATE.rglob("*.md")):
        assert not re.search(r"60[ -]minute", _read(path)), path.name
    guard = _slice(_read(INIT), "### 1b. Concurrency Guard", "### 2.")
    for token in ("**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.**",
                  "bind `{lock_owner}` ← `owner`", "`stale_replaced`", "`run-lock-replaced:",
                  "or held by one still waiting at a gate, whose renewal will then halt",
                  "**3** (`acquired` false)", 'status: "halted-for-concurrent-run"', 'phase: "init:concurrency-guard"',
                  'reason: "another update in progress: {message}"', "This run took no lock, so it releases none",
                  'reason: "run-lock-failed: {that message}"', "**Release contract:**",
                  "so a run that halts does not block the next one", "the Stack Skill Guard",
                  "every later step's halts",
                  "`run-lock-not-released: " + LOCK_FILE + "`",
                  "A release deletes the lock only while `{lock_owner}` holds it",
                  "merge.md §6b and write.md §2 renew the lock before the run writes the skill"):
        assert token in guard, token
    for gone in ("pid=", "self-heal", "never blocks the next one", "a held `flock`", "adds a run id"):
        assert gone not in guard, gone
    # init's own halts run §1b's release; only the later steps' halts rely on SKILL.md
    assert "as SKILL.md's Workflow Rules say" not in _read(INIT)
    lost = ('reason: "run-lock-lost: this run\'s lock lapsed while it waited; another update may have changed the '
            'skill since this run read it"')
    renewals = {
        "merge": (_slice(_read(MERGE), "**Renew the run lock**", "**Choose the version this update writes**"),
                  "before this section writes anything", 'phase: "merge:run-lock"'),
        "write": (_slice(_read(WRITE), "**Renew the run lock first:**", "Update `{skill_package}/metadata.json`:"),
                  "before writing `metadata.json`", 'phase: "write:run-lock"'),
    }
    for name, (renewal, before, phase) in renewals.items():
        for token in ("- **Exit 0 with `refreshed` true:**", "- **Exit 0 with `refreshed` false, or exit 3:**",
                      "HALT with status `halted-for-concurrent-run` " + before, phase, lost,
                      'or on exit 3 `reason: "another update in progress: {message}"`',
                      "- **Any other exit, or no JSON:** HALT with status `blocked`", 'reason: "run-lock-failed:'):
            assert token in renewal, (name, token)
        assert "- **Exit 0:**" not in renewal and "- **Exit 3:**" not in renewal, name
    merge_renewal = renewals["merge"][0]
    for token in ("On exit 0 the lock was gone, or `stale_replaced` names another update's stale lock, and this "
                  "acquire took it again", "wrote nothing to the skill package",
                  "The halt's release (SKILL.md's Workflow Rules) removes a lock this acquire took"):
        assert token in merge_renewal, token
    write_renewal = _slice(_read(WRITE), "**Renew the run lock first:**", "Update `{skill_package}/metadata.json`:")
    for token in ("step 4 §8 may have waited at its gate", "`{lock_recovery}` is, outside gap-driven mode",
                  "delete `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`",
                  "which step 4 created for this update", "in gap-driven mode",
                  "needs manual recovery before you re-run update-skill"):
        assert token in write_renewal, token
    merge = _read(MERGE)
    assert (merge.index("### 6b. Write Merged Files to Disk") < merge.index("**Renew the run lock**")
            < merge.index("**Choose the version this update writes**") < merge.index("stage-dir --target"))
    write = _read(WRITE)
    assert (write.index("### 2. Write Updated metadata.json") < write.index("**Renew the run lock first:**")
            < write.index("Update `{skill_package}/metadata.json`:") < write.index("### 3."))
    rule = _slice(_slice(_read(SKILL), "## Workflow Rules", "## Stages"),
                  "- Once `references/init.md` §1b has bound `{lock_owner}`", "\n")
    for token in ("every HALT, ABORT or other exit before step 8", "the Stack Skill Guard's redirect included",
                  "before it emits its envelope, if any", "never stops on the result",
                  "`run-lock-not-released: " + LOCK_FILE + "`"):
        assert token in rule, token
    for gone in ("The helper deletes the lock", "health-check.md"):
        assert gone not in rule, gone
    health = _read(HEALTH)
    step1 = _slice(health, "1. **Release the concurrency lock**", "1b. **")
    for token in ("- `released` true, or `reason` `absent`: continue.", "- `reason` `not-owner`:",
                  "- No candidate resolves, or the command fails or prints no JSON:", "then continue."):
        assert token in step1, token
    assert "Release the lock before delegating" not in step1
    assert "apart from one line when the lock or the tree stays on disk" in _slice(health, "## STEP GOAL:", "## Steps")
    # no step keeps the lock in a shell process, and none deletes it without checking its owner
    for path in sorted(UPDATE.rglob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = _read(path)
        assert not re.search(r"(?<!\$)\$\$(?!\$)", text), (rel, "the shell's PID")
        for gone in ("kill -0", "HELD_PID", '"$LOCK"', "PID-file"):
            assert gone not in text, (rel, gone)
        for line in text.splitlines():
            assert not ("rm " in line and ".skf-update.lock" in line), (rel, line)
    props = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]
    status = props["status"]["description"]
    for token in ("'init:concurrency-guard'", "'merge:run-lock' or 'write:run-lock'", "'run-lock-lost: ...'",
                  "never a PID",
                  "after write.md §6a's provenance fixes (both error.phase 'write:verify-manual-integrity')"):
        assert token in status, token
    assert "PID-file" not in status and "minutes" not in status and "\u2014" not in status
    for token in ("run-lock-replaced", "run-lock-not-released"):
        assert token in props["warnings"]["description"], token


def _lock_main(lock_module, call: str, values: dict, capsys) -> tuple[int, dict]:
    code = lock_module.main(_argv(call, "runLockHelper", values))
    return code, json.loads(capsys.readouterr().out)


def test_the_documented_run_lock_calls_hold_across_runs(tmp_path, capsys):
    """Run the lock calls as the step files write them: a fresh lock halts a second update, a stale one is
    taken over, a renewal tells a run whether it still holds its lock, and a release never removes a lock
    another run took (#588)."""
    lock_module = _module(RUN_LOCK_HELPER, "skf_run_lock_prose")
    calls = _lock_calls()
    forge = tmp_path / "forge data"
    base = {"forge_data_folder": str(forge), "skill_name": "lib"}
    lock = forge / "lib" / ".skf-update.lock"
    stale_since = "2020-01-01T00:00:00Z"

    def age():
        """Date the lock back past its stale time, as a run left waiting at a gate for hours would."""
        record = json.loads(lock.read_bytes())
        record["acquired_at"] = stale_since
        lock.write_bytes((json.dumps(record) + "\n").encode("utf-8"))

    def acquire() -> tuple[dict, dict]:
        code, out = _lock_main(lock_module, calls["acquire"], base, capsys)
        assert code == 0 and out["acquired"] is True, out
        return out, {**base, "lock_owner": out["owner"]}

    a, run_a = acquire()
    assert a["stale_replaced"] is None and a["stale_after_minutes"] == 60
    assert re.fullmatch(r"update-skill:lib:\d{8}T\d{6}Z-[0-9a-f]{8}", a["owner"]), a["owner"]
    assert Path(a["lock"]).as_posix() == lock.as_posix()
    # a second update halts while the lock is fresh; the message names the file to delete when no update runs
    code, b = _lock_main(lock_module, calls["acquire"], base, capsys)
    assert code == 3 and b["acquired"] is False and b["held_by"] == a["owner"]
    assert str(lock) in b["message"] and "stale" in b["message"]
    # the first renews before merge.md and write.md write (`refreshed` true: still its lock), and releases at the end
    for renewal in ("renew", "renew-write"):
        code, renewed = _lock_main(lock_module, calls[renewal], run_a, capsys)
        assert code == 0 and renewed["refreshed"] is True, renewal
    code, released = _lock_main(lock_module, calls["release"], run_a, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()
    code, again = _lock_main(lock_module, calls["halt-release"], run_a, capsys)
    assert code == 0 and again["released"] is False and again["reason"] == "absent"

    # A waits at a gate past the stale time, B takes the lock over: A's renewal halts (exit 3), A's halt leaves
    # B's lock, and B's release removes it
    a, run_a = acquire()
    age()
    b, run_b = acquire()
    assert b["stale_replaced"] == {"held_by": a["owner"], "held_since": stale_since}
    code, renewed = _lock_main(lock_module, calls["renew"], run_a, capsys)
    assert code == 3 and renewed["held_by"] == b["owner"]
    code, left = _lock_main(lock_module, calls["init-release"], run_a, capsys)
    assert code == 0 and (left["released"], left["reason"]) == (False, "not-owner") and lock.exists()
    code, released = _lock_main(lock_module, calls["release"], run_b, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()
    # B finished and released while A still waited: A's renewal exits 0 but takes the lock anew (`refreshed`
    # false, nothing replaced), so A halts before it writes, and A's halt releases the lock that renewal took
    code, renewed = _lock_main(lock_module, calls["renew-write"], run_a, capsys)
    assert code == 0 and (renewed["acquired"], renewed["refreshed"], renewed["stale_replaced"]) == (True, False, None)
    code, released = _lock_main(lock_module, calls["halt-release"], run_a, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()

    # B's lock went stale too while B waited: A's renewal replaces it (`refreshed` false, `stale_replaced` names
    # B), A halts and releases, and B's own renewal then finds no lock and halts as well
    a, run_a = acquire()
    age()
    b, run_b = acquire()
    age()
    code, renewed = _lock_main(lock_module, calls["renew"], run_a, capsys)
    assert code == 0 and renewed["refreshed"] is False
    assert renewed["stale_replaced"] == {"held_by": b["owner"], "held_since": stale_since}
    code, released = _lock_main(lock_module, calls["halt-release"], run_a, capsys)
    assert code == 0 and released["released"] is True
    code, renewed = _lock_main(lock_module, calls["renew-write"], run_b, capsys)
    assert code == 0 and (renewed["refreshed"], renewed["stale_replaced"]) == (False, None)
    code, released = _lock_main(lock_module, calls["halt-release"], run_b, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()

    # the PID and time lines an older SKF version wrote name no owner and go stale the same way
    lock.write_bytes(b"12345\n2020-01-01T00:00:00Z\n")
    code, c = _lock_main(lock_module, calls["acquire"], base, capsys)
    assert code == 0 and c["stale_replaced"] == {"held_by": None, "held_since": stale_since}


# --------------------------------------------------------------------------
# Versions from skf-skill-inventory.py (#597)
# --------------------------------------------------------------------------


def test_versions_come_from_the_inventory_helper(capsys):
    """init §6c orders the source's version against the skill's, merge §6b takes the next patch (#597)."""
    for path in (INIT, MERGE):
        assert yaml.safe_load(_frontmatter(_read(path)))["skillInventoryProbeOrder"] == INVENTORY_PATHS, path.name
    six_c = _slice(_read(INIT), "### 6c. Detect the Source Version", "### 7.")
    order = _fence(six_c, "uv run {skillInventoryHelper} version order")
    for token in ("bind `{source_version_detected}` ← `a.normalized`", "When `major_minor` is `lower`",
                  "reads {a.normalized}, older than {version}", "Never compare the two by hand", "`NOT_A_VERSION`",
                  "When no version file gives one, leave `{source_version_detected}` unset"):
        assert token in six_c, token
    assert "strip build metadata as" not in six_c
    choose = _slice(_read(MERGE), "**Choose the version this update writes**", "**Create the version folder**")
    next_patch = re.search(r"`(uv run \{skillInventoryHelper\} version next-patch [^`]*)`", choose)
    assert next_patch, "merge §6b runs no next-patch"
    for token in ("bind `{new_version}` ← `next_patch`", "Never increment it by hand",
                  "HALT with status `halted-for-write-failure` before writing anything",
                  'phase: "merge:new-version-folder", path: "{skill_package}/metadata.json"'):
        assert token in choose, token
    assert "Version Sanitization" not in choose
    inventory = _module(INVENTORY_HELPER, "skf_skill_inventory_prose")

    def run(call: str, values: dict) -> tuple[int, dict]:
        code = inventory.main(_argv(call, "skillInventoryHelper", values))
        return code, json.loads(capsys.readouterr().out)

    code, out = run(order, {"the source's version": "v1.10.0+build.7", "version": "1.9.0"})
    assert code == 0 and out["order"] == "higher" and out["a"]["normalized"] == "1.10.0"
    code, out = run(order, {"the source's version": "1.2.0", "version": "1.2.1"})
    assert code == 0 and (out["order"], out["major_minor"]) == ("lower", "equal")  # no source-version-lower
    code, out = run(order, {"the source's version": "1.9.4", "version": "2.0.1"})
    assert code == 0 and (out["order"], out["major_minor"]) == ("lower", "lower")
    code, out = run(order, {"the source's version": "dynamic", "version": "1.0.0"})
    assert code == 1 and out["code"] == "NOT_A_VERSION"
    code, out = run(next_patch.group(1), {"version": "1.2.3"})
    assert code == 0 and out["next_patch"] == "1.2.4"
    code, out = run(next_patch.group(1), {"version": "1.2.3-rc.1"})
    assert code == 0 and out["next_patch"] == "1.2.3"


# --------------------------------------------------------------------------
# The verifier's definition-lines, fix and kind-at (#584, #549)
# --------------------------------------------------------------------------

API_PY = b"import os\n\n\n@decorate\ndef search(q):\n    return q\n"


def test_spot_check_reads_definition_lines_from_the_verifier(tmp_path, capsys):
    """re-extract §0's spot-check asks definition-lines, the rules write §6a's verify applies (#584)."""
    text = _read(RE_EXTRACT)
    assert yaml.safe_load(_frontmatter(text))["verifyProvenanceCompletenessProbeOrder"] == VERIFIER_PATHS
    # one missing-helper policy for the verifier in every stage file: advisory, and never a line found by eye
    comment = _comment_before(_frontmatter(text), "verifyProvenanceCompletenessProbeOrder")
    assert "when §0 bullet 2 first needs it" in comment and "records `unknown`" in comment
    assert "Advisory" in comment and "HALT" not in comment
    assert "Advisory" in _comment_before(_frontmatter(_read(WRITE)), "verifyProvenanceCompletenessProbeOrder")
    found = _slice(text, "   - **If export found:**", "   - Record verification outcome:")
    call = _fence(found, "uv run {verifyProvenanceCompletenessHelper} definition-lines")
    for token in ("Take the definition lines from its output, never by eye", "`file-missing`",
                  "`skipped-export-type`",
                  "`skipped-language` means the rules cover no such file: read the file and take the line that "
                  "declares the export itself, never a decorator or comment above it",
                  "Record `unknown` for an entry whose call exits 2 or prints no JSON.",
                  "When no candidate resolves, record `unknown` for every entry and add `provenance: spot-checks not "
                  "run: skf-verify-provenance-completeness.py is missing; re-install SKF` to `warnings[]`"):
        assert token in found, token
    for gone in ("PEP 695", "**TS/JS:**", "**Python:**", "**Indentation:**", "read the whole source file",
                 "they cover Python and TS/JS", "a definition one line away", "re-extract:spot-check"):
        assert gone not in text, gone
    outcome = _slice(text, "   - Record verification outcome:", "\n")
    for token in ("`line_is_definition` true", "`definition_lines` holds that one line",
                  "`line_check` is `file-missing`", "(an empty `definition_lines`)"):
        assert token in outcome, token
    assert "found that line by the verifier's text rules" in _slice(_read(MERGE), "**Priority 5", "**Priority 6")
    verifier = _module(VERIFIER, "skf_verify_provenance_spot_check_prose")
    src = tmp_path / "src tree"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    (src / "lib.rs").write_bytes(b"pub fn add() {}\n")

    def run(values: dict, optional: bool = False) -> dict:
        argv = _argv(call, "verifyProvenanceCompletenessHelper", {"source_root": str(src), **values}, optional)
        assert verifier.main(argv) == 0
        return json.loads(capsys.readouterr().out)

    entry = {"source_file": "pkg/api.py", "export_name": "search", "export_type": "function"}
    out = run({**entry, "source_line": "5"})
    assert (out["line_check"], out["line_is_definition"], out["definition_lines"]) == ("checked", True, [5])
    out = run({**entry, "source_line": "4"}, optional=True)  # the decorator line: `moved` to 5
    assert (out["line_is_definition"], out["definition_lines"]) == (False, [5])
    assert run({**entry, "source_file": "pkg/gone.py", "source_line": "5"})["line_check"] == "file-missing"
    assert run({**entry, "source_line": "1", "export_type": "module"}, optional=True)["line_check"] == \
        "skipped-export-type"
    rust = run({"source_file": "lib.rs", "export_name": "add", "source_line": "1"})
    assert rust["line_check"] == "skipped-language"


def test_6a_fixes_through_the_verifier_and_skips_the_set_diff_for_a_reference_app(tmp_path, capsys):
    """§6a writes verify's JSON beside the lock and hands it to fix; a reference app gets no orphans (#549, #584)."""
    six_a = _slice(_read(WRITE), "### 6a.", "### 6b.")
    verify = _fence(six_a, "uv run {verifyProvenanceCompletenessHelper} verify")
    fix = _fence(six_a, "uv run {verifyProvenanceCompletenessHelper} fix")
    assert f'-o "{VERIFY_JSON}"' in verify and f'--verify "{VERIFY_JSON}"' in fix
    assert '--manual-inventory "{manual_inventory}"' in fix and "[--no-line-moves]" in fix
    for token in ("- `summary.set_diff`: `not-applicable` for a reference app (`scope_type: reference-app`",
                  "its `status` comes from `stale[]`, `citations[]` and `node_kinds[]` alone",
                  "note `set diff not applicable: reference app` in the Validation Summary, never as a WARN",
                  "- **`manual_verify.ok` is false** (a [MANUAL] block changed): HALT with status "
                  "`halted-for-manual-mismatch`",
                  'phase: "write:verify-manual-integrity", path: "{skill_package}/SKILL.md", reason: "[MANUAL] blocks '
                  'changed after the provenance fixes: ..."',
                  "Never apply them by hand", "each `left_as_warn[]` item stays for a person to decide",
                  "a finding `fix` left as `line-moves-skipped`"):
        assert token in six_a, token
    assert ("`fix` prints `applied[]` (each fix it made), `left_as_warn[]` (each finding it left for a person, with "
            "its `why`), `files_written[]` and `manual_verify`") in six_a
    for gone in ("plan every move before making any", "apply every planned citation move in one pass",
                 "Skip this step when", "moves no citation of a line another entry also records",
                 "writes each changed file through skf-atomic-write.py", "which only a gap-driven run reaches"):
        assert gone not in six_a, gone
    grace = _slice(six_a, "**Graceful degradation:**", "\n")
    assert "Skip the set diff for a reference app (`scope_type: reference-app`" in grace
    assert "note `set diff not applicable: reference app`" in grace

    verifier = _module(VERIFIER, "skf_verify_provenance_fix_prose")
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    package = tmp_path / "skills" / "app" / "1.0.1" / "app"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_bytes(
        b"---\nname: app\n---\n# app\n\nSearch is cached [AST:pkg/api.py:L4].\n\n"
        b"<!-- [MANUAL:notes] -->\nKeep [SRC:pkg/api.py:L4] as written.\n<!-- [/MANUAL:notes] -->\n")
    (package / "metadata.json").write_bytes(json.dumps(
        {"name": "app", "generated_by": "create-skill", "scope_type": "reference-app", "exports": []}).encode("utf-8"))
    forge = tmp_path / "forge"
    forge_version = forge / "app" / "1.0.1"
    forge_version.mkdir(parents=True)
    entry = {"export_name": "search", "export_type": "function", "source_file": "pkg/api.py", "source_line": 4,
             "confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
             "signature_source": "T1-low"}
    (forge_version / "provenance-map.json").write_bytes(json.dumps({"entries": [entry]}, indent=2).encode("utf-8"))
    inventory = forge / "app" / ".skf-update-manual-inventory.json"
    proc = subprocess.run([sys.executable, str(HASH_CONTENT), "manual-inventory", str(package / "SKILL.md")],
                          capture_output=True)
    assert proc.returncode == 0, proc.stderr
    inventory.write_bytes(proc.stdout)
    values = {"skill_package": str(package), "forge_version": str(forge_version), "source_root": str(src),
              "forge_data_folder": str(forge), "skill_name": "app", "manual_inventory": str(inventory)}

    assert verifier.main(_argv(verify, "verifyProvenanceCompletenessHelper", values)) == 1
    found = json.loads((forge / "app" / ".skf-update-verify.json").read_bytes())
    assert found["summary"]["set_diff"] == "not-applicable" and found["missing"] == found["orphaned"] == []
    assert [s["reason"] for s in found["stale"]] == ["line-not-definition"]
    assert [c["reason"] for c in found["citations"]] == ["prefix-mismatch"]
    code = verifier.main(_argv(fix, "verifyProvenanceCompletenessHelper", values))
    fixed = json.loads(capsys.readouterr().out)
    assert code == 1 and fixed["manual_verify"]["ok"] is True
    assert sorted(a["kind"] for a in fixed["applied"]) == ["citation-line", "citation-prefix", "source-line"]
    assert [(w["kind"], w["why"]) for w in fixed["left_as_warn"]] == [("citation-line", "inside-manual-block")]
    skill_md = (package / "SKILL.md").read_bytes()
    assert b"Search is cached [SRC:pkg/api.py:L5]." in skill_md
    assert b"Keep [SRC:pkg/api.py:L4] as written." in skill_md
    assert json.loads((forge_version / "provenance-map.json").read_bytes())["entries"][0]["source_line"] == 5
    assert verifier.main(_argv(verify, "verifyProvenanceCompletenessHelper", values)) == 0
    # the verify JSON beside the lock is one of SKF's own names: the forge folder stays SKF's
    proc = subprocess.run([sys.executable, str(INVENTORY_HELPER), str(tmp_path / "skills"), "--skill", "app",
                           "--forge-data-folder", str(forge)], capture_output=True, encoding="utf-8")
    group = json.loads(proc.stdout)["forge_groups"][0]
    assert (group["ownership"], group["foreign_entries"]) == ("skf", []), group


UNQUOTED_OK = {"{source_line}"}  # a line number, never a path


def _unquoted_placeholders(call: str, helper: str) -> list[str]:
    """The `{...}` values of a documented call outside double quotes, less a line number."""
    rest = call.split("uv run {" + helper + "}", 1)[1]
    outside = rest.split('"')[::2]  # the text around each quoted argument
    return [p for part in outside for p in re.findall(r"\{[^{}]+\}", part) if p not in UNQUOTED_OK]


def test_documented_helper_calls_quote_every_path():
    """A project path with a space (common under Windows and macOS user folders) stays one argument in every
    helper call this change documents: each path it passes sits in double quotes. _argv fills the values after
    the split, so it cannot see an unquoted one."""
    assert _unquoted_placeholders('uv run {h} x --a {p}/b "{q}" --line {source_line}', "h") == ["{p}"]
    calls = [(call, "runLockHelper") for call in _lock_calls().values()]
    six_c = _slice(_read(INIT), "### 6c. Detect the Source Version", "### 7.")
    calls.append((_fence(six_c, "uv run {skillInventoryHelper} version order"), "skillInventoryHelper"))
    choose = _slice(_read(MERGE), "**Choose the version this update writes**", "**Create the version folder**")
    next_patch = re.search(r"`(uv run \{skillInventoryHelper\} version next-patch [^`]*)`", choose)
    assert next_patch, "merge §6b runs no next-patch"
    calls.append((next_patch.group(1), "skillInventoryHelper"))
    verifier = "verifyProvenanceCompletenessHelper"
    found = _slice(_read(RE_EXTRACT), "   - **If export found:**", "   - Record verification outcome:")
    calls.append((_fence(found, "uv run {" + verifier + "} definition-lines"), verifier))
    six_a = _slice(_read(WRITE), "### 6a.", "### 6b.")
    for sub in ("verify", "fix"):
        calls.append((_fence(six_a, "uv run {" + verifier + "} " + sub), verifier))
    kind_at = re.findall(r"`(uv run \{" + verifier + r"\} kind-at [^`]*)`", _read(WRITE))
    assert len(kind_at) == 2, kind_at
    calls += [(call, verifier) for call in kind_at]
    assert len(calls) == 13
    for call, helper in calls:
        assert _unquoted_placeholders(call, helper) == [], call


def test_node_kinds_are_looked_up_with_kind_at():
    """write §2's relabel and §6a's node-kind fix run one kind-at call, with the patterns file as --recipes (#584)."""
    write = _read(WRITE)
    frontmatter = yaml.safe_load(_frontmatter(write))
    # one name for extraction-patterns.md in every stage file, as re-extract.md names it
    assert "extractionPatternsProbeOrder" not in frontmatter and "{extractionPatterns}" not in write
    assert "{extractionPatterns}" not in _read(RE_EXTRACT)
    assert frontmatter["extractionPatternsDataProbeOrder"] == [
        "{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md",
        "{project-root}/src/skf-create-skill/references/extraction-patterns.md"]
    two = _slice(write, "### 2. Write Updated metadata.json", "### 3.")
    six_a = _slice(write, "### 6a.", "### 6b.")
    calls = []
    for section in (two, six_a):
        match = re.search(r"`(uv run \{verifyProvenanceCompletenessHelper\} kind-at [^`]*)`", section)
        assert match, "no kind-at call"
        calls.append(match.group(1))
    assert calls[0] == calls[1]
    assert '--recipes "{extractionPatternsData}"' in calls[0]
    assert "which runs the ast-grep recipes for its language" not in two
    for section in (two, six_a):
        assert "`status` is `found`" in section and "never invent a kind" in section.replace("Never", "never")
    assert "run the recipes `{extraction" not in six_a


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_documented_kind_at_call_runs(tmp_path, capsys):
    """The kind-at call write §2 and §6a document finds a recipe's kind with the probe-ordered patterns (#584)."""
    write = _read(WRITE)
    call = re.search(r"`(uv run \{verifyProvenanceCompletenessHelper\} kind-at [^`]*)`", write).group(1)
    patterns = yaml.safe_load(_frontmatter(write))["extractionPatternsDataProbeOrder"][1]
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    values = {"source_root": str(src), "source_file": "pkg/api.py", "source_line": "5", "export_name": "search",
              "extractionPatternsData": str(REPO_ROOT / patterns[len("{project-root}/"):])}
    verifier = _module(VERIFIER, "skf_verify_provenance_kind_at_prose")
    code = verifier.main(_argv(call, "verifyProvenanceCompletenessHelper", values))
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and (out["status"], out["kind"]) == ("found", "function_definition"), out


# --------------------------------------------------------------------------
# The drift override counts nothing at HEAD (W1 handoff), and the AST protocol
# --------------------------------------------------------------------------


def test_drift_override_keeps_the_recorded_counts_and_halts_on_a_rescope():
    """Under the override write §2 takes no public API count from HEAD, so a rescope, which needs one, halts (#557)."""
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    counts = _slice(two, "  **Public API counts under the drift override**", "\n")
    for token in ("count nothing at `{source_root}`, which is HEAD, not the pinned commit",
                  "the values `{skill_package}/metadata.json` records in `stats`",
                  "once the queued `metadata_patches[]` above are applied",
                  "step 3's drift gate halted on every new, modified or rescoped export"):
        assert token in counts, token
    assert (two.index("  **Judgment payload") < two.index("  **Public API counts under the drift override**")
            < two.index("  **Shape:**"))
    assert "- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);" in _drift_gate()
    zero_a = _zero_a()
    assert "and on every rescope, whose stats recount would count the public API there" in zero_a
    assert "write.md §2 keeps the public API counts metadata.json records" in zero_a
    deleted = _slice(_read(RE_EXTRACT), "   - **If the entry is `DELETED_EXPORT` (rescope, rule R1):**", "\n")
    assert "the §0.a drift gate halted on every `DELETED_EXPORT` before bullet 1" in deleted
    init = _slice(_read(INIT), "- `--allow-workspace-drift` (gap-driven mode only)", "\n")
    assert "counts no public API there" in init
    assert "which every new or modified export does, and on every rescope" in init
    flags = _slice(_read(SKILL), "| **Flags** |", "\n")
    assert "a gap that needs the pinned tree, a rescope included, halts `halted-for-workspace-drift`" in flags
    # the rescope's amendment stays in the brief: the halt names it, since a re-run appends it again
    gate = _drift_gate()
    assert "A rescope's amendment, which step 2 wrote to the skill brief (rule R1), stays there, and the message " \
           "names it" in gate
    message = _fence(gate, "Workspace drift blocks {N} gap(s)")
    for token in ("{if a gap above is a rescope:",
                  "Kept in skill-brief.yaml, which step 2 amended for the rescopes above.",
                  "re-run adds them again, so remove them before you re-run or drop the repair:",
                  "{for each rescope: - {name}: its scope.amendments[] entry and scope.exclude {path}}}"):
        assert token in message, token
    assert "kept in skill-brief.yaml: {name} (scope.exclude {path})" in _slice(gate, "In `{headless_mode}`", "\n")
    summary = yaml.safe_load(_read(REPO_ROOT / "changes" / "update-drift-override-halts.yaml"))["summary"]
    for token in ("no count of the public API", "and as a rescope (a gap that takes an export out of the skill's "
                  "scope) does", "the stats keep the public API counts `metadata.json` records",
                  "it names the scope amendment each rescope already wrote to the skill brief"):
        assert token in summary, token
    assert "(removals, provenance line fixes" not in summary


EXTRACT_PUBLIC_API = SRC / "shared" / "scripts" / "skf-extract-public-api.py"
EXTRACT_PUBLIC_API_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py",
    "{project-root}/src/shared/scripts/skf-extract-public-api.py",
]


def test_forge_tier_follows_the_ast_extraction_protocol():
    """The #556 pre-release fix for the AST extraction protocol, update part, through the recipe runner (W2
    handoff): detect-changes Category B runs skf-extract-public-api.py --mode full once over the files to extract,
    re-extract reads its output and never runs it again, §0a runs it over its own file set, and the workers read by
    eye only the forms the recipes leave out."""
    text = _read(RE_EXTRACT)
    assert yaml.safe_load(_frontmatter(text))["extractPublicApiProbeOrder"] == EXTRACT_PUBLIC_API_PATHS
    category_b = _slice(_read(DETECT), "**Category B: export-level changes.**", "**Category C")
    call = _fence(category_b, "uv run {extractPublicApiHelper} --mode full")
    for token in ('--source-root "{source_root}"', '--files-from "{run_dir}/extract-files.json"',
                  '[--language "{language}"]', '[--scope-type "{scope_type}"]', "--head-cap 0",
                  '-o "{run_dir}/extraction.json"'):
        assert token in call, token
    # Category A applied the scope: with --brief the runner would skip a tracked file the scope now leaves out
    assert "--brief" not in call and "It takes no `--brief`" in category_b
    for token in ("`--head-cap 0` keeps every match", "Step 3 reads this file and never runs the runner again",
                  "**Exit 1** (`incomplete`): run it once more",
                  "**Exit 2 or 3, no JSON, no candidate resolves, or Quick tier:**",
                  "Tell the user which files were read by eye"):
        assert token in category_b, token
    one_b = _slice(text, "### 1b. Determine Extraction Strategy by Tier", "### 2. Extract Changed Files")
    forge = _slice(one_b, "**Forge tier (AST structural extraction):**", "**Tier degradation handling")
    assert "uv run {extractPublicApiHelper}" not in forge and "never run it again here" in forge
    for token in ("take their file's exports from its `exports[]`", "copied, never inferred",
                  "an export a file defines in a form Known Limitation #11 in `{extractionPatternsData}` lists",
                  "a file `file_issues[]` names", "`entry_point_diff.extraction_gaps[]`",
                  "Step 2 already read those of the modified and added files into `{run_dir}/export-details.json`",
                  "its parameter types and return type unless `{run_dir}/export-details.json` holds them"):
        assert token in forge, token
    # the hand-run protocol and its cap dance are gone: the runner runs every recipe
    for gone in ("Run the **AST Extraction Protocol**", "run it again with a higher cap", "500", "metaVariables",
                 "range.start.line", "--json", "the decision tree based on the number of changed files"):
        assert gone not in forge, gone
    tool = _slice(one_b, "**Tool resolution:**", "\n")
    assert "`{extractPublicApiHelper}` `--mode full` (step 2 and §0a)" in tool
    assert "`find_code` only as the fallback of Known Limitation #4" in tool
    assert "find_code_by_rule" not in tool
    two = _slice(text, "### 2. Extract Changed Files", "### 2b.")
    assert 'cat > "{run_dir}/extract-files.json"' not in two  # step 2's helper wrote the list
    assert ("For each file `{run_dir}/extract-files.json` lists (step 2 wrote it: the MODIFIED and ADDED files and "
            "each MOVED file's new path)") in two
    worker = _slice(text, "launch a subprocess that:", "3. Extract each export")
    assert ("2. At Forge tier and above, takes this file's exports from step 2's `{run_dir}/extraction.json` and "
            "`export-details.json` (§1b); at Quick tier, matches the file's text as §1b says") in worker
    zero_a = _slice(text, "### 0a. Targeted Re-Extraction Branch", "### 1. Check for Docs-Only Mode")
    own = _fence(zero_a, "uv run {extractPublicApiHelper} --mode full")
    for token in ('--files-from "{run_dir}/remediation-files.json"', '[--scope-type "{scope_type}"]', "--head-cap 0"):
        assert token in own, token
    # a test report may name a file the brief's scope leaves out as an export's home
    assert "--brief" not in own and "It takes no `--brief`" in zero_a
    assert "On exit 1 (`incomplete`) run it once more" in zero_a
    init = _slice(_read(INIT), "**Check metadata.json exists:**", "**Detect skill")
    assert "`scope_type` and `language` (when present)" in init
    assert "Follow the AST Extraction Protocol in" not in zero_a


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_documented_runner_calls_run(tmp_path):
    """detect-changes Category B's runner call and re-extract §0a's run as written (W2 handoff).

    Category B passes no brief: a tracked file the brief's scope now excludes (rule R1's rescope) keeps its
    exports, which a run with the brief would drop and the diff would then read as deleted.
    """
    src = tmp_path / "src tree"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    (src / "pkg" / "hidden.py").write_bytes(b"def kept():\n    return 1\n")
    (src / "internal").mkdir()
    (src / "internal" / "impl.py").write_bytes(b"def hidden_home():\n    return 1\n")
    forge = tmp_path / "forge"
    (forge / "lib").mkdir(parents=True)
    (forge / "lib" / "skill-brief.yaml").write_bytes(yaml.safe_dump(
        {"language": "python", "scope": {"include": ["pkg/**"], "exclude": ["pkg/hidden.py"]}}).encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "extract-files.json").write_bytes(json.dumps(["pkg/api.py", "pkg/hidden.py"]).encode("utf-8"))
    (run_dir / "remediation-files.json").write_bytes(json.dumps(["internal/impl.py"]).encode("utf-8"))
    values = {"source_root": str(src), "forge_data_folder": str(forge), "skill_name": "lib",
              "run_dir": str(run_dir), "scope_type": "full-library", "language": "python"}
    calls = {
        "extraction.json": _fence(_slice(_read(DETECT), "**Category B: export-level changes.**", "**Category C"),
                                  "uv run {extractPublicApiHelper}"),
        "remediation-exports.json": _fence(_slice(_read(RE_EXTRACT), "### 0a.", "### 1. Check"),
                                           "uv run {extractPublicApiHelper}"),
    }
    expected = {
        # the line of the name, not of the decorator above it; the excluded file's export is kept
        "extraction.json": {("search", "pkg/api.py", 5), ("kept", "pkg/hidden.py", 1)},
        # out of the brief's scope, and still read: §0a passes no --brief
        "remediation-exports.json": {("hidden_home", "internal/impl.py", 1)},
    }
    for output, call in calls.items():
        proc = subprocess.run([sys.executable, str(EXTRACT_PUBLIC_API),
                               *_call_args(call, "extractPublicApiHelper", values)],
                              capture_output=True, encoding="utf-8")
        assert proc.returncode == 0, (output, proc.stderr)
        exports = json.loads((run_dir / output).read_text(encoding="utf-8"))["exports"]
        assert {(e["export_name"], e["source_file"], e["source_line"]) for e in exports} == expected[output]


# --------------------------------------------------------------------------
# Gap-driven spot-checks: the drift override and a cited new export
# --------------------------------------------------------------------------


def _zero_a() -> str:
    return _slice(_read(RE_EXTRACT), "**0.a Pre-flight", "1. Use the provenance map")


def _write_3() -> str:
    return _slice(_read(WRITE), "### 3. Write Updated provenance-map.json", "### 4.")


DRIFT_NOTE = "(drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha}"
NEW_ENTRY_BULLET = "- **`verified` or `moved` on a cited export the map does not hold, flagged `NEW_EXPORT` for merge**"


def test_drift_status_binding_and_warning():
    """Step 3 §0.a binds the status and both short SHAs; only `overridden` changes later steps (#530)."""
    zero_a = _zero_a()
    assert "Bind `{workspace_drift_status}` ← `status`" in zero_a
    assert "`{head_short_sha}` ← `head_short_sha`" in zero_a
    assert "`{pinned_short_sha}` ← the first 7 characters of `metadata.source_commit`" in zero_a
    # the flag with HEAD at the pinned commit (`ok`) moves lines as usual
    assert "`ok` (HEAD holds the pinned commit, with or without the flag) and `skipped` change nothing" in zero_a
    overridden = _slice(zero_a, "- **`overridden`** (helper exit 0):", "\n")
    # the helper emits a full `pinned_commit`; the warning names the short SHAs §0.a binds
    assert "{pinned_commit}" not in overridden
    assert ("add `workspace_drift_overridden: HEAD {head_short_sha} is not pinned {pinned_short_sha}` "
            "to `warnings[]`") in overridden
    # one override text: the report's Mode row shows it
    assert "report.md §2's Mode row is where the report shows it" in overridden
    assert "Workspace drift accepted via" not in overridden
    assert "Then run the drift gate below, and continue to bullet 1 only when it passes." in overridden
    assert "\u2014" not in overridden
    # a helper that fails, prints no JSON or returns another status leaves the status unbound: halt
    other = _slice(zero_a, "- **Any other result**", "\n")
    for token in ("prints no JSON", "returns a status not listed above", "HALT with status `blocked`",
                  'phase: "re-extract:workspace-drift"', "drift-check-failed"):
        assert token in other, token


DRIFT_GATE = "**Drift gate (only when `{workspace_drift_status}` is `overridden`).**"
GATE_REASONS = ["a public API recount from the tree (rule R1)", "a line from the tree (rule R3)",
                "a line and a signature from the tree", "a signature from the tree"]


def _drift_gate() -> str:
    return _slice(_read(RE_EXTRACT), DRIFT_GATE, "\n1. Use the provenance map")


def test_drift_gate_halts_before_merge_on_every_new_or_modified_export():
    """Under the override every new or modified export halts in step 3, before merge (#530, #557)."""
    text = _read(RE_EXTRACT)
    gate = _drift_gate()
    for token in ("update-skill writes nothing read there, neither a provenance line nor a signature, parameter "
                  "list, return type or node kind",
                  "Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the "
                  "provenance map holds the export",
                  "merge Priority 4 replaces a modified export's content with a fresh extraction",
                  "merge Priority 5 appends a new export's content",
                  "HALT with status `halted-for-workspace-drift` before merge runs",
                  "merge writes nothing and §0a never runs",
                  "A rescope's amendment, which step 2 wrote to the skill brief (rule R1), stays there",
                  "Every `DELETED_EXPORT` needs the tree as well: in gap-driven mode it is a rescope (rule R1)",
                  'phase: "re-extract:workspace-drift"'):
        assert token in gate, token
    # severity and the map no longer decide whether an entry halts: the #551 conditions are gone
    for gone in ("an export the map holds needs no new line",
                 "a non-empty `remediation_paths[]` and a blocking severity",
                 "Gaps that need a line:", "{rule R3 | remediation paths | cited export not in the map}"):
        assert gone not in gate, gone
    assert re.findall(r"^- `([^`]+)`: ", gate, re.M) == GATE_REASONS
    # the gap §0a would halt with nothing to scan halts here first under the override (#558 item 4)
    assert "under the override this gate halts on it first" in gate
    message = _fence(gate, "Workspace drift blocks {N} gap(s)")
    for token in ("Workspace drift blocks {N} gap(s) that need the pinned tree.",
                  "writes nothing read at HEAD: no provenance line, signature, parameter list,\n"
                  "return type or node kind.",
                  "Gaps that need the pinned tree:",
                  '({change_category}, {severity or "no severity"})',
                  "{" + " | ".join(GATE_REASONS) + "}",
                  "pinned (metadata.source_commit): {source_commit}",
                  "{if source_ref is set: pinned ref (metadata.source_ref): {source_ref}}",
                  'a) Check out the pinned commit: git -C "{source_root}" checkout {source_commit}',
                  "Run a normal update (without --from-test-report)"):
        assert token in message, token
    headless = _slice(gate, "In `{headless_mode}`", "\n")
    assert 'reason: "drift-override: {N} gap(s) need the pinned tree: {name} ({reason}), ...' in headless
    # the gate runs before any spot-check, and §0a says it never runs under the override
    assert text.index("**Drift gate") < text.index("1. Use the provenance map") < text.index("### 0a.")
    used_by = _slice(text, "**Used by:** §0 bullet 2", "**Purpose:**")
    assert "Never under the drift override (`{workspace_drift_status}` is `overridden`)" in used_by
    four = _slice(text, "4. Set `no_reextraction: true`", "\n")
    assert "a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` entry at that line" in four
    assert ("a spot-check that would move one records `unknown` with `unknown_reason: drift-override`, and §0.a's "
            "drift gate has already halted on every `NEW_EXPORT` and `MODIFIED_EXPORT`, so §0a never runs") in four
    zero_a = _zero_a()
    # what the override keeps out, by name: write §2 still counts the public surface at `{source_root}`
    assert ("so update-skill takes no provenance line, signature, parameter list, return type or node kind "
            "from it") in zero_a
    assert "takes nothing from it" not in zero_a
    assert "write.md §2 and §6a look up no node kind there" in zero_a
    assert "lines move and node kinds are looked up as usual" in zero_a


def test_every_change_category_halts_or_passes_the_drift_gate():
    """Each category detect-changes can emit is named once by the gate: as one that halts or one that passes (#557)."""
    bullet = _slice(_read(DETECT), "   - **`change_category`**", "\n")
    categories = re.findall(r"`([A-Z_]+|metadata update)`", bullet)
    assert categories == ["NEW_EXPORT", "MODIFIED_EXPORT", "MOVED_EXPORT", "DELETED_EXPORT", "STRUCTURAL_FIX",
                          "metadata update"]
    gate = _drift_gate()
    halts = _slice(gate, "Every `NEW_EXPORT`", " needs it,") + _slice(gate, "Every `DELETED_EXPORT`", " needs the tree")
    passes = _slice(gate, "A rule R5 `MOVED_EXPORT`", " need nothing from the tree and pass.")
    for category in categories:
        token = f"`{category}`"
        assert (token in halts) != (token in passes), category
    assert "`NEW_EXPORT`" in halts and "`MODIFIED_EXPORT`" in halts and "`DELETED_EXPORT`" in halts


def test_merge_says_no_new_or_modified_export_arrives_under_the_override():
    """Merge Priority 1, 4 and 5 state the route under the override: the drift gate halted first (#557)."""
    merge = _read(MERGE)
    one = _slice(merge, "**Priority 1", "**Priority 2")
    assert "no `DELETED_EXPORT` reaches this priority: step 3's drift gate halted on every rescope" in one
    four = _slice(merge, "**Priority 4", "**Priority 5")
    assert "no `MODIFIED_EXPORT` reaches this priority" in four
    assert "could only be read at HEAD, so step 3's drift gate halted on it before merge" in four
    five = _slice(merge, "**Priority 5", "**Priority 6")
    assert "no `NEW_EXPORT` reaches this priority either" in five
    assert "whatever its severity and whether the provenance map holds it" in five


def test_relabel_runs_no_recipe_under_the_override():
    """write §2 looks up no node kind at HEAD: the violation stays, with a WARN that names the drift (#557)."""
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    relabel = _slice(two, "**Label violations.**", "\n")
    drift = _slice(relabel, "**Under the drift override**", "When the run cannot tell")
    for token in ("run no recipe at `{source_root}`, so no `kind-at`",
                  "Leave each violation that needs a kind from the tree in place",
                  "list it as a WARN ending ` " + DRIFT_NOTE + ")`",
                  "a relabel that reads nothing from the tree still applies",
                  "With the status `ok` or `skipped`, run the lookup as above"):
        assert token in drift, token
    # the gate follows the lookup it gates, and the re-run keeps the shape (#550)
    assert relabel.index("kind-at --source-root") < relabel.index("**Under the drift override**")
    assert "re-run the helper with the same payload and `--shape`" in relabel


def test_name_lookup_filters_by_the_citation_file():
    """Same-name entries: the citation's normalized file, then its line, pick one; none left is not found (#530)."""
    lookup = _slice(_read(RE_EXTRACT), "   - Look up the export in the provenance map's `entries[]`", "\n")
    for token in ("take the entries whose `export_name` equals the name",
                  "**With a `source_citation`,** keep those whose `source_file`, normalized as write.md §6a",
                  "(a leading `./` dropped, backslashes turned to `/`)",
                  "One left: the export is found.",
                  "Several left: take the one whose `source_line` equals the citation's line, or else record "
                  "`unknown` and leave them as they are.",
                  "None left: take the \"not found\" branch below.",
                  "**Without a `source_citation`,** exactly one entry means the export is found; several record "
                  "`unknown`",
                  "none takes the \"not found\" branch"):
        assert token in lookup, token
    assert "When none matches, or the entry has no `source_citation`" not in lookup


def test_spot_checks_move_and_pin_no_line_under_the_override():
    """A drifted HEAD moves no line and pins none, and each drift `unknown` says why (#530)."""
    text = _read(RE_EXTRACT)
    outcome = _slice(text, "   - Record verification outcome:", "\n")
    moved = _slice(outcome, "`moved` (the file defines", "`missing` (")
    assert ("when `{workspace_drift_status}` is `overridden` (§0.a), record `unknown` with "
            "`unknown_reason: drift-override` instead and set no `new_location`") in moved
    assert "with `unknown_reason: drift-override`, a `moved` the drift override turned into `unknown`" in outcome
    assert "a cited `NEW_EXPORT` it kept from being spot-checked" not in outcome  # the gate halts those now (#557)
    # an R5 line that defines the export at HEAD stays verified, but never closes silently
    verified = _slice(outcome, "`verified` (the recorded", "`moved` (the file")
    assert "under the drift override a rule R5 `MOVED_EXPORT` still records `verified`" in verified
    assert "write.md §3 lists a drift WARN for it" in verified
    moved_export = _slice(text, "   - **If the entry is `MOVED_EXPORT`", "\n")
    assert "it records `unknown` with `unknown_reason: drift-override` where it would record `moved`" in moved_export
    assert "Record in `pinned_definition_lines` the definition lines its `remediation` lists" in moved_export
    cited = _slice(text, "     - **If the manifest entry has a `source_citation`", "\n")
    drift = "under the drift override (`{workspace_drift_status}` is `overridden`, §0.a) no entry reaches this branch"
    assert drift in cited
    assert cited.index(drift) < cited.index("Otherwise run the \"export found\" branch's `definition-lines` call")
    assert "the §0.a drift gate halted on every `NEW_EXPORT` and `MODIFIED_EXPORT` before bullet 1" in cited
    assert "unknown_reason: drift-override" not in cited  # no cited export is kept from its spot-check any more
    assert "so step 6 writes" not in cited and "write.md §3 adds a full entry" in cited
    # the reachability gate reads barrels: under the override no new export reaches it (#557)
    gate = _slice(text, "   - **Public-reachability gate (`NEW_EXPORT` only):**", "\n")
    reach = gate[gate.index("**Under the drift override**"):]
    assert "no entry reaches this gate" in reach
    assert "halted on every `NEW_EXPORT` and `MODIFIED_EXPORT` before bullet 1" in reach
    assert "reachability: not-checked" not in text and "`not-checked`" not in _write_3()
    record = _fence(text, "Per-export verification:")
    for field in ("unknown_reason: drift-override", "pinned_definition_lines:"):
        assert field in record, field
    breakdown = _slice(record, "confidence_breakdown:", "T2: 0")
    assert ("each cited export not in the map that the spot-check pinned and the public-reachability gate passed"
            in _slice(breakdown, "T1-low:", "\n"))
    assert ("other than a pinned cited export that passed the reachability gate (counted under T1-low)"
            in _slice(breakdown, "unlabeled:", "\n"))
    summary = _slice(text, '"**Gap-driven re-extraction.**', "\n")
    assert summary.endswith("or a line the drift override kept from being moved): {unknown_count}.\"")
    qualifier = _slice(text, "When `{workspace_drift_status}` is `overridden`, add: \"Every check read HEAD", "\n")
    assert "no line was moved or pinned.\"" in qualifier and "reachability" not in qualifier
    assert text.index('"**Gap-driven re-extraction.**') < text.index(qualifier)
    assert "`provenance_map.exports`" not in text
    r5 = _slice(_read(DETECT), "- **R5: MOVED_EXPORT", "\n")
    assert "it records `unknown` in place of `moved`" in r5
    assert "a drift WARN that carries the definition lines this gap's remediation lists" in r5
    # merge moves citations only for a `moved` outcome
    priority2 = _slice(_read(MERGE), "**Priority 2", "**Priority 3")
    assert "move citations only for an export whose step 3 §0 spot-check recorded `moved`" in priority2
    assert "`MOVED_EXPORT` that recorded `unknown` (the drift override among the causes), `verified` or `missing` moves none" in priority2


def test_write_adds_the_cited_export_entry_and_names_the_drift():
    """write §3 adds one entry per pinned cited export; every WARN under the override names the drift (#530)."""
    three = _write_3()
    bullet = _slice(three, NEW_ENTRY_BULLET, "\n")
    for token in ("a `NEW_EXPORT` or `MODIFIED_EXPORT` gap", "add one entry",
                  "only for an export that passed step 3's public-reachability gate",
                  "at most one per `export_name` and `source_file`, however many manifest entries pin it",
                  "set source_library as create-skill's entry contract does",
                  "to the citation for `verified`, or to `new_location` for `moved`",
                  "`confidence: T1-low`", "`extraction_method: source-read`", "`ast_node_type: null`",
                  "`signature_source: T1-low`",
                  "take `export_type` from step 4's merge output, or from the spot-check's read of that line",
                  "§2's stats helper pairs `source-read` with these labels"):
        assert token in bullet, token
    assert "the only labels" not in bullet and "no ast-grep rule matched" not in bullet
    assert ("Under the drift override no such record reaches this bullet: step 3's drift gate halted on every "
            "`NEW_EXPORT` and `MODIFIED_EXPORT` before merge.") in bullet
    verified = _slice(three, "- **`verified` exports the map already holds**", "\n")
    assert ("`{export_name}: verified at HEAD only " + DRIFT_NOTE +
            "; definition lines per the test report: {pinned_definition_lines})`") in verified
    # no drift `unknown` reaches the `unknown` bullet any more: the gate halts every new export first (#557)
    unknown = _slice(three, "- **`unknown` exports**", "\n")
    assert "under the drift override step 3's drift gate halts on every `NEW_EXPORT` first" in unknown
    assert "unknown_reason" not in unknown and "no line taken from HEAD" not in unknown
    left = _slice(three, "- **`missing` exports,", "\n")
    assert "When `{workspace_drift_status}` is `overridden`" in left
    assert "`{export_name}: {outcome} " + DRIFT_NOTE + ")`" in left
    assert ("For a record whose `unknown_reason` is `drift-override` (a `moved` the override turned into "
            "`unknown`), add `{export_name}: unknown " + DRIFT_NOTE + "; no line taken from HEAD)`") in left
    assert "is the `unknown` bullet's" not in left
    assert "a cited `NEW_EXPORT` it kept from being spot-checked" not in left
    assert ("end its WARN with `; definition lines per the test report: {pinned_definition_lines}` from its step 3 "
            "record") in left
    assert "they apply only while that is still the skill's current source commit" in left
    assert "{source_commit}" not in left and "{lines}" not in left
    assert "- **Any record whose `reachability` is `not-checked`**" not in three
    write = _read(WRITE)
    six_a = _slice(write, "### 6a.", "### 6b.")
    assert "Pass `--no-line-moves` when `{workspace_drift_status}` is `overridden`" in six_a
    drift_6a = _slice(six_a, "**Under the drift override** (`{workspace_drift_status}` is `overridden`, step 3 §0.a)",
                      "\n")
    for token in ("end the `Provenance:` line of the Validation Summary", "`file-missing`, `line-out-of-bounds`",
                  "an unverified export or a finding `fix` left as `line-moves-skipped`", DRIFT_NOTE):
        assert token in drift_6a, token
    assert "allow_workspace_drift" not in write
    priority5 = _slice(_read(MERGE), "**Priority 5", "**Priority 6")
    assert "cite it as `[SRC:{source_file}:L{line}]`" in priority5


def test_new_entry_labels_pass_the_stats_helper():
    """The labels write §3 gives a pinned cited export pass skf-render-metadata-stats.py's label check (#530)."""
    bullet = _slice(_write_3(), NEW_ENTRY_BULLET, "\n")
    labels = dict(re.findall(r"`(confidence|extraction_method|ast_node_type|signature_source): ([^`]+)`", bullet))
    assert labels == {"confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": "null",
                      "signature_source": "T1-low"}
    spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_prose", STATS_HELPER)
    stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stats)
    entry = {"export_name": "search", "export_type": "function", "source_library": "cognee",
             "source_file": "cognee/api/v1/search/search.py", "source_line": 27,
             **{key: None if value == "null" else value for key, value in labels.items()}}
    assert stats.check_label_agreement({"entries": [entry]}) == []


def test_report_shows_the_override_once():
    """The Mode row is the report's one override text; §5b names the warning and the spot-check WARNs (#530)."""
    report = _read(REPORT)
    two = _slice(report, "### 2. Present Change Summary", "### Changes Applied")
    row = _slice(two, "- `re-extract.md §0.a` accepted a drifted workspace", "\n")
    assert "this row is where the report shows §0.a's override warning" in row
    assert ("(workspace drift accepted: spot-checks read HEAD {head_short_sha}, not pinned {pinned_short_sha}; "
            "no provenance line moved or pinned)") in row
    assert "WARN, provenance entry left for a person to decide (write.md §3)" in report
    five_b = _slice(report, "### 5b. Result Contract", "### 6.")
    assert "`workspace_drift_overridden` (re-extract.md §0.a)" in five_b
    assert "spot-check entries §3 left for a person to decide" in five_b and "left unchanged" not in five_b


def _doc_line(name: str, *needles: str) -> str:
    """The one line of docs/{name} that holds every needle."""
    lines = [line for line in _read(REPO_ROOT / "docs" / name).splitlines() if all(n in line for n in needles)]
    assert len(lines) == 1, (name, needles, len(lines))
    return lines[0]


def test_override_is_described_where_the_flag_is():
    """init.md, SKILL.md and the docs say the override moves or pins no line and halts on gaps that need one.

    init.md and both docs pages also say it takes no signature, parameter list, return type or node kind from
    HEAD, so every new or modified export halts, whatever its severity, and SKILL.md gives the flag one clause
    (#557).
    """
    init = _slice(_read(INIT), "- `--allow-workspace-drift` (gap-driven mode only)", "\n")
    assert "moves or pins no provenance line read there" in init and "halted-for-workspace-drift" in init
    for token in ("update-skill takes nothing from HEAD",
                  "reads no signature, parameter list, return type or node kind there",
                  "which every new or modified export does"):
        assert token in init, token
    # SKILL.md gives the caller one clause; re-extract.md §0.a holds what the override keeps out
    flags = _slice(_read(SKILL), "| **Flags** |", "\n")
    for token in ("update-skill takes nothing from HEAD",
                  "a gap that needs the pinned tree, a rescope included, halts `halted-for-workspace-drift` before "
                  "merge"):
        assert token in flags, token
    # the docs say it in their own words; the #551 wording, under which only a gap that needed a line halted, is gone
    gap_driven = ("`--allow-workspace-drift`", "Update Skill with `--from-test-report`")
    verifying = _doc_line("verifying-a-skill.md", *gap_driven)
    workflows = _doc_line("workflows.md", *gap_driven)
    for doc in (verifying, workflows):
        for token in ("takes nothing from", "provenance line", "signature, parameter list, return type or node kind",
                      "new or changed export", "whatever its severity", "`halted-for-workspace-drift`",
                      "before it changes the skill"):
            assert token in doc, token
    assert "a gap that needs a line from the source" not in verifying
    assert "stops on a gap that needs one" not in workflows
    # the reports verifying-a-skill.md says still run hold only categories the drift gate lets through; removed
    # exports stay out, as the gate halts on a rescope once write.md §2 keeps the recorded public API counts
    gate = _drift_gate()
    end = gate.index(" need nothing from the tree and pass.")
    passes = gate[gate.rindex(". ", 0, end) + 2:end]
    still_runs = _slice(verifying, "A report whose gaps are only", " still runs")
    for category, words in (("MOVED_EXPORT", "provenance line fixes"), ("STRUCTURAL_FIX", "structural fixes"),
                            ("metadata update", "metadata patches")):
        assert f"`{category}`" in passes and words in still_runs, category
    assert "removed exports" not in still_runs
    for text in (init, flags, verifying, workflows):
        assert "\u2014" not in text


def test_docs_say_a_rescope_halts_under_the_override():
    """Both docs pages say a rescope halts under the override, as re-extract.md's drift gate does (#557).

    Its public API recount needs the pinned tree, the brief amendment stays and the message names it, and a run
    that still goes ahead keeps the public API counts metadata.json records.
    """
    gate = _drift_gate()
    assert "- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);" in gate
    assert "A rescope's amendment, which step 2 wrote to the skill brief (rule R1), stays there, and the message " \
           "names it" in gate
    assert "write.md \u00a72 keeps the public API counts metadata.json records" in _zero_a()
    gap_driven = ("`--allow-workspace-drift`", "Update Skill with `--from-test-report`")
    for name in ("verifying-a-skill.md", "workflows.md"):
        line = _doc_line(name, *gap_driven)
        rescope = _slice(line, "A rescope (", "the message names it")
        for token in ("stops", "the same way", "public API", "needs the pinned tree", "amendment", "already wrote"):
            assert token in rescope, (name, token)
        assert "the stats keep the public API counts `metadata.json` records" in line, name


# --------------------------------------------------------------------------
# Gap-driven routing: blocking gaps with no path, split-body findings
# --------------------------------------------------------------------------

BLOCKING_RULE = ("blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or "
                 "unrecognized one is blocking, like `Critical` and `High`")


def _not_found() -> str:
    return _slice(_read(RE_EXTRACT), "   - **If export not found in provenance map:**", "   - **If export found:**")


def test_one_severity_rule_in_detect_re_extract_and_write():
    """A missing or unrecognized severity is blocking wherever a gap is routed by severity (#558 item 5)."""
    severity = _slice(_read(DETECT), "   - **`severity`**", "\n")
    assert "A severity is " + BLOCKING_RULE in severity
    assert "only a `Medium`, `Low` or `Info` gap may degrade to `unknown`" in severity
    assert "a `severity` is " + BLOCKING_RULE in _not_found()
    text = _read(RE_EXTRACT)
    assert "`severity` is `Critical` or `High`" not in text  # the test a missing severity slipped through
    used_by = _slice(text, "**Used by:** §0 bullet 2", "**Purpose:**")
    assert "a blocking `severity` (anything but `Medium`, `Low` or `Info`, a missing one included)" in used_by
    # the prose around §0a states the same rule, an unrecognized severity included
    for gone in ("citation-less Critical/High", "the Critical/High HALT",
                 "Critical and High gaps, and gaps with no severity"):
        assert gone not in text, gone
    rule = "any severity but `Medium`, `Low` or `Info`, a missing or unrecognized one included"
    assert rule in _slice(text, "**Exception (gap-driven mode):**", "\n")
    assert rule in _slice(text, "**Purpose:**", "\n")
    template = " ".join(_fence(text, "Targeted re-extraction failed for {N} gap(s).").split())
    assert ("A blocking gap (any severity but Medium, Low or Info, a missing or unrecognized one included) must "
            "resolve to AST provenance.") in template
    why = _slice(text, "**Why halt instead of degrading to `unknown`:**", "\n")
    assert "a gap with a missing or unrecognized severity counts as blocking" in why
    unknown = _slice(_write_3(), "- **`unknown` exports**", "\n")
    assert "a `severity` of `Medium`, `Low` or `Info`, compared case-insensitively" in unknown
    assert "(a blocking severity, a missing one included)" in unknown


def test_blocking_gap_without_a_path_halts_in_step_3_before_merge():
    """No citation that pins a line and no path in the Remediation: §0a lists it with files_scanned 0 (#558)."""
    text = _read(RE_EXTRACT)
    not_found = _not_found()
    cited = _slice(not_found, "     - **If the manifest entry has a `source_citation`", "\n")
    blocking = _slice(not_found, "     - **If the manifest entry has no `source_citation` (or one whose spot-check "
                      "above pinned no line) and a blocking `severity`", "\n")
    unknown = _slice(not_found, "     - **If the manifest entry has no `source_citation` (or one whose spot-check "
                     "above pinned no line), is not a provenance-completeness gap, and its `severity` is `Medium`, "
                     "`Low` or `Info`:**", "\n")
    # a citation that pins no line goes on to the two branches, in this order
    assert "go on to the branches below as if the entry had no `source_citation`" in cited
    assert not_found.index(cited) < not_found.index(blocking) < not_found.index(unknown)
    for token in ("the rule R3 branch above did not take it",
                  "Route this entry to §0a (Targeted Re-Extraction Branch), whatever its `resolved_paths[]`",
                  "With an empty list it has nothing to scan and lists the entry in `unresolved[]` with "
                  "`files_scanned: 0`",
                  "halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included"):
        assert token in blocking, token
    assert "a blocking gap never gets here, whatever its `resolved_paths[]`" in unknown
    assert "`remediation_paths[]` is empty OR" not in text  # the empty-paths way into `unknown` is gone
    zero_a = _slice(text, "### 0a. Targeted Re-Extraction Branch", "### 1. Check for Docs-Only Mode")
    used_by = _slice(zero_a, "**Used by:** §0 bullet 2", "**Purpose:**")
    assert ("an empty one leaves nothing to scan, so step 4 puts the entry straight into `unresolved[]` with "
            "`files_scanned: 0`") in used_by
    assert "that the rule R3 case below does not take" in used_by
    assert "gap-driven runs in which §0 bullet 2 routes no entry here, skip this section entirely" in zero_a
    match = _slice(zero_a, "4. **Match by name**", "\n")
    assert "An entry with no path set to scan (an empty `resolved_paths[]`) is not matched" in match
    assert "search the extraction results of its own `resolved_paths[]`" in match
    # a rule R3 gap scans the source file its documentation cites, which step 2 resolved through the helper
    r3 = _slice(used_by, "- a provenance-completeness gap (rule R3", "\n")
    assert ("Its `resolved_paths[]` is the path set to scan: step 2 §0 filled them from the source file its "
            "documentation cites when its remediation named none") in r3
    failures = _slice(zero_a, "5. **Track failures across all qualifying entries.**", "\n")
    assert "every entry step 4 had nothing to scan for (`files_scanned: 0`)" in failures
    template = _fence(zero_a, "Targeted re-extraction failed for {N} gap(s).")
    for token in ('- {name} ({severity or "no severity"})', 'remediation_paths: {paths, or "none named"}',
                  'rejected_paths:    {each refused path (its reason), or "none"}',
                  "files_scanned:     {count}", "a) Add a `file:line` citation", "b) Edit the Remediation text",
                  "c) Downgrade the gap(s) to Medium/Low/Info"):
        assert token in template, token
    exit_ = _slice(zero_a, "   Exit with status `halted-for-remediation-path`", "\n")
    for token in ("under `--dry-run` too", "Step-04 merge has not run; no partial writes",
                  'phase: "re-extract:targeted-reextraction"'):
        assert token in exit_, token
    # detect-changes lists the fields the route reads; re-extract states the route once, where it acts
    paths = _slice(_read(DETECT), "   - **`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**", "\n")
    assert "Step 3's §0a scans only `resolved_paths`" in paths
    for gone in ("depending on severity", "halts the run with `halted-for-remediation-path`", "records `unknown`"):
        assert gone not in paths, gone


def test_gap_driven_dry_run_stops_after_step_3():
    """§0 bullet 5 hands off through §6, so a gap-driven --dry-run never loads merge (#558 item 6)."""
    text = _read(RE_EXTRACT)
    five = _slice(text, "5. **Skip sections 1–5 of step 3**", "\n")
    for token in ("then go straight to §6 (Route to Next Step), whose branches hold in gap-driven mode too",
                  "with `dry_run_mode` true it loads `report.md` (status `dry-run`) and never merge.md",
                  "A halt in this section (the drift gate, §0a) stops a `--dry-run`"):
        assert token in five, token
    assert "Skip all remaining sections of step 3" not in text
    six = _slice(text, "### 6. Route to Next Step", "\n- **Otherwise**")
    assert "load `report.md` (NOT `{nextStepFile}`)" in six
    assert "Proceeding to merge" not in _slice(text, '"**Gap-driven re-extraction.**', "\n")  # §6 says where next
    halt = "a re-extract halt such as `halted-for-remediation-path` or `halted-for-workspace-drift` still stops it"
    assert halt in _slice(_read(SKILL), "| **Flags** |", "\n")
    assert halt in _slice(_read(INIT), "- `--dry-run` to run detect-changes + re-extract", "\n")


def test_write_keeps_a_documented_defensive_halt():
    """A blocking `unknown` that still reaches write §3 halts with a documented status and phase (#558).

    `halted-for-remediation-path` tells a pipeline nothing was written; this halt comes after merge rewrote
    SKILL.md in place, so it takes `blocked`, the schema's status for a halt with no code of its own.
    """
    unknown = _slice(_write_3(), "- **`unknown` exports**", "\n")
    assert "**This path is only for `Medium`, `Low` or `Info`.**" in unknown
    halt = unknown[unknown.index("If one does (step 3 was skipped or bypassed)"):]
    for token in ("HALT with status `blocked`", "write no `metadata.json`, `provenance-map.json` or other artifact",
                  'phase: "write:provenance-map"', 'path: "{forge_version}/provenance-map.json"',
                  "blocking-gap-unresolved",
                  # merge Priority 5 and 8 may have edited reference files too
                  "This repair edited SKILL.md and references/ in place: restore them from version control or a "
                  "backup"):
        assert token in halt, token
    assert "halt with a pointer to §0a" not in unknown  # the old halt named no status
    status = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["status"]["enum"]
    assert "blocked" in status and "halted-for-remediation-path" in status


def test_split_body_findings_route_to_a_structural_fix():
    """A Source inside the skill package marks a split-body finding: STRUCTURAL_FIX, never MODIFIED_EXPORT (#547)."""
    zero = _slice(_read(DETECT), "### 0. Check for Test Report Input", "### 1. Scan Current Source State")
    rows = [line for line in zero.splitlines() if line.startswith("| ")]
    split = next(i for i, row in enumerate(rows) if "Split-body inconsistency" in row)
    signature = next(i for i, row in enumerate(rows) if "`signature-mismatch`" in row)
    assert split < signature  # read top-down, the split-body row comes first
    assert rows[split].startswith("| `split-body-mismatch` | Split-body inconsistency:")
    assert "with a `Source:` inside the skill package" in rows[split]
    assert ("STRUCTURAL_FIX, see rule R2 (for an older report, this row takes precedence over the Signature mismatch "
            "row below)") in rows[split]
    assert "MODIFIED_EXPORT" not in rows[split]
    r2 = _slice(zero, "- **R2: STRUCTURAL_FIX.**", "\n- **R3")
    for token in ("a coherence finding from `skf-scan-skill-md-structure.py`",
                  "a split-body consistency finding (test-skill coverage-check §1b `cross_check_mismatches`)",
                  "Its `category` is `split-body-mismatch`; in a report older than the ledger, recognize it by its "
                  "`Source:`, which points inside the skill package",
                  "at the skill's own `SKILL.md` or at one of its `references/*.md` files",
                  "while its issue sets the SKILL.md body against a `references/*.md` file",
                  "Test for it before the High \"Signature mismatch\" row",
                  "a High signature gap whose `Source:` points into the source tree, or that has no `Source:`, "
                  "stays `MODIFIED_EXPORT`",
                  "routes to merge Priority 8",
                  "it never adds, modifies, or removes a provenance `entries[]` row"):
        assert token in r2, token
    assert "\u2014" not in r2
    cite = _slice(zero, "   - **`source_citation: {file, line}`**", "\n")
    assert "or names a line inside the skill package (a split-body finding's `SKILL.md:42`, rule R2)" in cite
    # a STRUCTURAL_FIX needs nothing from the tree: forwarded as is, and the drift gate lets it through
    forward = _slice(_read(RE_EXTRACT), "   - **`STRUCTURAL_FIX`** (detect-changes §0 rule R2)", "\n")
    assert "No spot-check, no provenance lookup, no `entries[]` change." in forward
    assert "a `STRUCTURAL_FIX` (a split-body consistency finding among them)" in _drift_gate()


def test_merge_edits_the_reference_file_of_a_split_body_finding():
    """The SKILL.md body is authoritative (test-skill coverage-check §1b): merge edits the reference file (#547)."""
    priority8 = _slice(_read(MERGE), "**Priority 8 ", "**Priority 8b")
    split = _slice(priority8, "- **A split-body consistency finding**", "\n")
    for token in ("edit the `references/*.md` file so it documents the export as the SKILL.md body does",
                  "whichever of the two files the gap's `Source:` names",
                  "never change the body to match the reference file"):
        assert token in split, token
    assert "Do **not** add, modify, or remove any provenance `entries[]` row" in priority8


# --------------------------------------------------------------------------
# Write bookkeeping and reference-app stats
# --------------------------------------------------------------------------


def test_update_bookkeeping_has_one_home():
    """last_update and update_type live in one block at the top of provenance-map.json, one value per mode (#548)."""
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    assert "`generation_date` / `last_update` below" not in two
    assert "of the fields that mark an update only `generation_date` below changes" in two
    generation = _slice(two, "- Update `generation_date` timestamp", "\n")
    assert "§3's update operation block records `last_update` and `update_type` in provenance-map.json" in generation
    # a copy an older SKF version left in metadata.json goes, or it keeps an earlier update's date
    for token in ("Write neither key into metadata.json",
                  "remove a `last_update` or `update_type` an older SKF version left there",
                  "so metadata.json never keeps the date or type of an earlier update beside the map's current one"):
        assert token in generation, token
    block = _slice(_write_3(), "**Add update operation metadata**", "`manual_sections_preserved` =")
    for token in ("at the top level of `{forge_version}/provenance-map.json`, the one place an update is recorded",
                  "replacing the values an earlier update wrote, so the map holds one block, for the latest update, "
                  "never a history",
                  "Add no other update-history key",
                  "(`update_operations[]`, `update_metadata`) stays as it is",
                  "§2 writes neither `last_update` nor `update_type` into metadata.json and removes one an older SKF "
                  "version left there"):
        assert token in block, token
    # metadata.json has a `confidence_tier` of its own, the forge tier, so §3 names the two keys it must not hold
    assert "records none of these keys" not in block
    assert '"confidence_tier": "{Quick|Forge|Forge+|Deep}"' in _read(SRC / "skf-create-skill" / "assets" /
                                                                     "skill-sections.md")
    fields = json.loads(_fence(block, '"last_update"').replace("{count}", "0"))
    assert list(fields) == ["last_update", "update_type", "test_report_run_id", "files_changed", "exports_affected",
                            "confidence_tier", "manual_sections_preserved"]
    # the time to the second, read from the clock, and the report a gap-driven repair applied (#583): step 1 §4b
    # never offers that report again, even on the day of the test
    assert "read from the clock (`date -u +%Y-%m-%dT%H:%M:%SZ`), never typed" in generation
    for token in ("`last_update` is the `generation_date` §2 wrote",
                  "`test_report_run_id` the `{test_report_run_id}` of the test report a gap-driven run applied "
                  "(null in the other modes), which step 1 §4b then never offers again"):
        assert token in block, token
    values = dict(re.findall(r"([a-z-]+) if ([a-z-]+)", fields["update_type"]))
    assert values == {"incremental": "normal", "gap-driven": "gap-driven", "full": "degraded"}
    # one value for each mode the report names, and the prose names the same pairs
    modes = re.findall(r"`([a-z-]+)`", _slice(_read(REPORT), "**`{update_mode}`** is one of", "\n"))
    assert sorted(values.values()) == sorted(modes) == ["degraded", "gap-driven", "normal"]
    for value, mode in values.items():
        assert f"`{value}` for `{mode}`" in block, (value, mode)


def test_reference_app_stats_use_the_reference_app_shape():
    """write §2 passes the shape metadata.json records and the Pattern Surface row count, as compile.md §4 does.

    #550: without them the update counted citations as documented exports and dropped the pattern-surface count.
    """
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    shape = _slice(two, "  **Shape:**", "\n")
    for token in ("read `scope_type` from `{skill_package}/metadata.json` before this section rewrites it",
                  "When it is `reference-app`, pass `--shape reference-app` and put `pattern_surfaces_documented` in "
                  "the payload",
                  "pass no `--shape` (the helper's default, the library shape)",
                  "Stack Skill Guard"):
        assert token in shape, token
    payload = _slice(two, "  - `pattern_surfaces_documented` (reference app only):", "\n")
    assert "the number of rows in the `## Pattern Surface` table of the merged SKILL.md" in payload
    stats = _slice(two, "- **Compute the `stats` block", "\n")
    assert "sets `exports_documented` = the entry count for the library shape" in stats
    assert "\u2014" not in stats
    compile_ = _read(SRC / "skf-create-skill" / "references" / "compile.md")
    assert "pass `--shape reference-app`" in compile_ and "`pattern_surfaces_documented`" in compile_


def _stats_main(block: str, forge_version: Path, monkeypatch, capsys) -> tuple[int, dict]:
    """Run one of write §2's fenced helper calls, as written, through the helper's own main()."""
    payload = re.search(r"echo '(.*)' \\", block).group(1)
    for placeholder, value in (("{N}", "4"), ("{M}", "1"), ("{P}", "2"), ("{scripts-inventory-or-[]}", "[]"),
                               ("{assets-inventory-or-[]}", "[]")):
        payload = payload.replace(placeholder, value)
    # split the template, then fill it in: POSIX shlex.split would drop the backslashes of a Windows path
    argv = [arg.replace("{forge_version}", str(forge_version))
            for arg in shlex.split(block.split("uv run {renderMetadataStatsHelper}", 1)[1])]
    spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_calls", STATS_HELPER)
    stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stats)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    code = stats.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_the_documented_stats_calls_run(tmp_path, monkeypatch, capsys):
    """Both write §2 calls run as written; the reference-app one keeps the pattern-surface count (#550)."""
    entries = [{"export_name": f"surface{i}", "source_file": "src/app.py", "source_line": i + 1,
                "confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
                "signature_source": "T1-low"} for i in range(3)]
    # a backslash, as in every Windows path, reaches the helper intact (a separator there, a name character here)
    forge_version = tmp_path / "Users\\runner"
    forge_version.mkdir(parents=True)
    (forge_version / "provenance-map.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    library = _fence(two, "    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json\n")
    app = _fence(two, "--shape reference-app\n")
    assert library != app and "--shape" not in library and '"pattern_surfaces_documented": {P}' in app
    code, out = _stats_main(library, forge_version, monkeypatch, capsys)
    assert code == 0 and out["coherence"]["ok"] is True
    assert out["stats"]["exports_documented"] == 3 and "pattern_surfaces_documented" not in out["stats"]
    code, out = _stats_main(app, forge_version, monkeypatch, capsys)
    assert code == 0 and out["coherence"]["ok"] is True
    assert out["stats"]["exports_documented"] == out["stats"]["pattern_surfaces_documented"] == 2
    assert sum(out["confidence_distribution"].values()) == 3  # per citation, not per pattern surface
    assert "effective_denominator" not in out["stats"]


# --------------------------------------------------------------------------
# Docs and knowledge
# --------------------------------------------------------------------------


def test_docs_and_knowledge():
    workflows = _slice(_read(REPO_ROOT / "docs" / "workflows.md"), "### Update Skill (US)", "**Agent:**")
    assert "Fetch the source at the skill's ref" in workflows and "--target-ref" in workflows
    verifying = _slice(_read(REPO_ROOT / "docs" / "verifying-a-skill.md"), "### Workflow-time enforcement", "---")
    halt = _slice(verifying, "- **Test Skill (`@Ferris TS`)**", "\n")
    assert "**Update Skill with `--from-test-report`**" in halt
    assert "Test Skill with `workspace-drift`, Update Skill with `halted-for-workspace-drift`" in halt
    assert "records that commit" in verifying
    trouble = _slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                     "### Update Skill stops with `blocked` before detecting changes", "\n### ")
    for token in ("init:source-tree", "ref-not-found", "--target-ref", "source-not-fetched",
                  "workspace-clone-not-updated"):
        assert token in trouble, token
    assert "git -C" not in trouble and "workspace" not in trouble.replace("workspace-", "")
    assert "--target-ref <tag>" in _read(REPO_ROOT / "docs" / "concepts.md")
    assert "update-skill runs it before it moves the clone" in _read(SRC / "knowledge" / "ccc-bridge.md")
    example4 = _slice(_read(SRC / "knowledge" / "provenance-tracking.md"),
                      "### Example 4: Provenance Preservation During Updates", "### File-Level Provenance")
    assert "Record the commit the update read" in example4
    assert "`source_commit` always names the commit the citations were read from" in example4
    tier = _read(SRC / "skf-create-skill" / "references" / "tier-degradation-rules.md")
    assert "never from the workspace clone as it stands" in tier
    assert "`init:source-tree`" in _slice(tier, "- **update-skill:**", "\n")
    audit = _read(SRC / "skf-audit-skill" / "references" / "report.md")
    assert "`--target-ref {latest_tag}`" in audit and "`--target-ref HEAD`" in audit


# --------------------------------------------------------------------------
# Gap reports through the shared helpers (#583, #546) and drift through
# scripts (#589)
# --------------------------------------------------------------------------

PARSE_GAPS = SRC / "shared" / "scripts" / "skf-parse-gaps.py"
FIND_TEST_REPORT = SRC / "shared" / "scripts" / "skf-find-test-report.py"
STRUCTURAL_DIFF = SRC / "shared" / "scripts" / "skf-structural-diff.py"
RESOLVER = SRC / "shared" / "scripts" / "skf-resolve-authoritative-files.py"
BUILD_MANIFEST = SRC / "shared" / "scripts" / "skf-build-change-manifest.py"
GAP_LEDGER = SRC / "skf-test-skill" / "scripts" / "gap-ledger.py"
RUN_ID = "20260930T101010Z-4242-ab12"


def _probe(name: str) -> list[str]:
    return [f"{{project-root}}/_bmad/skf/shared/scripts/{name}", f"{{project-root}}/src/shared/scripts/{name}"]


def _zero() -> str:
    return _slice(_read(DETECT), "### 0. Check for Test Report Input", "### 1. Scan Current Source State")


def _routing_table() -> dict[str, str]:
    """detect-changes §0's table: each ledger category slug -> the Change Category its row names."""
    routes = {}
    for row in _zero().splitlines():
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[0].startswith("`") or cells[2] == "Change Category":
            continue
        change = re.match(r"(NEW_EXPORT|MODIFIED_EXPORT|MOVED_EXPORT|STRUCTURAL_FIX|metadata update)", cells[2])
        assert change, row
        for slug in re.findall(r"`([a-z][a-z0-9-]*)`", cells[0]):
            assert slug not in routes, slug
            routes[slug] = change.group(1)
    return routes


def test_gap_routing_keys_on_the_ledger_category():
    """Every ledger category is routed by one row or listed as not routed, never both (#583)."""
    ledger = _module(GAP_LEDGER, "skf_gap_ledger_prose")
    routes = _routing_table()
    not_routed = set(re.findall(r"`([a-z][a-z0-9-]*)`", _slice(_zero(), "**Not routed:**", "\n")))
    assert set(routes) | not_routed == set(ledger.CATEGORIES), set(ledger.CATEGORIES) ^ (set(routes) | not_routed)
    assert not set(routes) & not_routed
    assert routes["missing-export"] == routes["missing-type"] == routes["provenance-completeness"] == "NEW_EXPORT"
    assert routes["signature-mismatch"] == routes["fabricated-signature"] == "MODIFIED_EXPORT"
    assert routes["split-body-mismatch"] == routes["broken-reference"] == "STRUCTURAL_FIX"
    assert routes["provenance-line"] == "MOVED_EXPORT" and routes["metadata-drift"] == "metadata update"
    translate = _slice(_zero(), "2. **Translate each gap by its `category`**", "\n")
    assert "never by its severity" in translate
    # the old severity column is gone: a Medium missing export no longer falls to `unknown` by its severity
    assert "| Gap Severity |" not in _zero() and "| Critical | Missing export documentation |" not in _zero()
    # step 3 routes a missing export or type to targeted re-extraction whatever its severity, and never halts on one
    route = _slice(_not_found(), "     - **If the manifest entry has no `source_citation` (or one whose spot-check "
                   "above pinned no line), the branches above did not take it, and it asks to document a missing "
                   "export or type**", "\n")
    for token in ("its `category` is `missing-export` or `missing-type`", "route it to §0a when its "
                  "`resolved_paths[]` is not empty, whatever its severity", "The route follows the gap's category, "
                  "not its severity", "record it `unknown` as the bullet below does", "so it does not halt"):
        assert token in route, token
    # step 3 routes on the category alone: detect-changes chose it, for an older report too
    assert "title names a missing export or type" not in route
    category = _slice(_zero(), "   - **`gap_id`** and **`category`**", "\n")
    for token in ("For a report older than the ledger, `category` is the slug of the row step 2 chose",
                  "so step 3 routes on `category` alone"):
        assert token in category, token
    # the route is stated where it acts: §0 bullet 2, §0a's Used by and its no-halt exception, nowhere else
    zero_a = _slice(_read(RE_EXTRACT), "### 0a. Targeted Re-Extraction Branch", "### 1. Check for Docs-Only Mode")
    used_by = _slice(zero_a, "**Used by:** §0 bullet 2", "**Purpose:**")
    assert "that §0 bullet 2 routes here by its `category` (a missing export or type)" in used_by
    failures = _slice(zero_a, "5. **Track failures across all qualifying entries.**", "\n")
    assert "except a `Medium`, `Low` or `Info` missing export or type" in failures
    rules = _slice(_read(RE_EXTRACT), "**Exception (gap-driven mode):**", "\n")
    assert "the `resolved_paths[]` of each entry §0 bullet 2 routes to it" in rules
    for prose in (rules, _slice(zero_a, "**Purpose:**", "\n")):
        assert "missing export or type" not in prose
    # a gap no row routes is reported, headless included
    four = _slice(_zero(), "4. Set `gap_count`", "\n")
    assert "Add each gap the table does not route to `warnings[]` as `test-report: not routed: {id} ({category})`" \
        in four
    assert "`test-report: not routed: {id} ({category})`" in _slice(_read(REPORT), "### 5b.", "### 6.")
    assert "**Not repaired by this run:**" in _slice(_read(REPORT), "### 2. Present Change Summary", "### 3.")
    warnings = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["warnings"]["description"]
    assert "test-report: not routed:" in warnings


def _ledger_record(severity, category, title, source, remediation, export=None) -> dict:
    record = {"severity": severity, "category": category, "title": title, "source": source,
              "remediation": remediation}
    if export:
        record["export"] = export
    return record


def test_a_hard_gate_blocked_report_is_read_through_its_ledger(tmp_path):
    """#546: a blocked run's Gap Report holds only its placeholder; parse-gaps reads the ledger beside it."""
    zero = _zero()
    assert yaml.safe_load(_frontmatter(_read(DETECT)))["parseGapsProbeOrder"] == _probe("skf-parse-gaps.py")
    read = _slice(zero, "1. **Read the gaps through `{parseGapsHelper}`**", "2. **Translate each gap")
    for token in ("It reads the gap ledger test-skill wrote beside the report (`test-findings-{run_id}.json`), "
                  "which holds every gap of a run test-skill's hard gate blocked (its `stepsCompleted` ends at "
                  "`hard-gate`)", "Never read gaps from the report by eye", "`test-report: <entry>`",
                  'phase: "detect-changes:parse-gaps"', "`LEDGER_INVALID`",
                  "`--provenance-map` whenever init.md §4 loaded one"):
        assert token in read, token
    assert "--ext" not in read  # the helper takes the map's extensions itself, none collected by eye
    for gone in ("1. Read the **Gap Report** section", "Read the **Coverage Analysis** section",
                 "any substring matching a recognized source file extension"):
        assert gone not in _read(DETECT), gone
    forge_version = tmp_path / "forge data" / "lib" / "1.0.0"
    forge_version.mkdir(parents=True)
    report = forge_version / f"test-report-lib-{RUN_ID}.md"
    report.write_bytes((
        "---\nworkflowType: 'test-skill'\nskillName: 'lib'\n"
        f"runId: '{RUN_ID}'\ntestResult: 'fail'\n"
        "stepsCompleted: ['step-01-init', 'step-03-coverage-check', 'step-04-coherence-check', 'hard-gate']\n"
        "---\n\n# Test Report: lib\n\n## Gap Report\n\n"
        "<!-- Populated by report §3-§4b (includes Discovery Quality subsection) -->\n").encode("utf-8"))
    records = [
        _ledger_record("Critical", "signature-mismatch", "search signature", "pkg/api.py:5",
                       "Update SKILL.md to match `pkg/api.py:5`.", "search"),
        _ledger_record("High", "broken-reference", "Link to a missing reference file", "SKILL.md:12",
                       "Create `references/api.md` or remove the link."),
        _ledger_record("Medium", "missing-export", "fresh undocumented", "pkg/__init__.py",
                       "Document `fresh` from `pkg/new.py`; see also ../outside/secret.py.", "fresh"),
    ]
    ledger = forge_version / f"test-findings-{RUN_ID}.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check"], input=json.dumps(records), capture_output=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout
    src = tmp_path / "src tree"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    (src / "pkg" / "new.py").write_bytes(b"def fresh():\n    return 1\n")
    provenance = forge_version / "provenance-map.json"
    provenance.write_bytes(json.dumps({"entries": [{"export_name": "search", "source_file": "pkg/api.py"}]})
                           .encode("utf-8"))
    call = _fence(read, "uv run {parseGapsHelper} parse")
    argv = _call_args(call, "parseGapsHelper", {"test_report_path": str(report), "source_root": str(src),
                                                "provenance_map_path": str(provenance)})
    code, out = _run_script(PARSE_GAPS, argv)
    assert code == 0 and out["read_from"] == "ledger", out
    gaps = {gap["category"]: gap for gap in out["gaps"]}
    assert out["gap_count"] == 3 and set(gaps) == {"signature-mismatch", "broken-reference", "missing-export"}
    assert gaps["signature-mismatch"]["source_citation"] == {"file": "pkg/api.py", "line": 5}
    assert gaps["signature-mismatch"]["severity"] == "Critical" and gaps["broken-reference"]["severity"] == "High"
    missing = gaps["missing-export"]
    assert missing["export"] == "fresh" and missing["source_citation"] is None
    assert missing["resolved_paths"] == ["pkg/new.py"]
    assert {"path": "../outside/secret.py", "reason": "outside-root"} in missing["rejected_paths"]
    routes = _routing_table()
    assert [routes[gap["category"]] for gap in out["gaps"]] == ["MODIFIED_EXPORT", "STRUCTURAL_FIX", "NEW_EXPORT"]
    fields = _slice(zero, "3. Build the change manifest from the translated gaps", "4. Set `gap_count`")
    for token in ("**`name`**: the gap's `export`, else the export its `title` names",
                  "**`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**",
                  "(`outside-root`, `symlink-outside-root`, `not-found`, `no-match`)", "never from the report by eye"):
        assert token in fields, token


def test_zero_a_scans_the_resolved_paths_never_a_hand_expansion(tmp_path):
    """re-extract §0a takes parse-gaps' resolved files; every root check is the helper's, a rule R3 gap's cited
    source file included (#583)."""
    zero_a = _slice(_read(RE_EXTRACT), "### 0a. Targeted Re-Extraction Branch", "### 1. Check for Docs-Only Mode")
    files = _slice(zero_a, "2. **The file set**", "\n")
    for token in ("is the `resolved_paths[]` of every entry routed here, as they are",
                  "step 2 §0's `{parseGapsHelper}` resolved them under `{source_root}`",
                  "never scan a refused path, and never expand or check a path by hand",
                  "`outside-root`", "`symlink-outside-root`", "`not-found`", "`no-match`"):
        assert token in files, token
    for gone in ("**Expand `remediation_paths[]`**", "using the provenance map's file patterns",
                 "Deduplicate the resolved file set", "no `..` part", "each file once"):
        assert gone not in zero_a, gone
    paths = _slice(_zero(), "   - **`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**", "\n")
    call = re.search(r"`(uv run \{parseGapsHelper\} paths [^`]*)`", paths)
    assert call, "detect-changes §0 runs no root check for a rule R3 gap's cited file"
    src = tmp_path / "src tree"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "api.py").write_bytes(API_PY)
    (tmp_path / "outside.py").write_bytes(b"def x():\n    pass\n")
    for cited, resolved, rejected in (("pkg/api.py", ["pkg/api.py"], []),
                                      ("../outside.py", [], [{"path": "../outside.py", "reason": "outside-root"}])):
        argv = _call_args(call.group(1), "parseGapsHelper", {"source_root": str(src)},
                          {"<the cited source file>": cited})
        code, out = _run_script(PARSE_GAPS, argv)
        assert code == 0 and (out["resolved_paths"], out["rejected_paths"]) == (resolved, rejected), out


def _report_fixture(folder: Path, run_id: str, result: str, test_date: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"test-report-lib-{run_id}.md"
    path.write_bytes((f"---\nrunId: '{run_id}'\ntestResult: '{result}'\nscore: '72'\ntestDate: '{test_date}'\n"
                      "---\n\n# Test Report: lib\n").encode("utf-8"))
    return path


def _gone_report_fixture(folder: Path) -> None:
    """A result file that names a report someone deleted: the helper finds it, from its summary only."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skf-test-skill-result-latest.json").write_bytes(json.dumps({
        "runId": "20260930T101010Z-2-bbbb", "timestamp": "2026-09-30T10:10:10Z",
        "outputs": [{"type": "report", "path": "gone/test-report-lib-20260930T101010Z-2-bbbb.md"}],
        "summary": {"result": "FAIL", "score": 61}}).encode("utf-8"))


def test_the_test_report_is_found_by_the_shared_helper(tmp_path):
    """init §1 finds the report with skf-find-test-report.py, never by glob and sort (#583)."""
    init = _read(INIT)
    assert yaml.safe_load(_frontmatter(init))["findTestReportProbeOrder"] == _probe("skf-find-test-report.py")
    lookup = _slice(init, "**If `--from-test-report` was provided", "**If `--allow-workspace-drift` was provided:**")
    for gone in ("sort -r", "Glob `{forge_data_folder}", "Read the report path from `outputs[]`",
                 "picks the newest report by the run id"):
        assert gone not in lookup, gone
    for token in ("Never glob, sort or read a report's frontmatter by hand",
                  "**`status` is `found` and `report_exists` is true:** set `test_report_path` ← `path`, "
                  "`{test_report_run_id}` ← `run_id` and `update_mode: gap-driven`",
                  "with its `testResult`, `score` and `source`", "(`skipped[]`)",
                  "`found` with `report_exists` false, a result file naming a report that is gone",
                  "Pass `--version` only when steps 1-3 above bound `{active_version}`"):
        assert token in lookup, token
    forge = tmp_path / "forge data"
    newest = _report_fixture(forge / "lib" / "1.0.0", "20260930T101010Z-2-bbbb", "fail", "2026-09-30T10:10:10Z")
    _report_fixture(forge / "lib" / "1.0.0", "20260901T080000Z-1-aaaa", "pass", "2026-09-01T08:00:00Z")
    values = {"forge_data_folder": str(forge), "skill_name": "lib", "active_version": "1.0.0"}
    call = _fence(lookup, "uv run {findTestReportHelper} find")
    code, out = _run_script(FIND_TEST_REPORT, _call_args(call, "findTestReportHelper", values))
    assert code == 0 and (out["status"], out["path"], out["testResult"]) == ("found", str(newest), "fail"), out
    assert out["report_exists"] is True and out["source"] == "versioned-glob"
    # a report a result file names but someone deleted: found, from its summary, and not a gap-driven input
    gone = tmp_path / "gone forge"
    _gone_report_fixture(gone / "lib" / "1.0.0")
    code, out = _run_script(FIND_TEST_REPORT, _call_args(call, "findTestReportHelper", {**values,
                                                                                         "forge_data_folder": str(gone)}))
    assert code == 0 and out["status"] == "found" and out["report_exists"] is False, out


REPORT_RUN = "20260930T101010Z-2-bbbb"


@pytest.mark.parametrize(("result", "generation_date", "applied", "unconsumed"), [
    ("fail", "2026-09-29T12:00:00Z", False, True),
    ("pass-with-drift", "2026-09-29T12:00:00Z", False, True),
    ("fail", "2026-10-02T00:00:00Z", False, False),  # the skill was regenerated or repaired after the test
    ("pass", "2026-09-29T12:00:00Z", False, False),
    ("fail", "", False, True),  # no generation_date: offered rather than hidden
    # a repair the same day: write.md stamps generation_date to the second, so the report it applied reads older
    ("fail", "2026-09-30T10:42:07Z", False, False),
    # the map's update block names the report the last gap-driven repair applied, whatever a date alone says
    ("fail", "2026-09-30", True, False),
    ("gone", "2026-09-29T12:00:00Z", False, False),  # a result file naming a deleted report: nothing to repair
], ids=["fail-newer", "drift-newer", "fail-older", "pass", "no-date", "repaired-same-day", "applied", "report-gone"])
def test_a_normal_run_offers_an_unconsumed_failing_report(tmp_path, result, generation_date, applied, unconsumed):
    """init §4b: a FAIL or PASS_WITH_DRIFT report newer than the skill, not yet applied, is offered (#583)."""
    init = _read(INIT)
    four_b = _slice(init, "### 4b. Offer an Unconsumed Test Report", "### 5. Load [MANUAL] Section Inventory")
    # after §4 binds the provenance map the offer reads, before §6 skips the source tree in gap-driven mode
    assert init.index("### 4. Load Provenance Map") < init.index("### 4b.") < init.index("### 6. Resolve the Source")
    assert "### 2b." not in init
    call = _fence(four_b, "uv run {findTestReportHelper} find")
    assert '--newer-than "{generation_date}"' in call and '--provenance-map "{provenance_map_path}"' in call
    forge = tmp_path / "forge data"
    if result == "gone":
        _gone_report_fixture(forge / "lib" / "1.0.0")
    else:
        _report_fixture(forge / "lib" / "1.0.0", REPORT_RUN, result, "2026-09-30T10:10:10Z")
    provenance = tmp_path / "provenance-map.json"
    block = {"update_type": "gap-driven", "test_report_run_id": REPORT_RUN} if applied else {}
    provenance.write_bytes(json.dumps({"entries": [], **block}).encode("utf-8"))
    values = {"forge_data_folder": str(forge), "skill_name": "lib", "active_version": "1.0.0",
              "generation_date": generation_date, "provenance_map_path": str(provenance)}
    code, out = _run_script(FIND_TEST_REPORT, _call_args(call, "findTestReportHelper", values))
    assert code == 0 and out["status"] == "found", out
    # the rule §4b states, applied to the helper's output
    offered = (out["report_exists"] is True and out["testResult"] in ("fail", "pass-with-drift")
               and out["newer"] is not False and out["applied"] is not True)
    assert offered is unconsumed, out
    for token in ("**Run this section only when `--from-test-report` was not given and `degraded_mode` is false**",
                  "`report_exists` is true", "`testResult` is `fail` or `pass-with-drift`", "`newer` is not `false`",
                  "offers the report rather than hiding it", "`applied` is not `true`",
                  "[G] Repair the gaps it lists", "[S] Check the source for changes",
                  "Its default follows the verdict: [G] for `fail`; [S] for `pass-with-drift`",
                  "so a repair would read that same tree and halt `halted-for-workspace-drift`",
                  "set `test_report_path` ← `{unconsumed_test_report}`, `{test_report_run_id}` ← `run_id` and "
                  "`update_mode: gap-driven`",
                  "add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`",
                  "It is a notice, not a gate the run resolves: no `headless_decisions[]` entry"):
        assert token in four_b, token
    gates = _slice(_read(SKILL), "| **Gates** |", "\n")
    assert "init.md §4b's [G]/[S] test-report offer, interactive only (headless warns `unconsumed-test-report`)" \
        in gates


def test_the_no_change_report_points_at_the_unconsumed_report():
    """report §1 names --from-test-report, or for a drift pass a test against the pinned commit, instead of 'No
    action required' when a test report stands (#583)."""
    one = _slice(_read(REPORT), "### 1. Handle No-Change Shortcut", "### 1a.")
    pointer = _slice(one, "When `{unconsumed_test_report}` is bound", "\n\nIn gap-driven mode")
    for token in ("replace that recommendation by its `{unconsumed_test_result}`",
                  "- `fail`:", "`@Ferris US {skill_name} --from-test-report`", "has not been applied to this skill",
                  # test-skill's own advice for a drift pass: the repair would read the same drifted tree
                  "- `pass-with-drift`:", "Once the workspace holds the pinned commit, re-run test-skill without "
                  "`--allow-workspace-drift`"):
        assert token in pointer, token
    assert "In gap-driven mode (step 2 §0 translated none of the report's gaps)" in one
    five_b = _slice(_read(REPORT), "### 5b. Result Contract", "### 6.")
    for token in ("`unconsumed-test-report` (init.md §4b)", "`test-report:` entries", "`no-baseline-time`",
                  "`moved-check-skipped`", "`unknown-language`"):
        assert token in five_b, token
    # the flag's cell stays the flag's: the offer is listed with the gates
    flags = _slice(_read(SKILL), "| **Flags** |", "\n")
    assert "`--from-test-report` (gap-driven mode);" in flags and "§2b" not in flags and "§4b" not in flags
    warnings = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["warnings"]["description"]
    for token in ("unconsumed-test-report (init.md §4b", "test-report:", "no-baseline-time", "moved-check-skipped",
                  "unknown-language"):
        assert token in warnings, token


def test_category_b_diffs_through_the_structural_diff_helper(tmp_path, capsys):
    """Category B: the runner's exports plus what the workers read, diffed by skf-structural-diff.py, and mapped
    onto the manifest by skf-build-change-manifest.py, never by eye (#589)."""
    detect = _read(DETECT)
    frontmatter = yaml.safe_load(_frontmatter(detect))
    assert frontmatter["structuralDiffProbeOrder"] == _probe("skf-structural-diff.py")
    assert frontmatter["classifyChangedFilesProbeOrder"] == _probe("skf-classify-changed-files.py")
    assert frontmatter["extractPublicApiProbeOrder"] == EXTRACT_PUBLIC_API_PATHS
    assert "Run §2.1's categories in order, A, then B, then C" in _slice(detect, "## Rules", "## Steps")
    two_one = _slice(detect, "#### 2.1 Categories A, B and C, in Order", "**Category D")
    assert "Launch subprocesses in parallel" not in detect
    order = [two_one.index(mark) for mark in ("**Category A:", "**Category B:", "**Category C:")]
    assert order == sorted(order)
    category_b = _slice(two_one, "**Category B: export-level changes", "**Category C")
    for token in ("`export_name` and `source_file` as it wrote them", "`params` (each parameter as the source "
                  "writes it, `name: type`", "a name `entry_point_diff.extraction_gaps[]` lists",
                  "a form Known Limitation #11 in `{extractionPatternsData}` lists",
                  "`confidence: T1-low` and `extraction_method: source-read`",
                  "Write the union of their `exports` arrays to `{run_dir}/export-details.json`",
                  "which §3's helper maps onto Category B: never re-diff by eye"):
        assert token in category_b, token
    # the mapping table and the renamed keys are the helper's now, not the prompt's
    for gone in ("| `removed[]` | `deleted_exports` |", "copied from the runner's", "current-exports.json",
                 "modified and added lists, as one JSON array"):
        assert gone not in detect, gone
    assert "Exports in provenance but not in source → DELETED_EXPORT" not in detect
    call = _fence(category_b, "uv run {structuralDiffHelper}")
    for token in ('"{run_dir}/extraction.json"', '--current-extra "{run_dir}/export-details.json"',
                  '--files "{run_dir}/modified-files.json"', '-o "{run_dir}/category-b-diff.json"'):
        assert token in call, token
    forge_version = tmp_path / "forge"
    forge_version.mkdir()
    provenance = forge_version / "provenance-map.json"
    provenance.write_bytes(json.dumps({"entries": [
        {"export_name": "search", "export_type": "function", "source_file": "pkg/api.py", "source_line": 5,
         "params": ["q"], "return_type": None},
        {"export_name": "old_fn", "export_type": "function", "source_file": "pkg/api.py", "source_line": 10,
         "params": [], "return_type": None},
        {"export_name": "by_eye", "export_type": "function", "source_file": "pkg/api.py", "source_line": 20,
         "params": [], "return_type": None},
        {"export_name": "stable", "export_type": "function", "source_file": "pkg/util.py", "source_line": 1,
         "params": [], "return_type": None}]}).encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # the runner's records, as it writes them, and what the workers added: params, and an export read by eye
    (run_dir / "extraction.json").write_bytes(json.dumps({"exports": [
        {"export_name": "search", "export_type": "function", "source_file": "pkg/api.py", "source_line": 7,
         "confidence": "T1", "extraction_method": "ast-grep"},
        {"export_name": "helper", "export_type": "function", "source_file": "pkg/api.py", "source_line": 12,
         "confidence": "T1", "extraction_method": "ast-grep"}]}).encode("utf-8"))
    (run_dir / "export-details.json").write_bytes(json.dumps({"exports": [
        {"export_name": "search", "source_file": "pkg/api.py", "params": ["q", "limit: int"], "return_type": None},
        {"export_name": "helper", "source_file": "pkg/api.py", "params": [], "return_type": None},
        {"export_name": "by_eye", "export_type": "function", "source_file": "pkg/api.py", "source_line": 20,
         "params": [], "return_type": None, "confidence": "T1-low",
         "extraction_method": "source-read"}]}).encode("utf-8"))
    (run_dir / "modified-files.json").write_bytes(json.dumps(["pkg/api.py"]).encode("utf-8"))
    diff_module = _module(STRUCTURAL_DIFF, "skf_structural_diff_prose")
    code = diff_module.main(_call_args(call, "structuralDiffHelper", {"provenance_map_path": str(provenance),
                                                                       "run_dir": str(run_dir)}))
    capsys.readouterr()
    assert code == 1  # differences found, and the diff written
    diff = json.loads((run_dir / "category-b-diff.json").read_text(encoding="utf-8"))
    assert [e["name"] for e in diff["removed"]] == ["old_fn"] and [e["name"] for e in diff["added"]] == ["helper"]
    assert sorted(c["field"] for c in diff["changed"] if c["name"] == "search") == ["line", "params"]
    assert diff["file_scope"]["baseline_left_out"] == 1  # `stable` is outside --files: unchanged, in no list
    # §3's helper maps the diff: search modified (its params), helper new, old_fn deleted, by_eye unchanged
    (run_dir / "category-a.json").write_bytes(json.dumps({"category_a": {
        "modified": ["pkg/api.py"], "added": [], "deleted": []}, "moved_files": []}).encode("utf-8"))
    (run_dir / "categories.json").write_bytes(json.dumps({"degraded_mode": False,
                                                          "update_mode": "normal"}).encode("utf-8"))
    build = _fence(_slice(detect, "### 3. Build Change Manifest", "### 4."), "uv run {buildChangeManifestHelper} build")
    manifest = _module(BUILD_MANIFEST, "skf_build_change_manifest_category_b")
    assert manifest.main(_call_args(build, "buildChangeManifestHelper", {"run_dir": str(run_dir)})) == 0
    affected = json.loads(capsys.readouterr().out)["per_file"][0]["exports_affected"]
    assert sorted((e["name"], e["change_type"]) for e in affected) == [
        ("helper", "NEW_EXPORT"), ("old_fn", "DELETED_EXPORT"), ("search", "MODIFIED_EXPORT")]


def test_the_documented_resolver_call_classifies_the_mirror(tmp_path, capsys):
    """§1b runs skf-resolve-authoritative-files.py resolve --provenance-map, never a walk by eye (#589)."""
    detect = _read(DETECT)
    assert yaml.safe_load(_frontmatter(detect))["resolveAuthoritativeFilesProbeOrder"] == \
        _probe("skf-resolve-authoritative-files.py")
    one_b = _slice(detect, "### 1b. Discovered Authoritative Files Protocol", "### 1c.")
    call = _fence(one_b, "uv run {resolveAuthoritativeFilesHelper} resolve")
    assert '--provenance-map "{provenance_map_path}"' in call
    for token in ("**`already_tracked[]`:**", "**`already_in_scope[]`:**", "with no prompt, as create-skill §2a does",
                  "**`pre_decided[]` with `prior_action: \"promoted\"`:**", "**`unresolved[]`:**",
                  "except for a candidate whose `prior_action` is `deferred-headless`, which a headless run already "
                  "recorded: write no second amendment for it", "as the helper reported them",
                  "Never walk, match or hash these files by hand"):
        assert token in one_b, token
    for gone in ("1. **Walk the source tree.**", "uv run {hashContentHelper} hash"):
        assert gone not in one_b, gone
    src = tmp_path / "src tree"
    (src / "docs").mkdir(parents=True)
    for name in ("AGENTS.md", "llms.txt", "CLAUDE.md"):
        (src / "docs" / name).write_bytes(b"# guide\n")
    forge = tmp_path / "forge"
    (forge / "lib").mkdir(parents=True)
    provenance = forge / "lib" / "provenance-map.json"
    provenance.write_bytes(json.dumps({"entries": [], "file_entries": [
        {"file_type": "doc", "source_file": "docs/AGENTS.md"}]}).encode("utf-8"))
    (forge / "lib" / "skill-brief.yaml").write_bytes(yaml.safe_dump({"scope": {
        "include": ["docs/*.txt"], "amendments": [
            {"action": "skipped", "path": "docs/CLAUDE.md", "reason": "headless: no user to prompt"}]}}).encode("utf-8"))
    resolver = _module(RESOLVER, "skf_resolve_authoritative_files_prose")
    code = resolver.main(_call_args(call, "resolveAuthoritativeFilesHelper", {
        "source_root": str(src), "forge_data_folder": str(forge), "skill_name": "lib",
        "provenance_map_path": str(provenance)}))
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [r["path"] for r in out["already_tracked"]] == ["docs/AGENTS.md"]
    assert [r["path"] for r in out["already_in_scope"]] == ["docs/llms.txt"]
    assert [(r["path"], r["prior_action"]) for r in out["unresolved"]] == [("docs/CLAUDE.md", "deferred-headless")]


def test_the_run_folder_carries_the_helper_files_and_step_8_removes_it(tmp_path, capsys):
    """The helpers pass JSON through one run folder; §2.2 and §3 read the helper files and the category JSON from it,
    with no echo and no list typed by hand."""
    detect = _read(DETECT)
    steps = _slice(detect, "## Steps", "### 0. Check for Test Report Input")
    assert ('mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d '
            '"{project-root}/_bmad-output/.skf-run/skf-update-skill-XXXXXXXX"') in _fence(steps, "mktemp -d")
    assert "Bind `{run_dir}` ← the path it prints" in steps and 'phase: "detect-changes:run-folder"' in steps
    # a run that bound the folder earlier keeps it
    assert "Unless `{run_dir}` is already bound, first create this run's folder" in steps
    health = _read(HEALTH)
    one_c = _slice(health, "1c. **Remove this update's run folder**", "\n")
    assert 'rm -rf "{run_dir}"' in one_c and "in every mode" in one_c
    marks = [health.index("1b. **Remove the private source tree**"), health.index("1c. **Remove this update's"),
             health.index("2. Load `{nextStepFile}`")]
    assert marks == sorted(marks)
    assert "_bmad-output/.skf-run/` that step 8 removes" in _slice(_read(SKILL), "| **Outputs** |", "\n")
    assert 'echo "{category JSON}"' not in detect
    write = _fence(detect, 'cat > "{run_dir}/categories.json"')
    assert "category_a" not in write and "category_b" not in write  # A and B stay in the helpers' files
    ratio = _fence(_slice(detect, "#### 2.2", "### 3."), "uv run {buildChangeManifestHelper} deletion-ratio")
    build = _fence(_slice(detect, "### 3. Build Change Manifest", "### 4."), "uv run {buildChangeManifestHelper} build")
    forge = tmp_path / "forge"
    forge.mkdir()
    provenance = forge / "provenance-map.json"
    provenance.write_bytes(json.dumps({"entries": [{"export_name": "a", "source_file": "a.py"},
                                                   {"export_name": "b", "source_file": "b.py"}]}).encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "category-a.json").write_bytes(json.dumps({
        "status": "ok", "mode": "diff", "category_a": {"modified": ["a.py"], "added": ["c.py"], "deleted": ["b.py"]},
        "moved_files": []}).encode("utf-8"))
    (run_dir / "category-b-diff.json").write_bytes(json.dumps({
        "removed": [], "added": [], "moved": [], "signature_unverified": [],
        "changed": [{"name": "a", "field": "params", "baseline_value": [], "current_value": ["x"], "file": "a.py",
                     "line": 2}]}).encode("utf-8"))
    # Category C found b.py renamed to c.py
    (run_dir / "categories.json").write_bytes(json.dumps({
        "category_c": {"renamed_files": [{"old_path": "b.py", "new_path": "c.py"}], "renamed_exports": []},
        "degraded_mode": False, "update_mode": "normal"}).encode("utf-8"))
    manifest = _module(BUILD_MANIFEST, "skf_build_change_manifest_prose")
    values = {"provenance_map_path": str(provenance), "run_dir": str(run_dir)}
    assert manifest.main(_call_args(ratio, "buildChangeManifestHelper", values)) == 0
    ratio_out = json.loads(capsys.readouterr().out)
    assert ratio_out["deletion_ratio"] == 0.0 and ratio_out["renamed_or_moved_count"] == 1  # a rename, not a loss
    assert manifest.main(_call_args(build, "buildChangeManifestHelper", values)) == 0
    counts = json.loads(capsys.readouterr().out)["counts"]
    assert (counts["files_deleted"], counts["files_added"], counts["files_moved"], counts["exports_modified"]) == \
        (0, 0, 1, 1)


def test_the_new_helper_calls_quote_every_path():
    """Every path the new helper calls pass sits in double quotes, as the earlier calls' do."""
    detect, init, re_extract = _read(DETECT), _read(INIT), _read(RE_EXTRACT)
    calls = [
        (_fence(detect, "uv run {parseGapsHelper} parse"), "parseGapsHelper"),
        (re.search(r"`(uv run \{parseGapsHelper\} paths [^`]*)`", detect).group(1), "parseGapsHelper"),
        (_fence(detect, "uv run {resolveAuthoritativeFilesHelper} resolve"), "resolveAuthoritativeFilesHelper"),
        (_fence(detect, "uv run {classifyChangedFilesHelper} classify"), "classifyChangedFilesHelper"),
        (_fence(_slice(detect, "**Category B", "**Category C"), "uv run {extractPublicApiHelper}"),
         "extractPublicApiHelper"),
        (_fence(detect, "uv run {structuralDiffHelper}"), "structuralDiffHelper"),
        (_fence(detect, "uv run {buildChangeManifestHelper} deletion-ratio"), "buildChangeManifestHelper"),
        (_fence(detect, "uv run {buildChangeManifestHelper} build"), "buildChangeManifestHelper"),
        (_fence(_slice(init, "**If `--from-test-report` was provided", "### 1b."), "uv run {findTestReportHelper}"),
         "findTestReportHelper"),
        (_fence(_slice(init, "### 4b.", "### 5."), "uv run {findTestReportHelper}"), "findTestReportHelper"),
        (_fence(_slice(re_extract, "### 0a.", "### 1. Check"), "uv run {extractPublicApiHelper}"),
         "extractPublicApiHelper"),
        (_fence(detect, "uv run {hashContentHelper} compare"), "hashContentHelper"),
        # Category D's two piped calls, each on its own side of the pipe
        (_fence(detect, "uv run {detectScriptsAssetsHelper} detect").split("|")[0], "detectScriptsAssetsHelper"),
        (_fence(detect, "uv run {detectScriptsAssetsHelper} detect"), "newFileDiffHelper"),
    ]
    for call, helper in calls:
        assert _unquoted_placeholders(call, helper) == [], call
