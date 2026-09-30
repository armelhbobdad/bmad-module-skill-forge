#!/usr/bin/env python3
"""Prose pins: update-skill reads a remote skill at the commit it tracks.

A skill forged from a remote repository records, as its `source_root`, the
clone SKF keeps for that repository, which every SKF run moves. These tests
keep update-skill's step files on the contract of skf-source-tree.py:

- init.md reads the source fields from metadata.json, runs the helper's
  `open` before change detection in every mode but gap-driven, binds every
  field it consumes, halts `blocked` (`init:source-tree`) when no commit
  can be read, releases the PID lock only when the run took it, and shows
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
READ_ONLY_RELEASE = 'release the lock unless `detect_only_mode` or `dry_run_mode` is true (`rm -f "$LOCK"`)'
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
        assert 'release the lock (`rm -f "$LOCK"`)' not in section


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
    assert report < text.index("If all three lookups fail, warn and continue with normal source drift mode") \
        < text.index("**If `--target-ref` was provided:**")


def test_version_detection_moved_to_init():
    six_c = _slice(_read(INIT), "### 6c. Detect the Source Version", "### 7.")
    assert "bind `{source_version_detected}`" in six_c and "higher semantic version" in six_c
    # SKF's own patch bumps put the skill ahead of a source that did not raise its version: no warning then.
    lower = six_c[six_c.index("Otherwise leave `{source_version_detected}` unset"):]
    assert "when the source's major and minor version numbers are lower than those of `{version}`" in lower
    assert "when the source's version is lower," not in lower
    assert lower.index("major and minor") < lower.index("`source-version-lower:")
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
    launch = _slice(text, "#### 2.1 — Launch Category Subprocesses", "**Category B")
    assert "the Category A worker also receives" in launch and "`{source_changed_files}`" in launch
    assert "never from timestamps or sizes" in launch and "file-diff-unavailable" in launch
    assert "Files in both but with different timestamps/sizes → MODIFIED" not in text
    assert "the brief's `scope.include` and `scope.exclude` globs" in launch
    assert "Category A takes added, modified and deleted files from `{source_changed_files}`" in one
    assert "the Category C worker `{source_tree_status}`" in launch
    rename = _slice(text, "**Category C — Rename detection:**", "**Subprocess return contract.**")
    ccc = rename[rename.index("Forge+/Deep: use CCC semantic similarity"):]
    assert "except when `{source_tree_status}` is `ready` or `offline`" in ccc
    assert "keep the ast-grep comparison" in ccc
    bridge = _read(SRC / "knowledge" / "ccc-bridge.md")
    assert "so it runs no ccc search there" in bridge and "rename detection keeps its ast-grep comparison" in bridge


def test_category_a_takes_every_file_change_from_git_in_a_tree():
    """A live run read an unchanged in-scope `__init__.py` as ADDED: it exports nothing, so the map never named it."""
    category_a = _slice(_read(DETECT), "**Category A — File-level changes:**", "**Category B")
    tree = _slice(category_a, "- **When `{source_diff_status}` is `ok`**", "\n- **When `{source_tree_status}`")
    for rule in ("- DELETED: a tracked file with a `D` row, or one `{source_root}` does not hold",
                 "- MODIFIED: a tracked file with an `M` or `A` row", "- Every other file is unchanged."):
        assert rule in tree, rule
    assert "never from the provenance map alone" in tree
    added_rule = _slice(tree, "- ADDED:", "\n")
    assert ("a file the provenance map does not name, inside the brief's scope (a `scope.include` glob matches it "
            "and no `scope.exclude` glob does)") in added_rule
    # An untracked in-scope file that exported nothing gets an M row when it gains an export.
    assert "that has an `A` or `M` row" in added_rule and "a row with `status` `A` whose path" not in added_rule
    # With no include glob, create-skill reads auto-detected folders: no git row may narrow that.
    assert "When the brief's `scope.include` is empty, take ADDED as for a local source below instead." in added_rule
    # §1c promotes an out-of-scope glob whose files exist unchanged at source_commit, and says Category A adds them.
    one_c = _slice(_read(DETECT), "### 1c. Major-Version Scope Reconciliation", "### 2. Compare Against")
    assert "§2 Category A will pick up matching files as ADDED" in one_c and "`category: \"scope-expansion\"`" in one_c
    assert ("or that a glob matches which a `scope.amendments[]` entry with `action` `promoted` and `category` "
            "`scope-expansion` names while no tracked file matches that glob yet") in added_rule
    launch = _slice(_read(DETECT), "#### 2.1 — Launch Category Subprocesses", "**Category A")
    assert "the brief's `scope.include` and `scope.exclude` globs and its `scope.amendments[]`" in launch
    assert "as §1c left it" in launch
    unavailable = _slice(category_a, "- **When `{source_tree_status}` is `ready` or `offline` and "
                         "`{source_diff_status}` is `unavailable`:**", "\n- **Otherwise")
    assert "take ADDED and DELETED as for a local source below" in unavailable
    local = _slice(category_a, "- **Otherwise (a local source):**", "\n- Files with same content")
    added = "Files in source but not in provenance map AND not in `change_detection_excludes` → ADDED"
    assert added in local and category_a.count(added) == 1
    assert category_a.count("Files in provenance map but missing from source → DELETED") == 1
    assert "Files in `change_detection_excludes`: skip entirely" in category_a.split("- **When", 1)[0]


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
    concurrency = _slice(text, "| **Concurrency** |", "\n")
    assert "(§4, §6 and §6b" in concurrency
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
GATE_REASONS = ["a line from the tree (rule R3)", "a line and a signature from the tree", "a signature from the tree"]


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
                  "nothing is written and §0a never runs",
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
    assert 'reason: "drift-override: {N} gap(s) need the pinned tree: {name} ({reason}), ..."' in headless
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
    halts = _slice(gate, "Every `NEW_EXPORT`", " needs it,")
    passes = _slice(gate, "A `DELETED_EXPORT`", " need nothing from the tree and pass.")
    for category in categories:
        token = f"`{category}`"
        assert (token in halts) != (token in passes), category
    assert "`NEW_EXPORT`" in halts and "`MODIFIED_EXPORT`" in halts


def test_merge_says_no_new_or_modified_export_arrives_under_the_override():
    """Merge Priority 4 and 5 state the route under the override: the drift gate halted first (#557)."""
    merge = _read(MERGE)
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
    for token in ("run no recipe at `{source_root}`",
                  "Leave each violation that needs a kind from the tree in place",
                  "list it as a WARN ending ` " + DRIFT_NOTE + ")`",
                  "a relabel that reads nothing from the tree still applies",
                  "With the status `ok` or `skipped`, run the recipes as above"):
        assert token in drift, token
    # the gate follows the recipe run it gates, and the re-run keeps the shape (#550)
    assert relabel.index("run the ast-grep recipes for its language") < relabel.index("**Under the drift override**")
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
    assert cited.index(drift) < cited.index("Otherwise read the file that citation names")  # drift clause first
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
    assert "Skip this step when `{workspace_drift_status}` is `overridden`" in six_a
    drift_6a = _slice(six_a, "**Under the drift override** (`{workspace_drift_status}` is `overridden`, step 3 §0.a)",
                      "\n")
    for token in ("end the `Provenance:` line of the Validation Summary", "`file-missing`, `line-out-of-bounds`",
                  "an unverified export or a finding step 2 skipped", DRIFT_NOTE):
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

    All four also say it takes no signature, parameter list, return type or node kind from HEAD, so every new or
    modified export halts, whatever its severity (#557).
    """
    init = _slice(_read(INIT), "- `--allow-workspace-drift` (gap-driven mode only)", "\n")
    assert "moves or pins no provenance line read there" in init and "halted-for-workspace-drift" in init
    for token in ("update-skill takes nothing from HEAD",
                  "reads no signature, parameter list, return type or node kind there",
                  "which every new or modified export does"):
        assert token in init, token
    flags = _slice(_read(SKILL), "| **Flags** |", "\n")
    assert "no provenance line read at HEAD is moved or pinned" in flags
    for token in ("update-skill takes nothing from HEAD",
                  "no signature, parameter list, return type or node kind is read there",
                  "as every new or modified export does, halts `halted-for-workspace-drift` before merge"):
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
                  "Route this entry to §0a (Targeted Re-Extraction Branch), whatever its `remediation_paths[]`",
                  "With an empty list it has nothing to scan and lists the entry in `unresolved[]` with "
                  "`files_scanned: 0`",
                  "halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included"):
        assert token in blocking, token
    assert "a blocking gap never gets here, whatever its `remediation_paths[]`" in unknown
    assert "`remediation_paths[]` is empty OR" not in text  # the empty-paths way into `unknown` is gone
    zero_a = _slice(text, "### 0a. Targeted Re-Extraction Branch", "### 1. Check for Docs-Only Mode")
    used_by = _slice(zero_a, "**Used by:** §0 bullet 2", "**Purpose:**")
    assert ("an empty one leaves nothing to scan, so step 4 puts the entry straight into `unresolved[]` with "
            "`files_scanned: 0`") in used_by
    assert "that the second case below does not take" in used_by
    assert "gap-driven runs in which §0 bullet 2 routes no entry here, skip this section entirely" in zero_a
    match = _slice(zero_a, "4. **Match by name**", "\n")
    # a rule R3 gap scans its documented `source` reference, so an empty `remediation_paths[]` alone skips nothing
    assert ("An entry with no path set to scan (a blocking gap with an empty `remediation_paths[]`, or a rule R3 gap "
            "with neither a documented `source` reference nor remediation paths) is not matched") in match
    r3 = _slice(used_by, "- a provenance-completeness gap (rule R3", "\n")
    assert ("treat the export's documented `source` reference (or `remediation_paths[]` when present) as the path "
            "set") in r3
    failures = _slice(zero_a, "5. **Track failures across all qualifying entries.**", "\n")
    assert "every entry step 4 had nothing to scan for (`files_scanned: 0`)" in failures
    template = _fence(zero_a, "Targeted re-extraction failed for {N} gap(s).")
    for token in ('- {name} ({severity or "no severity"})', 'remediation_paths: {paths, or "none named"}',
                  "files_scanned:     {count}", "a) Add a `file:line` citation", "b) Edit the Remediation text",
                  "c) Downgrade the gap(s) to Medium/Low/Info"):
        assert token in template, token
    exit_ = _slice(zero_a, "   Exit with status `halted-for-remediation-path`", "\n")
    for token in ("under `--dry-run` too", "Step-04 merge has not run; no partial writes",
                  'phase: "re-extract:targeted-reextraction"'):
        assert token in exit_, token
    # detect-changes describes the same route
    paths = _slice(_read(DETECT), "   - **`remediation_paths: [path, ...]`**", "\n")
    for token in ("a blocking one still goes to §0a, which has nothing to scan", "`files_scanned: 0`",
                  "halts the run with `halted-for-remediation-path` before merge",
                  "a `Medium`, `Low` or `Info` one records `unknown`"):
        assert token in paths, token
    assert "depending on severity" not in paths


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
    signature = next(i for i, row in enumerate(rows) if "| Signature mismatch |" in row)
    assert split < signature  # read top-down, the split-body row comes first
    assert rows[split].startswith("| High | Split-body inconsistency:")
    assert "with a `Source:` inside the skill package" in rows[split]
    assert ("STRUCTURAL_FIX, see rule R2 (this row takes precedence over the Signature mismatch row below)"
            in rows[split])
    assert "MODIFIED_EXPORT" not in rows[split]
    r2 = _slice(zero, "- **R2: STRUCTURAL_FIX.**", "\n- **R3")
    for token in ("a coherence finding from `skf-scan-skill-md-structure.py`",
                  "a split-body consistency finding (test-skill coverage-check §1b `cross_check_mismatches`)",
                  "Recognize it by its `Source:`, which points inside the skill package",
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
    assert "or a line inside the skill package (a split-body finding's `SKILL.md:42`, rule R2)" in cite
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
    assert list(fields) == ["last_update", "update_type", "files_changed", "exports_affected", "confidence_tier",
                            "manual_sections_preserved"]
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
