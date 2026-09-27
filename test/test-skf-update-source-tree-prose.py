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
  update-skill copy of create-skill's clone steps, is gone.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
    assert "gives the commands that bring it there" in trouble and "the two commands" not in trouble
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
# Docs and knowledge
# --------------------------------------------------------------------------


def test_docs_and_knowledge():
    workflows = _slice(_read(REPO_ROOT / "docs" / "workflows.md"), "### Update Skill (US)", "**Agent:**")
    assert "Fetch the source at the skill's ref" in workflows and "--target-ref" in workflows
    verifying = _slice(_read(REPO_ROOT / "docs" / "verifying-a-skill.md"), "### Workflow-time enforcement", "---")
    assert "test-skill halts with `workspace-drift`" in verifying
    assert "gap-driven update-skill with `halted-for-workspace-drift`" in verifying
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
