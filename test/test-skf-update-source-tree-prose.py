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
  gap-driven.md before merge (its line, signature, parameters and return type could
  only come from HEAD), write.md §2 runs no ast-grep recipe there, and a
  cited new export whose spot-check pins a line gets its provenance entry.

They also pin how a gap-driven run routes a test report's gaps and records
what it did:

- a split-body consistency finding (a `Source:` inside the skill package) is
  a structural fix that edits the reference file, never a modified export;
- a blocking gap with no citation that pins a line and no path to scan halts
  in gap-driven.md with `halted-for-remediation-path`, `--dry-run` included,
  one severity rule holds in gap-driven.md and write, and write's defensive
  halt has a documented status;
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
  its `kind-at` looks up node kinds in write.md §2 and §6, its `fix`
  applies §6's citation and line fixes, and §6 skips the export set diff
  for a reference app, both through the helper and in the by-hand fallback;
- every path a documented helper call passes sits in double quotes;
- re-extract's Forge tier runs the recipe runner (skf-extract-public-api.py
  --mode full) over the changed files, and gap-driven.md §4a over its file set
  without the brief's scope; the per-file workers take their exports from its
  output;
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
- gap-driven.md §1 reads the gaps through skf-parse-gaps.py, a hard-gate
  blocked report through its ledger, and routes each by its ledger category,
  every category exactly once, warning for each gap it does not route;
  gap-driven.md §4a scans the paths the helper resolved, and a Medium missing
  export gets targeted re-extraction without halting the run;
- Category A comes from skf-classify-changed-files.py (no brief and no
  provenance map included), Category B from one recipe runner run, which
  step 3 reuses, and skf-structural-diff.py, in order A, B, C, and §3's
  build maps them; §1b comes from skf-resolve-authoritative-files.py resolve
  --provenance-map; the helpers pass their JSON through one run folder,
  which step 7 removes, and every documented call runs as written.

And the leaner stage chain (#599, #600, #596 update parts):

- there is no validate stage: merge chains to write, skill-check runs once,
  in write.md §7, which re-checks the [MANUAL] blocks after its edits; the
  active link moves to the new version only after §6 and §7, the last
  checks that can halt, and §10 then closes the rollback window; the report
  reads the Validation Summary write.md recorded;
- the headless contract lives in references/invocation-contract.md, its
  Gates row lists the gates the stages raise, and every step and section
  the stage files cite exists under the Stages table's numbering;
- persistent_facts keeps its project-context.md default with a documented
  way to drop it, and the one static rule file holds no copy of merge.md.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
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
# Gap-driven mode's stage file: it stands in for steps 2 and 3 when init.md §8 routes a repair to it (#600).
GAP = REFS / "gap-driven.md"
MERGE = REFS / "merge.md"
WRITE = REFS / "write.md"
REPORT = REFS / "report.md"
HEALTH = REFS / "health-check.md"
SKILL = UPDATE / "SKILL.md"
CONTRACT = REFS / "invocation-contract.md"
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
HALT_PROCEDURE = "**Halt procedure.**"
HALT_CALL = 'uv run {runStateHelper} halt --run-dir "{run_dir}"'
HALT_FLAGS = ('[--tree "{source_tree}"]',
              '[--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"]',
              "[--emit] <<'SKF_JSON'")
STEP_FILES = (INIT, DETECT, GAP, RE_EXTRACT, MERGE, WRITE)
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
# The envelope enums: no new status; init.degraded-rebuild, which init.md §4 records under --allow-degraded,
# joined the gates when the emitter began to check every decision against the schema.
STATUS_ENUM = ["success", "no-changes", "detect-only", "dry-run", "halted-for-workspace-drift",
               "halted-for-brief-refinement", "halted-for-audit", "halted-for-remediation-path",
               "halted-for-manual-mismatch", "halted-for-write-failure", "halted-for-concurrent-run", "blocked"]
GATE_ENUM = ["init.update-confirmation", "init.degraded-rebuild", "detect-changes.promoted-doc-prompt",
             "detect-changes.scope-expansion", "detect-changes.deletion-ratio", "merge.clean-merge-gate"]
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


def _halt_procedure(path: Path) -> str:
    """The **Halt procedure.** block a step file states once, above its sections."""
    return _slice(_read(path), HALT_PROCEDURE, "\n### ")


def _skill_binding(name: str) -> str:
    """The src/ script SKILL.md On Activation binds `{name}` to, for every stage."""
    line = next(line for line in _read(SKILL).splitlines() if f"`{{{name}}}` ←" in line)
    return re.search(r"`\{project-root\}/(src/[^`]+\.py)`", line).group(1)


def _write_9() -> str:
    return _slice(_read(WRITE), "### 9. Move the Workspace Clone", "### 10.")


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
    advance_flags = set(FLAG_RE.findall(_fence(_write_9(), "uv run {sourceTreeHelper} advance")))
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
    write_9 = _write_9()
    result = helper.advance(helper._build_parser().parse_args(
        ["advance", "--clone", str(tmp_path / "c"), "--source-repo", "acme/lib", "--target", "xyz"]))
    assert result["skip_reason"] == "invalid-target"
    for flag, field in ADVANCE_BINDINGS.items():
        assert f"`{flag}` ← `{field}`" in write_9, flag
        assert field in result, field


def test_init_6b_dispatch_and_halt_contract():
    six_b = _init_6b()
    for token in ("**`ready`**", "**`offline`**", "**`skipped`**", "**`unavailable`**",
                  'phase: "init:source-tree"', "source-not-fetched: {source_tree_message}",
                  "target-ref-needs-remote-source", "helper-failed",
                  '**Every §6b HALT** runs the halt procedure with `status: "blocked"`',
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
    assert '--timeout "{tree_timeout}"' in _fence(_write_9(), "uv run {sourceTreeHelper} advance")
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
        assert "HALT (halt procedure:" in section or "HALT instead (halt procedure:" in section
        assert "rm -f" not in section and "emit `SKF_UPDATE_RESULT_JSON`" not in section
    # the halt procedure releases only a lock §1b took (the read-only modes take none), and a tree §6b made
    procedure = _halt_procedure(INIT)
    assert "`--lock` and `--owner` once §1b has bound `{lock_owner}`" in procedure
    assert "Pass `--tree` once §6b has bound `{source_tree}`" in procedure


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
                  '[--brief "{brief_path}"]', '--lists-dir "{run_dir}"',
                  '> "{run_dir}/category-a.json"'):
        assert token in call, token
    # it reads the brief §1c may just have amended, and a skill without one has none to pass
    assert "`--brief` (as §1c left it) when that file exists" in category_a
    rename = _slice(text, "**Category C: rename detection.**", "**Category D")
    ccc = rename[rename.index("**CCC check (Forge+ and Deep, a local source only).**"):]
    assert "`{source_tree_status}` is neither `ready` nor `offline`" in ccc
    assert "never undo a pair the rules made" in ccc
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
        "source_changed_files": str(changed), "run_dir": str(run_dir),
        "brief_path": str(forge / "lib" / "skill-brief.yaml")}, {"<promoted document path>": "docs/AGENTS.md"})
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
    zero_a = _slice(_read(GAP), "### 4a.", "### 5.")
    assert "MCP-fallback" not in zero_a
    assert "never through the gh contents API, zread or deepwiki" in _slice(zero_a, "1. **Source access:**", "\n")
    # the CCC ranking no stage read is gone (#599, leanness): ccc pairs renames in step 2's Category C only
    for gone in ("### 2b.", "ccc_bridge.search", "ccc_significant_changes", "ccc search --refresh"):
        assert gone not in text, gone
    assert "CCC semantic ranking" not in _read(INIT)
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


def test_write_9_advance_contract():
    text = _read(WRITE)
    marks = [text.index("### 8a."), text.index("### 9. Move the Workspace Clone"), text.index("### 10.")]
    assert marks == sorted(marks)
    six_b = _write_9()
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
    for token in ('with `status: "no-changes"` in the payload and `--result-dir "{forge_version}"`',
                  "`files_written: []`", "The line carries `warnings[]`", "Then run `{onCompleteCommand}`"):
        assert token in one, token
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
    contract = _read(CONTRACT)
    flags = _slice(contract, "| **Flags** |", "\n")
    assert "`--target-ref <ref>`" in flags
    # One sentence for the caller: init.md §1b holds the lock's owner, stale time, renewals and releases.
    concurrency = _slice(contract, "| **Concurrency** |", "\n")
    for token in ("A second real update of the same skill halts `halted-for-concurrent-run` while the first holds "
                  "its run lock (init.md §1b)", "`--detect-only` and `--dry-run` take no lock"):
        assert token in concurrency, token
    for gone in ("PID", "self-heal", "minutes", "renews", "\u2014"):
        assert gone not in concurrency, gone
    assert "no mode writes to the shared workspace clone before write.md §9" in concurrency
    rules = _slice(text, "## Workflow Rules", "## Stages")
    assert "source-tree-missing" in rules and "reads nothing from its output" not in rules
    # The halt-time cleanup sits where halts fire (#593): each step file's halt procedure, which SKILL.md names
    rule = _slice(rules, "- Every HALT, ABORT or other exit before step 7", "\n")
    assert "runs the **Halt procedure** of the step file it fires in" in rule
    assert "`{runStateHelper}` `halt` call" in rule
    assert 'close --tree "{source_tree}"' not in rules and "{runLockHelper}" not in rules
    for path in STEP_FILES:
        procedure = _halt_procedure(path)
        # the procedure carries every case itself: a halt must not read SKILL.md's rules or a later step file
        for gone in ("health-check.md` step 1b", "SKILL.md's Workflow Rules", "SKILL.md §Headless",
                     "halt.json", "emit-halt", "{sourceTreeHelper}", "{runLockHelper}"):
            assert gone not in procedure, (path.name, gone)
        # one helper call does the cleanup the halts used to restate (#593): the tree, the lock, the line
        block = _fence(procedure, HALT_CALL)
        # a repair reads no private source tree (init.md §6 skips §6b), so gap-driven.md passes no --tree
        for flag in HALT_FLAGS[1:] if path == GAP else HALT_FLAGS:
            assert flag in block, (path.name, flag)
        if path == GAP:
            assert "--tree" not in procedure and "source tree" not in procedure
            cases = ("It releases the run lock", "(`run-lock-not-released`)",
                     '`phase: "re-extract:<the helper\'s file name>"`')
        else:
            cases = ("removes the private source tree, releases the run lock",
                     "(`source-tree-not-removed`, `run-lock-not-released`)" if path in (INIT, DETECT, RE_EXTRACT)
                     else "(`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`)",
                     f'`phase: "{path.stem}:<the helper\'s file name>"`')
        for case in ("`--emit` in `{headless_mode}`", *cases, "it never stops on a result",
                     "which redoes nothing already done"):
            assert case in procedure, (path.name, case)
        assert "An interactive HALT displays its message and emits nothing." in procedure, path.name
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
                  "workspace-clone-not-updated", "target-ref-not-recorded", "source-tree-not-removed",
                  "interrupted-run-cleaned", "proposed-amendment:", "rollback-incomplete", "doc-fetch-failed"):
        assert token in warnings, token
    for token in ("'init:skill-name'", "'input-missing'", "'merge:verify-manual-integrity'",
                  "'merge:conflict-resolution'"):
        assert token in status, token
    taken = props["headless_decisions"]["items"]["properties"]["taken_action"]["description"]
    assert "'deferred-headless' at detect-changes.promoted-doc-prompt and detect-changes.scope-expansion" in taken
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
    """Each documented run-lock call: init's acquire, the renewals in merge and write, the release the halt
    helper runs for the halt procedure of each step file (`halt-<file>`: its --lock and --owner, handed to
    skf-run-lock.py release as skf-update-run-state.py halt does), and the health check's release."""
    guard = _slice(_read(INIT), "### 1b. Concurrency Guard", "### 2.")
    calls = {
        "acquire": _fence(guard, "uv run {runLockHelper} acquire"),
        "renew": _fence(_slice(_read(MERGE), "**Renew the run lock**", "**Choose the version this update writes**"),
                        "uv run {runLockHelper} acquire"),
        "renew-write": _fence(_slice(_read(WRITE), "**Renew the run lock first:**", "`{lock_recovery}` is"),
                              "uv run {runLockHelper} acquire"),
        "release": _fence(_slice(_read(HEALTH), "1. **Release the concurrency lock**", "1b. **"),
                          "uv run {runLockHelper} release"),
    }
    for path in STEP_FILES:
        lock = re.search(r'\[(--lock "[^"]+" --owner "[^"]+")\]', _fence(_halt_procedure(path), HALT_CALL))
        assert lock, path.name
        calls[f"halt-{path.name}"] = "uv run {runLockHelper} release " + lock.group(1)
    return calls


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
    # the owner carries the run folder's id, so the next update can find what an interrupted run left
    assert '--owner "update-skill:{skill_name}:{run_id}"' in calls["acquire"]
    for name in calls:
        if name != "acquire":
            assert '--owner "{lock_owner}"' in calls[name], name
    # the stale time is stated once, as the flag every acquire passes, never restated in the prose
    for name in ("acquire", "renew", "renew-write"):
        assert "--stale-after 60" in calls[name], name
    assert calls["renew"] == calls["renew-write"]
    released = {name: " ".join(calls[name].replace("\\\n", " ").split())
                for name in calls if name == "release" or name.startswith("halt-")}
    assert len(released) == 1 + len(STEP_FILES) and len(set(released.values())) == 1, released
    for path in sorted(UPDATE.rglob("*.md")):
        assert not re.search(r"60[ -]minute", _read(path)), path.name
    guard = _slice(_read(INIT), "### 1b. Concurrency Guard", "### 2.")
    for token in ("**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.**",
                  "bind `{lock_owner}` ← `owner`", "`stale_replaced`", "`run-lock-replaced:",
                  "**Clean up an interrupted update.**", "`interrupted-run-cleaned: {stale_replaced.held_by}:",
                  "`interrupted-run-not-cleaned: {stale_replaced.held_by}:",
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
                  "The halt's release (step 3 of the halt procedure) removes a lock this acquire took"):
        assert token in merge_renewal, token
    write_renewal = _slice(_read(WRITE), "**Renew the run lock first:**", "Update `{skill_package}/metadata.json`:")
    # the halt's rollback undoes what the run wrote: no recovery by hand (#587)
    for token in ("step 4 §8 may have waited at its gate", "`{lock_recovery}` is, outside gap-driven mode",
                  "the halt removed `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`",
                  "which step 4 created for this update", "in gap-driven mode",
                  "the halt restored the package and the skill brief from the snapshot step 4 took"):
        assert token in write_renewal, token
    assert "manual recovery" not in write_renewal
    merge = _read(MERGE)
    assert (merge.index("### 6b. Write Merged Files to Disk") < merge.index("**Renew the run lock**")
            < merge.index("**Choose the version this update writes**") < merge.index("stage-dir --target"))
    write = _read(WRITE)
    assert (write.index("### 2. Write Updated metadata.json") < write.index("**Renew the run lock first:**")
            < write.index("Update `{skill_package}/metadata.json`:") < write.index("### 3."))
    rule = _slice(_slice(_read(SKILL), "## Workflow Rules", "## Stages"),
                  "- Every HALT, ABORT or other exit before step 7", "\n")
    assert "releases the run lock" in rule and "A halt never falls through to step 6" in rule
    for path in STEP_FILES:
        procedure = _halt_procedure(path)
        assert "`run-lock-not-released`" in procedure, path.name
        # the helper's order: undo, then the tree, then the lock, then the line
        if path in (MERGE, WRITE):
            assert (procedure.index("first undoes what this run wrote")
                    < procedure.index("removes the private source tree")), path.name
    halt = _module(RUN_STATE, "skf_update_run_state_halt_order").halt
    source = inspect.getsource(halt)
    order = [source.index(mark) for mark in ("rollback(", "SOURCE_TREE_HELPER", "RUN_LOCK_HELPER")]
    assert order == sorted(order)
    assert "the Stack Skill Guard" in _slice(_read(INIT), "**Release contract:**", "### 2.")
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
                  "after write.md §6's provenance fixes and after write.md §7's skill-check edits (all error.phase "
                  "'write:verify-manual-integrity')", "a failed write in write.md §2 to §5 (error.phase "
                  "'write:artifact-write')", "only after §6 and §7, the last checks that can halt"):
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

    def acquire(run_id: str) -> tuple[dict, dict]:
        code, out = _lock_main(lock_module, calls["acquire"], {**base, "run_id": run_id}, capsys)
        assert code == 0 and out["acquired"] is True, out
        return out, {**base, "lock_owner": out["owner"]}

    a, run_a = acquire("a1B2c3D4")
    assert a["stale_replaced"] is None and a["stale_after_minutes"] == 60
    assert a["owner"] == "update-skill:lib:a1B2c3D4", a["owner"]  # the run folder's id, set at activation
    assert Path(a["lock"]).as_posix() == lock.as_posix()
    # a second update halts while the lock is fresh; the message names the file to delete when no update runs
    code, b = _lock_main(lock_module, calls["acquire"], {**base, "run_id": "e5F6g7H8"}, capsys)
    assert code == 3 and b["acquired"] is False and b["held_by"] == a["owner"]
    assert str(lock) in b["message"] and "stale" in b["message"]
    # the first renews before merge.md and write.md write (`refreshed` true: still its lock), and releases at the end
    for renewal in ("renew", "renew-write"):
        code, renewed = _lock_main(lock_module, calls[renewal], run_a, capsys)
        assert code == 0 and renewed["refreshed"] is True, renewal
    code, released = _lock_main(lock_module, calls["release"], run_a, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()
    code, again = _lock_main(lock_module, calls["halt-write.md"], run_a, capsys)
    assert code == 0 and again["released"] is False and again["reason"] == "absent"

    # A waits at a gate past the stale time, B takes the lock over: A's renewal halts (exit 3), A's halt leaves
    # B's lock, and B's release removes it
    a, run_a = acquire("a2B2c3D4")
    age()
    b, run_b = acquire("b2B2c3D4")
    assert b["stale_replaced"] == {"held_by": a["owner"], "held_since": stale_since}
    code, renewed = _lock_main(lock_module, calls["renew"], run_a, capsys)
    assert code == 3 and renewed["held_by"] == b["owner"]
    code, left = _lock_main(lock_module, calls["halt-init.md"], run_a, capsys)
    assert code == 0 and (left["released"], left["reason"]) == (False, "not-owner") and lock.exists()
    code, released = _lock_main(lock_module, calls["release"], run_b, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()
    # B finished and released while A still waited: A's renewal exits 0 but takes the lock anew (`refreshed`
    # false, nothing replaced), so A halts before it writes, and A's halt releases the lock that renewal took
    code, renewed = _lock_main(lock_module, calls["renew-write"], run_a, capsys)
    assert code == 0 and (renewed["acquired"], renewed["refreshed"], renewed["stale_replaced"]) == (True, False, None)
    code, released = _lock_main(lock_module, calls["halt-write.md"], run_a, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()

    # B's lock went stale too while B waited: A's renewal replaces it (`refreshed` false, `stale_replaced` names
    # B), A halts and releases, and B's own renewal then finds no lock and halts as well
    a, run_a = acquire("a3B2c3D4")
    age()
    b, run_b = acquire("b3B2c3D4")
    age()
    code, renewed = _lock_main(lock_module, calls["renew"], run_a, capsys)
    assert code == 0 and renewed["refreshed"] is False
    assert renewed["stale_replaced"] == {"held_by": b["owner"], "held_since": stale_since}
    code, released = _lock_main(lock_module, calls["halt-merge.md"], run_a, capsys)
    assert code == 0 and released["released"] is True
    code, renewed = _lock_main(lock_module, calls["renew-write"], run_b, capsys)
    assert code == 0 and (renewed["refreshed"], renewed["stale_replaced"]) == (False, None)
    code, released = _lock_main(lock_module, calls["halt-write.md"], run_b, capsys)
    assert code == 0 and released["released"] is True and not lock.exists()

    # the PID and time lines an older SKF version wrote name no owner and go stale the same way
    lock.write_bytes(b"12345\n2020-01-01T00:00:00Z\n")
    code, c = _lock_main(lock_module, calls["acquire"], {**base, "run_id": "c4D5e6F7"}, capsys)
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
                  '`phase: "merge:new-version-folder"`, `path: "{skill_package}/metadata.json"`'):
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
    """gap-driven.md §4's spot-check asks definition-lines, the rules write §6's verify applies (#584)."""
    text = _read(GAP)
    assert yaml.safe_load(_frontmatter(text))["verifyProvenanceCompletenessProbeOrder"] == VERIFIER_PATHS
    assert "verifyProvenanceCompletenessProbeOrder" not in _frontmatter(_read(RE_EXTRACT))  # moved with §0 (#600)
    # one missing-helper policy for the verifier in every stage file: advisory, and never a line found by eye
    comment = _comment_before(_frontmatter(text), "verifyProvenanceCompletenessProbeOrder")
    assert "when §4 bullet 2 first needs it" in comment and "records `unknown`" in comment
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


def test_6_fixes_through_the_verifier_and_skips_the_set_diff_for_a_reference_app(tmp_path, capsys):
    """§6 writes verify's JSON beside the lock and hands it to fix; a reference app gets no orphans (#549, #584)."""
    six_a = _slice(_read(WRITE), "### 6. Provenance Completeness", "### 7.")
    verify = _fence(six_a, "uv run {verifyProvenanceCompletenessHelper} verify")
    fix = _fence(six_a, "uv run {verifyProvenanceCompletenessHelper} fix")
    assert f'-o "{VERIFY_JSON}"' in verify and f'--verify "{VERIFY_JSON}"' in fix
    assert '--manual-inventory "{manual_inventory}"' in fix and "[--no-line-moves]" in fix
    for token in ("- `summary.set_diff`: `not-applicable` for a reference app (`scope_type: reference-app`",
                  "its `status` comes from `stale[]`, `citations[]` and `node_kinds[]` alone",
                  "note `set diff not applicable: reference app` in the Validation Summary, never as a WARN",
                  "- **`manual_verify.ok` is false** (a [MANUAL] block changed): HALT with status "
                  "`halted-for-manual-mismatch`",
                  '`phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] '
                  'blocks changed after the provenance fixes: ..."`',
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
    found = _slice(_read(GAP), "   - **If export found:**", "   - Record verification outcome:")
    calls.append((_fence(found, "uv run {" + verifier + "} definition-lines"), verifier))
    six_a = _slice(_read(WRITE), "### 6. Provenance Completeness", "### 7.")
    for sub in ("verify", "fix"):
        calls.append((_fence(six_a, "uv run {" + verifier + "} " + sub), verifier))
    kind_at = re.findall(r"`(uv run \{" + verifier + r"\} kind-at [^`]*)`", _read(WRITE))
    assert len(kind_at) == 1, kind_at
    calls += [(call, verifier) for call in kind_at]
    assert len(calls) == 16
    for call, helper in calls:
        assert _unquoted_placeholders(call, helper) == [], call


def test_node_kinds_are_looked_up_with_kind_at():
    """§6's node-kind fix runs kind-at with the patterns file as --recipes (#584); write §2 relabels by the Relabel
    Rule that file states once, which runs the same call (W3-create-extraction handoff, #600)."""
    write = _read(WRITE)
    frontmatter = yaml.safe_load(_frontmatter(write))
    # one name for extraction-patterns.md in every stage file, as re-extract.md names it
    assert "extractionPatternsProbeOrder" not in frontmatter and "{extractionPatterns}" not in write
    assert "{extractionPatterns}" not in _read(RE_EXTRACT)
    assert frontmatter["extractionPatternsDataProbeOrder"] == [
        "{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md",
        "{project-root}/src/skf-create-skill/references/extraction-patterns.md"]
    two = _slice(write, "### 2. Write Updated metadata.json", "### 3.")
    six_a = _slice(write, "### 6. Provenance Completeness", "### 7.")
    match = re.search(r"`(uv run \{verifyProvenanceCompletenessHelper\} kind-at [^`]*)`", six_a)
    assert match, "no kind-at call"
    assert '--recipes "{extractionPatternsData}"' in match.group(1)
    assert "which runs the ast-grep recipes for its language" not in two
    assert "`status` is `found`" in six_a and "never invent a kind" in six_a.replace("Never", "never")
    assert "run the recipes `{extraction" not in six_a
    # §2 states no copy of the general rule: it relabels by the rule's one home and keeps only update's own clauses
    relabel = _slice(two, "**Label violations.**", "\n")
    assert "relabel it by the `## Relabel Rule` section of `{extractionPatternsData}`" in relabel
    assert "## Relabel Rule" in _read(SRC / "skf-create-skill" / "references" / "extraction-patterns.md")
    for gone in ("kind-at --source-root", "so `direct-read` becomes `source-read`", "**Where the kind and the tool come from:**",
                 "T1 needs evidence that an ast-grep rule matched"):
        assert gone not in relabel, gone


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_documented_kind_at_call_runs(tmp_path, capsys):
    """The kind-at call write §2 and §6 document finds a recipe's kind with the probe-ordered patterns (#584)."""
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
                  "once the queued `metadata_patches[]` above are applied"):
        assert token in counts, token
    # the drift gate's own text says no new, modified or rescoped export gets here; write states only its action
    assert "drift gate halted" not in counts and "A stack never reaches this step" not in two
    assert (two.index("  **Judgment payload") < two.index("  **Public API counts under the drift override**")
            < two.index("  **Shape:**"))
    assert "- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);" in _drift_gate()
    zero_a = _zero_a()
    assert "and on every rescope, whose stats recount would count the public API there" in zero_a
    # write §2's counts paragraph above is the one statement of the kept counts: §3 no longer catalogues what the
    # override makes other stages do (#600 w3 leanness-3)
    assert "keeps the public API counts" not in zero_a and "no spot-check in §4 moves a line" not in zero_a
    deleted = _slice(_read(GAP), "   - **If the entry is `DELETED_EXPORT` (rescope, rule R1):**", "\n")
    assert "drift gate halted" not in deleted and "reaches this branch" not in deleted  # no unreachable route (#600)
    init = _slice(_read(INIT), "- `--allow-workspace-drift` (gap-driven mode only)", "\n")
    assert "counts no public API there" in init
    assert "which every new or modified export does, and on every rescope" in init
    flags = _slice(_read(CONTRACT), "| **Flags** |", "\n")
    assert "a gap that needs the pinned tree, a rescope included, halts `halted-for-workspace-drift`" in flags
    # the rescope's amendment is not in the brief before step 4 §6b writes it: the halt leaves the brief as it
    # was, and a re-run asks again (W2 handoff: rule R1's brief write is idempotent and deferred)
    gate = _drift_gate()
    assert "A rescope's amendment is not in the skill brief yet (rule R1): step 4 §6b writes it, so this halt " \
           "leaves the brief as it was" in gate
    message = _fence(gate, "Workspace drift blocks {N} gap(s)")
    for gone in ("Kept in skill-brief.yaml", "re-run adds them again", "scope.exclude {path}"):
        assert gone not in message and gone not in gate, gone
    r1 = _slice(_read(GAP), "- **R1: DELETED_EXPORT (rescope).**", "\n")
    for token in ("give the manifest entry a `rescope` object", "This step writes neither to the brief: step 4 §6b "
                  "writes both", "skips an amendment or an exclude path the brief already holds",
                  "`proposed-amendment: excluded {path} (scope-expansion); not written:"):
        assert token in r1, token
    in_place = _slice(_read(MERGE), "**Write the merged files in place**", "**Do NOT write here:**")
    assert ("skip an amendment the brief already holds (same `action`, `category` and `path`) and a path "
            "`scope.exclude` already lists, so a re-run never adds them twice") in in_place
    summary = yaml.safe_load(_read(REPO_ROOT / "changes" / "update-drift-override-halts.yaml"))["summary"]
    for token in ("no count of the public API", "and as a rescope (a gap that takes an export out of the skill's "
                  "scope) does", "the stats keep the public API counts `metadata.json` records",
                  "A rescope's scope amendment reaches the skill brief only when the repair writes, so the halt "
                  "leaves the brief as it was"):
        assert token in summary, token
    assert "(removals, provenance line fixes" not in summary and "already wrote to the skill brief" not in summary


EXTRACT_PUBLIC_API = SRC / "shared" / "scripts" / "skf-extract-public-api.py"
EXTRACT_PUBLIC_API_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py",
    "{project-root}/src/shared/scripts/skf-extract-public-api.py",
]


def test_forge_tier_follows_the_ast_extraction_protocol():
    """The #556 pre-release fix for the AST extraction protocol, update part, through the recipe runner (W2
    handoff): detect-changes Category B runs skf-extract-public-api.py --mode full once over the files to extract,
    re-extract reads its output and never runs it again, gap-driven.md §4a runs it over its own file set, and the
    workers read by eye only the forms the recipes leave out."""
    text = _read(RE_EXTRACT)
    # re-extract runs the runner nowhere now: §4a, its one run, moved to gap-driven.md with its probe order (#600)
    assert "extractPublicApiProbeOrder" not in yaml.safe_load(_frontmatter(text))
    assert yaml.safe_load(_frontmatter(_read(GAP)))["extractPublicApiProbeOrder"] == EXTRACT_PUBLIC_API_PATHS
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
    # a repair never loads re-extract.md, so its tool line names only step 2's run (#600 architecture-4)
    assert "`{extractPublicApiHelper}` `--mode full` (step 2), which runs every recipe" in tool
    assert "gap-driven" not in tool
    assert "`find_code` only as the fallback of Known Limitation #4" in tool
    assert "find_code_by_rule" not in tool
    two = _slice(text, "### 2. Extract Changed Files", "### 3. Deep Tier")
    assert 'cat > "{run_dir}/extract-files.json"' not in two  # step 2's helper wrote the list
    assert ("For each file `{run_dir}/extract-files.json` lists (step 2 wrote it: the MODIFIED and ADDED files and "
            "each MOVED file's new path)") in two
    worker = _slice(text, "launch a subprocess that:", "3. Extract each export")
    assert ("2. At Forge tier and above, takes this file's exports from step 2's `{run_dir}/extraction.json` and "
            "`export-details.json` (§1b); at Quick tier, matches the file's text as §1b says") in worker
    zero_a = _slice(_read(GAP), "### 4a. Targeted Re-Extraction Branch", "### 5.")
    own = _fence(zero_a, "uv run {extractPublicApiHelper} --mode full")
    for token in ('--files-from "{run_dir}/remediation-files.json"', '[--scope-type "{scope_type}"]', "--head-cap 0"):
        assert token in own, token
    # a test report may name a file the brief's scope leaves out as an export's home
    assert "--brief" not in own and "It takes no `--brief`" in zero_a
    assert "On exit 1 (`incomplete`) run it once more" in zero_a
    init = _slice(_read(INIT), "**Check metadata.json exists:**", "**Detect skill")
    assert "`scope_type` and `language` (when present)" in init
    assert "Follow the AST Extraction Protocol in" not in zero_a
    # §4a states what is read by eye itself: re-extract.md §1b, which it used to point to, is not loaded (#600)
    assert "as §1b says" not in zero_a and "Known Limitation #11 in `{extractionPatternsData}`" in zero_a


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_documented_runner_calls_run(tmp_path):
    """detect-changes Category B's runner call and gap-driven.md §4a's run as written (W2 handoff).

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
        "remediation-exports.json": _fence(_slice(_read(GAP), "### 4a.", "### 5."),
                                           "uv run {extractPublicApiHelper}"),
    }
    expected = {
        # the line of the name, not of the decorator above it; the excluded file's export is kept
        "extraction.json": {("search", "pkg/api.py", 5), ("kept", "pkg/hidden.py", 1)},
        # out of the brief's scope, and still read: §4a passes no --brief
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
    """gap-driven.md §3, the workspace drift guard (re-extract.md §0.a before the carve, #600)."""
    return _slice(_read(GAP), "### 3. Verify the Workspace Holds the Pinned Commit", "### 4.")


def _write_3() -> str:
    return _slice(_read(WRITE), "### 3. Write Updated provenance-map.json", "### 4.")


DRIFT_NOTE = "(drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha}"
GAP_BULLET = "- **Gap-driven mode** (`no_reextraction` true, gap-driven.md §4):"


def test_drift_status_binding_and_warning():
    """gap-driven.md §3 binds the status and both short SHAs; only `overridden` changes later steps (#530)."""
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
    assert "Then run the drift gate below, and continue to §4 only when it passes." in overridden
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
    return _slice(_read(GAP), DRIFT_GATE, "\n### 4.")


def test_drift_gate_halts_before_merge_on_every_new_or_modified_export():
    """Under the override every new or modified export halts in gap-driven.md, before merge (#530, #557)."""
    text = _read(GAP)
    gate = _drift_gate()
    for token in ("update-skill writes nothing read there, neither a provenance line nor a signature, parameter "
                  "list, return type or node kind",
                  "Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the "
                  "provenance map holds the export",
                  "merge Priority 4 replaces a modified export's content with a fresh extraction",
                  "merge Priority 5 appends a new export's content",
                  "HALT with status `halted-for-workspace-drift` before merge runs",
                  "merge writes nothing and §4a never runs",
                  "A rescope's amendment is not in the skill brief yet (rule R1)",
                  "Every `DELETED_EXPORT` needs the tree as well: in gap-driven mode it is a rescope (rule R1)",
                  'phase: "re-extract:workspace-drift"'):
        assert token in gate, token
    # severity and the map no longer decide whether an entry halts: the #551 conditions are gone
    for gone in ("an export the map holds needs no new line",
                 "a non-empty `remediation_paths[]` and a blocking severity",
                 "Gaps that need a line:", "{rule R3 | remediation paths | cited export not in the map}"):
        assert gone not in gate, gone
    assert re.findall(r"^- `([^`]+)`: ", gate, re.M) == GATE_REASONS
    # the gap §4a would halt with nothing to scan halts here first under the override (#558 item 4)
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
    headless = _slice(gate, "The halt procedure takes", "\n")
    assert '`reason: "drift-override: {N} gap(s) need the pinned tree: {name} ({reason}), ..."`' in headless
    # the gate runs before any spot-check; it says §4a never runs, which §4a, reached by no entry then, does not
    # repeat (#600 leanness-6)
    assert text.index("**Drift gate") < text.index("1. Read the gap-derived manifest") < text.index("### 4a.")
    zero_a = _slice(text, "### 4a. Targeted Re-Extraction Branch", "### 5.")
    assert "Never under the drift override" not in zero_a and "drift override" not in zero_a
    four = _slice(text, "4. Set `no_reextraction: true`", "\n")
    assert "a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` entry at that line" in four
    # the MOVED_EXPORT bullet states the one override rule a spot-check acts on (#600 leanness-6)
    assert "drift override" not in four and "so §4a never runs" not in four
    zero_a = _zero_a()
    # what the override keeps out, by name: write §2 still counts the public surface at `{source_root}`
    assert ("so update-skill takes no provenance line, signature, parameter list, return type or node kind "
            "from it") in zero_a
    assert "takes nothing from it" not in zero_a
    assert "lines move and node kinds are looked up as usual" in zero_a
    # write.md §2 and §6 state that they look up no node kind under the override, so §3 does not (#600 w3 leanness-3)
    assert "look up no node kind" not in zero_a
    write = _read(WRITE)
    assert "run no recipe at `{source_root}`, so no `kind-at`" in _slice(write, "  **Label violations.**", "\n")
    assert "the tree read is not the recorded commit, so run no `kind-at`" in _slice(write, "2. **Node kinds.**", "\n")


def test_every_change_category_halts_or_passes_the_drift_gate():
    """Each category gap-driven.md §1 can emit is named once by the gate: as one that halts or one that passes (#557)."""
    bullet = _slice(_read(GAP), "   - **`change_category`**", "\n")
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


def test_merge_states_no_unreachable_override_route():
    """gap-driven.md's drift gate halts on every new, modified or rescoped export before merge (#557), so merge Priority 1, 4
    and 5 no longer narrate a route no entry takes (#600 leanness); Priority 2 keeps the rule that acts."""
    merge = _read(MERGE)
    for start, end in (("**Priority 1", "**Priority 2"), ("**Priority 4", "**Priority 5"), ("**Priority 5", "**Priority 6")):
        section = _slice(merge, start, end)
        assert "drift override" not in section and "reaches this priority" not in section, start
    two = _slice(merge, "**Priority 2", "**Priority 3")
    assert "A `MOVED_EXPORT` that recorded `unknown` (the drift override among the causes)" in two


def test_relabel_runs_no_recipe_under_the_override():
    """write §2 looks up no node kind at HEAD: the violation stays, with a WARN that names the drift (#557)."""
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    relabel = _slice(two, "**Label violations.**", "\n")
    drift = _slice(relabel, "**Under the drift override**", "Rewrite `{forge_version}/provenance-map.json`")
    for token in ("run no recipe at `{source_root}`, so no `kind-at`",
                  "Leave each violation that needs a kind from the tree in place",
                  "list it as a WARN ending ` " + DRIFT_NOTE + ")`",
                  "a relabel that reads nothing from the tree still applies",
                  "With the status `ok` or `skipped`, run the lookup as the rule says"):
        assert token in drift, token
    # the gate follows the rule whose lookup it gates, and the re-run keeps the shape (#550)
    assert relabel.index("`## Relabel Rule`") < relabel.index("**Under the drift override**")
    assert "re-run the helper with the same payload and `--shape`" in relabel


def test_name_lookup_filters_by_the_citation_file():
    """Same-name entries: the citation's normalized file, then its line, pick one; none left is not found (#530)."""
    lookup = _slice(_read(GAP), "   - Look up the export in the provenance map's `entries[]`", "\n")
    for token in ("take the entries whose `export_name` equals the name",
                  "**With a `source_citation`,** keep those whose `source_file`, normalized as write.md §6",
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
    """A drifted HEAD moves no line and pins none, and each drift `unknown` says why (#530).

    Only a rule R5 `MOVED_EXPORT` reaches a spot-check under the override (the drift gate halts every new, modified
    or rescoped export), so its bullet states the rule once and the outcome bullet repeats none of it; apply names
    the drift in its WARN for a `verified` R5 line itself (#600 leanness-6).
    """
    text = _read(GAP)
    outcome = _slice(text, "   - Record verification outcome:", "\n")
    moved = _slice(outcome, "`moved` (the file defines", "`missing` (")
    assert "record it as `new_location`" in moved
    assert "drift" not in outcome and "write.md §3 lists a drift WARN" not in outcome
    assert "a cited `NEW_EXPORT` it kept from being spot-checked" not in outcome  # the gate halts those now (#557)
    moved_export = _slice(text, "   - **If the entry is `MOVED_EXPORT`", "\n")
    assert ("it records `unknown` with `unknown_reason: drift-override` where it would record `moved`, and sets no "
            "`new_location`") in moved_export
    assert "Record in `pinned_definition_lines` the definition lines its `remediation` lists" in moved_export
    assert text.count("`unknown_reason: drift-override`") == 1, "the R5 drift rule is stated once"
    assert "unknown_reason" not in _read(RE_EXTRACT)
    cited = _slice(text, "     - **If the manifest entry has a `source_citation`", "\n")
    # the drift gate halts before this branch: it states only what it does (#600 leanness)
    assert "reaches this branch" not in cited and "drift gate halted" not in cited
    assert "and is not a `MOVED_EXPORT`:** run the \"export found\" branch's `definition-lines` call" in cited
    assert "unknown_reason: drift-override" not in cited  # no cited export is kept from its spot-check any more
    assert "so step 6 writes" not in cited and "write.md §3 adds a full entry" in cited
    # the reachability gate reads barrels; the drift gate halts every new export first (#557), unnarrated (#600)
    gate = _slice(text, "   - **Public-reachability gate (`NEW_EXPORT` only):**", "\n")
    assert "**Under the drift override**" not in gate and "reaches this gate" not in gate
    assert "reachability: not-checked" not in text and "`not-checked`" not in _write_3()
    record = _fence(text, '"verification": [')
    for field in ('"unknown_reason": "<drift-override', '"pinned_definition_lines":', '"in_map":', '"map_entry":',
                  '"severity":', '"reachability":'):
        assert field in record, field
    breakdown = _slice(record, '"confidence_breakdown": {', '"T2": 0')
    assert ("each cited export not in the map that the spot-check pinned and the public-reachability gate passed"
            in _slice(breakdown, '"T1-low":', "\n"))
    assert ("other than a pinned cited export that passed the reachability gate (counted under T1-low)"
            in _slice(breakdown, '"unlabeled":', "\n"))
    # the records reach step 6 through the run folder, before §5 sends the run on (#587, W3 handoff)
    three = _slice(text, "3. Write the gap-driven records to `{run_dir}/reextract-records.json`", "\n")
    assert "before §5 sends the run on" in three
    assert 'cat > "{run_dir}/reextract-records.json"' in record
    summary = _slice(text, '"**Gap-driven re-extraction.**', "\n")
    assert summary.endswith("or a line the drift override kept from being moved): {unknown_count}.\"")
    qualifier = _slice(text, "When `{workspace_drift_status}` is `overridden`, add: \"Every check read HEAD", "\n")
    assert "no line was moved or pinned.\"" in qualifier and "reachability" not in qualifier
    assert text.index('"**Gap-driven re-extraction.**') < text.index(qualifier)
    assert "`provenance_map.exports`" not in text
    # rule R5 gives its routing only: the spot-check outcomes and the WARNs are stated where they act (#600)
    r5 = _slice(_read(GAP), "- **R5: MOVED_EXPORT", "\n")
    assert "Route the entry to §4's spot-check only, with no public-reachability gate and no §4a." in r5
    for gone in ("drift", "records `moved`", "write.md §3", "`provenance-unverified`"):
        assert gone not in r5, gone
    # merge moves citations only for a `moved` outcome
    priority2 = _slice(_read(MERGE), "**Priority 2", "**Priority 3")
    assert "move citations only for an export whose gap-driven.md §4 spot-check recorded `moved`" in priority2
    assert "`MOVED_EXPORT` that recorded `unknown` (the drift override among the causes), `verified` or `missing` moves none" in priority2


def _apply_call() -> str:
    return _fence(_write_3(), "uv run {buildChangeManifestHelper} apply")


def _argv_with(call: str, helper: str, values: dict, keep: tuple = ()) -> list[str]:
    """A documented call's arguments with only the `[--flag ...]` groups `keep` names, filled in."""
    kept = re.sub(r"\[(--[^\]]*)\]", lambda m: m.group(1) if m.group(1).split()[0] in keep else "", call)
    return _argv(kept, helper, values)


def test_write_adds_the_cited_export_entry_and_names_the_drift(tmp_path, capsys):
    """write §3 hands the map to apply, which adds one entry per pinned cited export and names the drift in every WARN
    under the override (#530; W3 handoff: the map is written by script from the run's records, never by hand)."""
    three = _write_3()
    bullet = _slice(three, GAP_BULLET, "\n")
    for token in ("A cited `NEW_EXPORT` or `MODIFIED_EXPORT` the map does not hold",
                  "whose public-reachability gate passed", "at most one per `export_name` and `source_file`",
                  "at the line its `source_citation` names (`verified`) or at `new_location` (`moved`)",
                  "`confidence: T1-low`", "`extraction_method: source-read`", "`ast_node_type: null`",
                  "`signature_source: T1-low`", "from step 4's `merge-records.json`", "naming the drift under the override"):
        assert token in bullet, token
    assert "drift gate halted" not in bullet  # an unreachable route is not narrated (#600 leanness)
    assert "**For each export in the updated skill (normal mode only):**" not in three
    assert "never by hand" in _slice(three, "### 3. Write Updated provenance-map.json", "```bash")
    call = _apply_call()
    for token in ('--drift-head "{head_short_sha}" --drift-pinned "{pinned_short_sha}"',
                  '--reextract-records "{run_dir}/reextract-records.json"', '--merge-records "{run_dir}/merge-records.json"',
                  '--manual-sections-preserved "{manual_sections_preserved}"', '-o "{forge_version}/provenance-map.json"'):
        assert token in call, token
    assert "Pass `--drift-head` and `--drift-pinned` only when `{workspace_drift_status}` is `overridden`" in three
    six = _slice(three, "- **0:**", "\n")
    assert "Bind `{provenance_spot_check_warnings}` ← its `warnings`" in six
    # run the documented call: the pinned cited export gets its source-read entry, every WARN names the drift
    forge_version = tmp_path / "forge data" / "lib" / "1.0.0"
    forge_version.mkdir(parents=True)
    old = {"export_name": "search", "export_type": "function", "source_library": "lib", "source_file": "pkg/api.py",
           "source_line": 5, "confidence": "T1", "extraction_method": "ast-grep",
           "ast_node_type": "function_definition", "signature_source": "T1"}
    (forge_version / "provenance-map.json").write_bytes(json.dumps({"entries": [old]}).encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "reextract-records.json").write_bytes(json.dumps({"mode": "gap-driven", "verification": [
        {"export_name": "fresh", "gap_category": "NEW_EXPORT", "severity": "High", "verification": "verified",
         "in_map": False, "map_entry": None, "source_citation": {"file": "pkg/new.py", "line": 3},
         "reachability": "public"},
        {"export_name": "search", "gap_category": "MOVED_EXPORT", "severity": "Low", "verification": "unknown",
         "in_map": True, "map_entry": None, "unknown_reason": "drift-override", "pinned_definition_lines": [7]}],
        "files": []}).encode("utf-8"))
    (run_dir / "merge-records.json").write_bytes(json.dumps({"exports": [
        {"export_name": "fresh", "export_type": "function", "params": ["x"]}]}).encode("utf-8"))
    values = {"update_type": "gap-driven", "forge_version": str(forge_version), "run_dir": str(run_dir),
              "skill_name": "lib", "generation_date": "2026-10-01T10:00:00Z", "test_report_run_id": "r1",
              "forge_tier": "Forge", "manual_sections_preserved": "0", "map_source_commit": "abc",
              "map_source_ref": "v1", "head_short_sha": "1234567", "pinned_short_sha": "abcdef0"}
    argv = _argv_with(call, "buildChangeManifestHelper", values, keep=(
        "--provenance-map", "--reextract-records", "--merge-records", "--test-report-run-id", "--drift-head"))
    manifest = _module(BUILD_MANIFEST, "skf_build_change_manifest_apply_prose")
    assert manifest.main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    written = json.loads((forge_version / "provenance-map.json").read_bytes())
    fresh = next(e for e in written["entries"] if e["export_name"] == "fresh")
    assert (fresh["source_file"], fresh["source_line"], fresh["extraction_method"], fresh["params"]) == \
        ("pkg/new.py", 3, "source-read", ["x"])
    assert written["entries"][0] == old  # an unknown on a MOVED_EXPORT leaves its entry for a person
    note = DRIFT_NOTE.replace("{head_short_sha}", "1234567").replace("{pinned_short_sha}", "abcdef0")
    assert summary["warnings"] == [
        f"provenance: search: unknown {note}; no line taken from HEAD; definition lines per the test report: [7])"]
    assert (written["test_report_run_id"], written["source_commit"]) == ("r1", "abc")


def test_new_entry_labels_pass_the_stats_helper():
    """The labels write §3 gives a pinned cited export pass skf-render-metadata-stats.py's label check (#530)."""
    bullet = _slice(_write_3(), GAP_BULLET, "\n")
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
    row = _slice(two, "- `gap-driven.md §3` accepted a drifted workspace", "\n")
    assert "this row is where the report shows §3's override warning" in row
    assert ("(workspace drift accepted: spot-checks read HEAD {head_short_sha}, not pinned {pinned_short_sha}; "
            "no provenance line moved or pinned)") in row
    assert "WARN, provenance entry left for a person to decide (write.md §3)" in report
    five_b = _slice(report, "### 5b. Result Contract", "### 6.")
    assert "`workspace_drift_overridden` (gap-driven.md §3)" in five_b
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
    # SKILL.md gives the caller one clause; gap-driven.md §3 holds what the override keeps out
    flags = _slice(_read(CONTRACT), "| **Flags** |", "\n")
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
    """Both docs pages say a rescope halts under the override, as gap-driven.md's drift gate does (#557).

    Its public API recount needs the pinned tree, the brief amendment is not written yet so the brief stays as it
    was, and a run
    that still goes ahead keeps the public API counts metadata.json records.
    """
    gate = _drift_gate()
    assert "- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);" in gate
    assert "A rescope's amendment is not in the skill brief yet (rule R1): step 4 \u00a76b writes it, so this halt " \
           "leaves the brief as it was" in gate
    counts = _slice(_read(WRITE), "  **Public API counts under the drift override**", "\n")
    assert "the values `{skill_package}/metadata.json` records in `stats`" in counts
    gap_driven = ("`--allow-workspace-drift`", "Update Skill with `--from-test-report`")
    for name in ("verifying-a-skill.md", "workflows.md"):
        line = _doc_line(name, *gap_driven)
        rescope = _slice(line, "A rescope (", "a re-run asks again")
        for token in ("stops", "the same way", "public API", "needs the pinned tree", "amendment", "has not written",
                      "stays as it was"):
            assert token in rescope, (name, token)
        assert "the stats keep the public API counts `metadata.json` records" in line, name


# --------------------------------------------------------------------------
# Gap-driven routing: blocking gaps with no path, split-body findings
# --------------------------------------------------------------------------

BLOCKING_RULE = ("blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or "
                 "unrecognized one is blocking, like `Critical` and `High`")


def _not_found() -> str:
    return _slice(_read(GAP), "   - **If export not found in provenance map:**", "   - **If export found:**")


def test_one_severity_rule_in_gap_driven_and_write():
    """A missing or unrecognized severity is blocking wherever a gap is routed by severity (#558 item 5)."""
    severity = _slice(_read(GAP), "   - **`severity`**", "\n")
    assert "A severity is " + BLOCKING_RULE in severity
    assert "only a `Medium`, `Low` or `Info` gap may degrade to `unknown`" in severity
    # §4 and §4a cite §1 bullet 3's rule instead of restating it (#600 w3 leanness-5)
    assert "and a blocking `severity` (§1 bullet 3), and the rule R3 branch above did not take it" in _not_found()
    assert BLOCKING_RULE not in _not_found()
    assert _read(GAP).count(BLOCKING_RULE) == 1
    text = _read(GAP)
    assert "`severity` is `Critical` or `High`" not in text  # the test a missing severity slipped through
    used_by = _slice(text, "**Used by:** §4 bullet 2", "**Purpose:**")
    assert "a blocking `severity` (§1 bullet 3), that the rule R3 case below does not take" in used_by
    # the prose around §4a states the same rule, an unrecognized severity included
    for gone in ("citation-less Critical/High", "the Critical/High HALT",
                 "Critical and High gaps, and gaps with no severity"):
        assert gone not in text, gone
    assert "for a gap with a blocking `severity` (§1 bullet 3) and no citation that pins a line" in \
        _slice(text, "**Purpose:**", "\n")
    # re-extract.md keeps no gap-driven exception in its Rules: a repair never loads it (#600 architecture-4)
    assert "**Exception (gap-driven mode):**" not in _read(RE_EXTRACT)
    template = " ".join(_fence(text, "Targeted re-extraction failed for {N} gap(s).").split())
    assert ("A blocking gap (any severity but Medium, Low or Info, a missing or unrecognized one included) must "
            "resolve to AST provenance.") in template
    why = _slice(text, "**Why halt instead of degrading to `unknown`:**", "\n")
    assert "a null citation on a blocking gap lets the skill pass re-test" in why
    assert "Critical or High gap by definition" not in why
    refused = _slice(_write_3(), "- **3** (`status` `refused`):", "\n")
    assert "with a severity other than `Medium`, `Low` or `Info`, a missing one included" in refused
    assert "An `unknown` `NEW_EXPORT` the map does not hold with a `Medium`, `Low` or `Info` severity" in \
        _slice(_write_3(), GAP_BULLET, "\n")
    # the helper applies the same rule, case-insensitively
    assert _module(BUILD_MANIFEST, "skf_build_change_manifest_severity").NON_BLOCKING == ("medium", "low", "info")


def test_blocking_gap_without_a_path_halts_in_gap_driven_before_merge():
    """No citation that pins a line and no path in the Remediation: §4a lists it with files_scanned 0 (#558)."""
    text = _read(GAP)
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
                  "route this entry to §4a (Targeted Re-Extraction Branch), whatever its `resolved_paths[]`",
                  "With an empty list it has nothing to scan and lists the entry in `unresolved[]` with "
                  "`files_scanned: 0`",
                  "halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included"):
        assert token in blocking, token
    assert "a blocking gap never gets here, whatever its `resolved_paths[]`" in unknown
    assert "`remediation_paths[]` is empty OR" not in text  # the empty-paths way into `unknown` is gone
    zero_a = _slice(text, "### 4a. Targeted Re-Extraction Branch", "### 5.")
    used_by = _slice(zero_a, "**Used by:** §4 bullet 2", "**Purpose:**")
    # §4a's own procedure steps are items: step 4 is merge.md
    assert ("an empty one leaves nothing to scan, so item 4 puts the entry straight into `unresolved[]` with "
            "`files_scanned: 0`") in used_by
    assert "that the rule R3 case below does not take" in used_by
    assert "A run in which §4 bullet 2 routes no entry here skips this section entirely" in zero_a
    match = _slice(zero_a, "4. **Match by name**", "\n")
    assert "An entry with no path set to scan (an empty `resolved_paths[]`) is not matched" in match
    assert "search the extraction results of its own `resolved_paths[]`" in match
    # a rule R3 gap scans the source file its documentation cites, which §1 resolved through the helper
    r3 = _slice(used_by, "- a provenance-completeness gap (rule R3", "\n")
    assert ("Its `resolved_paths[]` is the path set to scan: §1 filled them from the source file its "
            "documentation cites when its remediation named none") in r3
    failures = _slice(zero_a, "5. **Track failures across all qualifying entries.**", "\n")
    assert "every entry item 4 had nothing to scan for (`files_scanned: 0`)" in failures
    assert "(item 5): the symbol was found, just not public, so it does not trigger item 5's HALT" in zero_a
    template = _fence(zero_a, "Targeted re-extraction failed for {N} gap(s).")
    for token in ('- {name} ({severity or "no severity"})', 'remediation_paths: {paths, or "none named"}',
                  'rejected_paths:    {each refused path (its reason), or "none"}',
                  "files_scanned:     {count}", "a) Add a `file:line` citation", "b) Edit the Remediation text",
                  "c) Downgrade the gap(s) to Medium/Low/Info"):
        assert token in template, token
    exit_ = _slice(zero_a, "   Exit with status `halted-for-remediation-path`", "\n")
    for token in ("under `--dry-run` too", "Step 4 (merge) has not run; no partial writes",
                  'phase: "re-extract:targeted-reextraction"'):
        assert token in exit_, token
    # §1 lists the fields the route reads; §4 states the route once, where it acts
    paths = _slice(_read(GAP), "   - **`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**", "\n")
    assert "§4a scans only `resolved_paths`" in paths
    for gone in ("depending on severity", "halts the run with `halted-for-remediation-path`", "records `unknown`"):
        assert gone not in paths, gone


def test_gap_driven_dry_run_stops_before_merge():
    """gap-driven.md §5 routes a --dry-run to the report, so a gap-driven --dry-run never loads merge (#558 item 6)."""
    text = _read(GAP)
    five = _slice(text, "### 5. Display the Repair Summary and Route", "\n- **Otherwise**")
    for token in ("load `{reportFile}` (report.md, NOT `{resumeStepFile}`)", "so a gap-driven `--dry-run` writes nothing",
                  "A halt in §3 or §4a (the drift gate, the targeted re-extraction) stops a `--dry-run`"):
        assert token in five, token
    assert yaml.safe_load(_frontmatter(text))["reportFile"] == "report.md"
    assert "Skip all remaining sections of step 3" not in text and "Skip sections 1" not in text
    six = _slice(_read(RE_EXTRACT), "### 6. Route to Next Step", "\n- **Otherwise**")
    assert "load `report.md` (NOT `{nextStepFile}`)" in six
    assert "Proceeding to merge" not in _slice(text, '"**Gap-driven re-extraction.**', "\n")  # §5's branch says it
    halt = "a gap-driven.md halt such as `halted-for-remediation-path` or `halted-for-workspace-drift` still stops it"
    assert halt in _slice(_read(CONTRACT), "| **Flags** |", "\n")
    assert halt in _slice(_read(INIT), "- `--dry-run` to run detect-changes + re-extract", "\n")


def test_write_keeps_a_documented_defensive_halt(tmp_path):
    """A blocking `unknown` that still reaches write §3 halts with a documented status and phase (#558).

    `halted-for-remediation-path` tells a pipeline nothing was written; this halt comes after merge rewrote
    SKILL.md in place, so it takes `blocked`, the schema's status for a halt with no code of its own. `apply`
    refuses it (exit 3) and writes nothing, and the halt's rollback restores what merge wrote (#587).
    """
    halt = _slice(_write_3(), "- **3** (`status` `refused`):", "\n")
    for token in ("HALT with status `blocked`", "write no `metadata.json`, `provenance-map.json` or other artifact",
                  '`phase: "write:provenance-map"`', '`path: "{forge_version}/provenance-map.json"`',
                  "blocking-gap-unresolved", "`apply` wrote nothing, and no null citation is written",
                  # merge Priority 5 and 8 may have edited reference files too
                  "The halt restored SKILL.md and references/ from the snapshot step 4 took"):
        assert token in halt, token
    assert "restore them from version control or a backup" not in _read(WRITE)
    forge_version = tmp_path / "forge"
    forge_version.mkdir()
    (forge_version / "provenance-map.json").write_bytes(b'{"entries": []}\n')
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "reextract-records.json").write_bytes(json.dumps({"mode": "gap-driven", "verification": [
        {"export_name": "lost", "gap_category": "NEW_EXPORT", "severity": None, "verification": "unknown",
         "in_map": False, "map_entry": None}]}).encode("utf-8"))
    values = {"update_type": "gap-driven", "forge_version": str(forge_version), "run_dir": str(run_dir),
              "skill_name": "lib", "generation_date": "2026-10-01T10:00:00Z", "forge_tier": "Quick",
              "manual_sections_preserved": "0", "map_source_commit": "", "map_source_ref": ""}
    argv = _argv_with(_apply_call(), "buildChangeManifestHelper", values,
                      keep=("--provenance-map", "--reextract-records"))
    code, out = _run_script(BUILD_MANIFEST, argv)
    assert code == 3 and out == {"status": "refused", "blocking_unresolved": [{"export_name": "lost",
                                                                              "severity": None}]}
    assert (forge_version / "provenance-map.json").read_bytes() == b'{"entries": []}\n'
    status = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["status"]["enum"]
    assert "blocked" in status and "halted-for-remediation-path" in status


def test_split_body_findings_route_to_a_structural_fix():
    """A Source inside the skill package marks a split-body finding: STRUCTURAL_FIX, never MODIFIED_EXPORT (#547)."""
    zero = _zero()
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
    forward = _slice(_read(GAP), "   - **`STRUCTURAL_FIX`** (rule R2)", "\n")
    assert "No spot-check, no provenance lookup, no `entries[]` change." in forward
    assert "a `STRUCTURAL_FIX` (a split-body consistency finding among them)" in _drift_gate()


def test_merge_edits_the_reference_file_of_a_split_body_finding():
    """The SKILL.md body is authoritative (test-skill coverage-check §1b): merge edits the reference file (#547)."""
    priority8 = _slice(_read(MERGE), "**Priority 8:", "**Priority 8b")
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
    block = _slice(_write_3(), "**The update operation block**", "`manual_sections_preserved` =")
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
                  "pass no `--shape` (the helper's default, the library shape)"):
        assert token in shape, token
    # init.md's Stack Skill Guard is the one gate for stacks: write does not narrate a route no stack takes (#600)
    assert "Stack Skill Guard" not in shape and "**This guard is the single gate for stack skills**" in _read(INIT)
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
    """gap-driven.md §1, the gap translation (detect-changes.md §0 before the carve, #600)."""
    return _slice(_read(GAP), "### 1. Translate the Test Report's Gaps", "### 2.")


def _routing_table() -> dict[str, str]:
    """gap-driven.md §1's table: each ledger category slug -> the Change Category its row names."""
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
    # §4 routes a missing export or type to targeted re-extraction whatever its severity, and never halts on one
    route = _slice(_not_found(), "     - **If the manifest entry has no `source_citation` (or one whose spot-check "
                   "above pinned no line), the branches above did not take it, and it asks to document a missing "
                   "export or type**", "\n")
    for token in ("its `category` is `missing-export` or `missing-type`", "route it to §4a when its "
                  "`resolved_paths[]` is not empty, whatever its severity", "The route follows the gap's category, "
                  "not its severity", "record it `unknown` as the bullet below does", "so it does not halt"):
        assert token in route, token
    # §4 routes on the category alone: §1 chose it, for an older report too
    assert "title names a missing export or type" not in route
    category = _slice(_zero(), "   - **`gap_id`** and **`category`**", "\n")
    for token in ("For a report older than the ledger, `category` is the slug of the row bullet 2 chose",
                  "so §4 routes on `category` alone"):
        assert token in category, token
    # the route is stated where it acts: §4 bullet 2, §4a's Used by and its no-halt exception, nowhere else
    zero_a = _slice(_read(GAP), "### 4a. Targeted Re-Extraction Branch", "### 5.")
    used_by = _slice(zero_a, "**Used by:** §4 bullet 2", "**Purpose:**")
    assert "that §4 bullet 2 routes here by its `category` (a missing export or type)" in used_by
    failures = _slice(zero_a, "5. **Track failures across all qualifying entries.**", "\n")
    assert "except a `Medium`, `Low` or `Info` missing export or type" in failures
    assert "missing export or type" not in _slice(zero_a, "**Purpose:**", "\n")
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
    assert yaml.safe_load(_frontmatter(_read(GAP)))["parseGapsProbeOrder"] == _probe("skf-parse-gaps.py")
    assert "parseGapsProbeOrder" not in _frontmatter(_read(DETECT))  # moved with detect-changes §0 (#600)
    read = _slice(zero, "1. **Read the gaps through `{parseGapsHelper}`**", "2. **Translate each gap")
    for token in ("It reads the gap ledger test-skill wrote beside the report "
                  "(`test-findings-<the report's run id>.json`), "
                  "which holds every gap of a run test-skill's hard gate blocked (its `stepsCompleted` ends at "
                  "`hard-gate`)", "Never read gaps from the report by eye", "`test-report: <entry>`",
                  'phase: "detect-changes:parse-gaps"', "`LEDGER_INVALID`",
                  "`--provenance-map` whenever init.md §4 loaded one"):
        assert token in read, token
    assert "--ext" not in read  # the helper takes the map's extensions itself, none collected by eye
    for gone in ("1. Read the **Gap Report** section", "Read the **Coverage Analysis** section",
                 "any substring matching a recognized source file extension"):
        assert gone not in _read(GAP), gone
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
    """gap-driven.md §4a takes parse-gaps' resolved files; every root check is the helper's, a rule R3 gap's cited
    source file included (#583)."""
    zero_a = _slice(_read(GAP), "### 4a. Targeted Re-Extraction Branch", "### 5.")
    files = _slice(zero_a, "2. **The file set**", "\n")
    for token in ("is the `resolved_paths[]` of every entry routed here, as they are",
                  "§1's `{parseGapsHelper}` resolved them under `{source_root}`",
                  "never scan a refused path, and never expand or check a path by hand",
                  "`outside-root`", "`symlink-outside-root`", "`not-found`", "`no-match`"):
        assert token in files, token
    for gone in ("**Expand `remediation_paths[]`**", "using the provenance map's file patterns",
                 "Deduplicate the resolved file set", "no `..` part", "each file once"):
        assert gone not in zero_a, gone
    paths = _slice(_zero(), "   - **`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**", "\n")
    call = re.search(r"`(uv run \{parseGapsHelper\} paths [^`]*)`", paths)
    assert call, "gap-driven.md §1 runs no root check for a rule R3 gap's cited file"
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
    gates = _slice(_read(CONTRACT), "| **Gates** |", "\n")
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
    assert "In gap-driven mode (gap-driven.md §1 translated none of the report's gaps)" in one
    five_b = _slice(_read(REPORT), "### 5b. Result Contract", "### 6.")
    for token in ("`unconsumed-test-report` (init.md §4b)", "`test-report:` entries", "`no-baseline-time`",
                  "`moved-check-skipped`", "`unknown-language`"):
        assert token in five_b, token
    # the flag's cell stays the flag's: the offer is listed with the gates
    flags = _slice(_read(CONTRACT), "| **Flags** |", "\n")
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
    (run_dir / "category-c.json").write_bytes(json.dumps({"category_c": {"renamed_files": [], "renamed_exports": []},
                                                          "evidence": {}, "unpaired": {}}).encode("utf-8"))
    (run_dir / "ccc-pairs.json").write_bytes(json.dumps({"renamed_files": []}).encode("utf-8"))
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
        "source_root": str(src), "brief_path": str(forge / "lib" / "skill-brief.yaml"),
        "provenance_map_path": str(provenance)}))
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [r["path"] for r in out["already_tracked"]] == ["docs/AGENTS.md"]
    assert [r["path"] for r in out["already_in_scope"]] == ["docs/llms.txt"]
    assert [(r["path"], r["prior_action"]) for r in out["unresolved"]] == [("docs/CLAUDE.md", "deferred-headless")]


def test_the_run_folder_carries_the_helper_files_and_step_7_removes_it(tmp_path, capsys):
    """The helpers pass JSON through one run folder; §2.2 and §3 read the helper files and the category JSON from it,
    with no echo and no list typed by hand."""
    detect = _read(DETECT)
    # SKILL.md On Activation creates it, before the first halt can fire (W1 and W3 handoffs): one place binds it
    activation = _slice(_read(SKILL), "3. **Resolve the shared helpers and create the run folder**",
                        "4. **Resolve workflow customization.**")
    assert ('mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d '
            '"{project-root}/_bmad-output/.skf-run/skf-update-skill-XXXXXXXX"') in _fence(activation, "mktemp -d")
    assert "Bind `{run_dir}` ← the path it prints and `{run_id}` ← its folder name less `skf-update-skill-`" \
        in activation
    assert '"phase": "on-activation:run-folder"' in _fence(activation, "emit-halt")
    for steps in (_slice(detect, "## Steps", "### 1. Scan Current Source State"),
                  _slice(_read(GAP), "## Steps", "### 1. Translate")):
        assert "mktemp" not in steps and "Unless `{run_dir}` is already bound" not in steps
    assert "which step 2 created" not in _read(HEALTH)
    health = _read(HEALTH)
    one_c = _slice(health, "1c. **Remove this update's run folder**", "\n")
    assert 'rm -rf "{run_dir}"' in one_c and "in every mode" in one_c
    marks = [health.index("1b. **Remove the private source tree**"), health.index("1c. **Remove this update's"),
             health.index("2. Load `{nextStepFile}`")]
    assert marks == sorted(marks)
    assert "_bmad-output/.skf-run/` that step 7 removes" in _slice(_read(CONTRACT), "| **Outputs** |", "\n")
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
    # Category C's rules paired nothing, the CCC check found b.py renamed to c.py: the helpers read both files,
    # and the category JSON holds neither
    (run_dir / "category-c.json").write_bytes(json.dumps({
        "category_c": {"renamed_files": [], "renamed_exports": []}, "evidence": {},
        "unpaired": {"deleted_files": ["b.py"], "added_files": ["c.py"]}}).encode("utf-8"))
    (run_dir / "ccc-pairs.json").write_bytes(json.dumps({
        "renamed_files": [{"old_path": "b.py", "new_path": "c.py"}]}).encode("utf-8"))
    (run_dir / "categories.json").write_bytes(json.dumps({
        "category_d": {}, "degraded_mode": False, "update_mode": "normal"}).encode("utf-8"))
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
    detect, init, gap = _read(DETECT), _read(INIT), _read(GAP)
    calls = [
        (_fence(gap, "uv run {parseGapsHelper} parse"), "parseGapsHelper"),
        (re.search(r"`(uv run \{parseGapsHelper\} paths [^`]*)`", gap).group(1), "parseGapsHelper"),
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
        (_fence(_slice(gap, "### 4a.", "### 5."), "uv run {extractPublicApiHelper}"),
         "extractPublicApiHelper"),
        (_fence(detect, "uv run {hashContentHelper} compare"), "hashContentHelper"),
        # Category D's two piped calls, each on its own side of the pipe
        (_fence(detect, "uv run {detectScriptsAssetsHelper} detect").split("|")[0], "detectScriptsAssetsHelper"),
        (_fence(detect, "uv run {detectScriptsAssetsHelper} detect"), "newFileDiffHelper"),
    ]
    for call, helper in calls:
        assert _unquoted_placeholders(call, helper) == [], call


# --------------------------------------------------------------------------
# Run state: dry-run in every mode, the snapshot and rollback, the emitter at
# every halt, deferred headless skips, the skill-name input, the terminal
# sequence (#585, #587, #593, #594 update parts, and their handoffs)
# --------------------------------------------------------------------------

EMITTER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
RUN_STATE = SRC / "shared" / "scripts" / "skf-update-run-state.py"
DETECT_DOCS = SRC / "shared" / "scripts" / "skf-detect-docs.py"
CUSTOMIZE = UPDATE / "customize.toml"


def _cmd_args(call: str, helper: str, values: dict, keep: tuple = ()) -> list[str]:
    """A documented call's arguments, cut at its first redirection or heredoc, with the `[--flag ...]` groups
    `keep` names, filled in."""
    call = re.split(r"\s(?:<<|<|>)\s?", call.replace("\\\n", " "), maxsplit=1)[0]
    kept = re.sub(r"\[(--[^\]]*)\]", lambda m: m.group(1) if m.group(1).split()[0] in keep else "", call)
    return _argv(kept, helper, values)


def _heredoc(call_block: str) -> str:
    """The body of the `<<'SKF_JSON'` heredoc in a fenced block, its indentation in a list item stripped."""
    match = re.search(r"<<'SKF_JSON'\n(.*?)\n[ \t]*SKF_JSON", call_block, re.S)
    assert match, "no SKF_JSON heredoc"
    return "\n".join(line.strip() for line in match.group(1).splitlines())


def _sample(template: str) -> dict:
    """A heredoc's JSON template with its `<...>` placeholders filled by sample values."""
    text = re.sub(r'"<[^>"]*>"', '"x"', template)
    text = re.sub(r"\[<[^>\]]*>\]", "[]", text)
    text = re.sub(r"<[^<>]*>", "1", text)
    for brace in re.findall(r'"\{[a-z_]+\}"', text):
        text = text.replace(brace, '"lib"')
    return json.loads(text)


def _emit(argv: list[str], payload: dict) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(payload), capture_output=True,
                          encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def test_every_route_out_of_step_3_honours_dry_run():
    """--dry-run writes nothing in any mode: gap-driven and docs-only leave step 3 through §6 too (#587)."""
    text = _read(RE_EXTRACT)
    assert "proceed directly to the merge step (section 5 or equivalent)" not in text
    docs_only = _slice(text, "### 1. Check for Docs-Only Mode", "### 1b.")
    for token in ("Re-fetch each URL in `changed_urls` of `{run_dir}/change-manifest.json`",
                  "`{run_dir}/reextract-records.json`", '{"mode": "docs-only", "changed_urls":',
                  "then go straight to §6 (Route to Next Step), whose `dry_run_mode` branch holds for a docs-only "
                  "skill too: a docs-only `--dry-run` never loads merge.md"):
        assert token in docs_only, token
    six = _slice(text, "### 6. Route to Next Step", "\n- **Otherwise**")
    assert "Every route out of this step comes here, the docs-only one (§1) included" in six
    # a gap-driven run leaves from gap-driven.md §5, whose dry-run branch loads the report (#600 architecture-4)
    assert "(report.md, NOT `{resumeStepFile}`)" in _slice(_read(GAP), "### 5.", "\n- **Otherwise**")
    # the read-only modes write no brief: the brief §1b and §1c amend is the run folder's copy, and rule R1 writes
    # nothing before step 4 (W1 handoff: read-only modes write the skill brief)
    detect = _read(DETECT)
    brief = _slice(detect, "**The brief this run reads.**", "\n")
    for token in ("copy it to `{run_dir}/skill-brief.yaml` and bind `{brief_path}` to the copy",
                  "the brief itself stays as it was", "`proposed-amendment: {action} {path} ({category}); not written:"):
        assert token in brief, token
    for section in ("### 1b.", "### 1c."):
        body = _slice(detect, section, "**Record for evidence report:**")
        assert "{forge_data_folder}/{skill_name}/skill-brief.yaml" not in body, section
        assert "{brief_path}" in body, section
    # §1b's decision protocol, which §1c follows, writes every amendment to `{brief_path}` (#600 leanness-7)
    assert "every brief write goes to `{brief_path}` (the run folder's copy in a read-only mode)" in \
        _slice(detect, "### 1b.", "### 1c.")
    assert "`--brief \"{brief_path}\"`" in detect or '--brief "{brief_path}"' in detect
    for path in (REPORT,):
        for section in ("### 1a.", "### 1b."):
            assert "**Proposed skill brief amendments (not written):**" in _slice(_read(path), section, "→ Load"), section


def test_a_halt_after_the_first_gap_driven_write_restores_the_package(tmp_path):
    """merge §6b snapshots before its first in-place write; a later halt's rollback restores it; write §10's finish
    closes the window (#587: a gap-driven halt after merge restores the package from its snapshot)."""
    merge, write = _read(MERGE), _read(WRITE)
    # SKILL.md binds the helper once, at activation, so every step file and every halt reach it
    assert _skill_binding("runStateHelper") == "src/shared/scripts/skf-update-run-state.py"
    for path in STEP_FILES:
        assert "runStateProbeOrder" not in yaml.safe_load(_frontmatter(_read(path))), path.name
    record = _slice(merge, "**Record what this run writes**", "**Create the version folder**")
    begin = _fence(record, "--mode in-place")
    # every step file's halt runs the same call; its rollback undoes the repair
    filled = {"run_dir": "D", "source_tree": "T", "forge_data_folder": "F", "skill_name": "lib", "lock_owner": "o"}
    calls = {path.name: _cmd_args(_fence(_halt_procedure(path), HALT_CALL), "runStateHelper", filled,
                                  keep=("--tree", "--lock", "--emit")) for path in STEP_FILES}
    # gap-driven.md passes no --tree: a repair reads no private source tree (init.md §6 skips §6b)
    gap = calls.pop(GAP.name)
    assert len({tuple(call) for call in calls.values()}) == 1, calls
    assert "--tree" not in gap and gap == [arg for arg in calls[INIT.name] if arg not in ("--tree", "T")]
    rollback = _fence(_halt_procedure(WRITE), HALT_CALL)
    finish = re.search(r"`(uv run \{runStateHelper\} finish [^`]*)`", _slice(write, "### 10. Close the Rollback Window",
                                                                           "### 11.")).group(1)
    in_place = _slice(merge, "**Write the merged files in place**", "**Do NOT write here:**")
    assert in_place.index("rescopes' brief amendments") < in_place.index('manual-verify "{run_dir}/SKILL.md"') < \
        in_place.index("Copy `{run_dir}/SKILL.md` to `{skill_package}/SKILL.md`")
    assert merge.index("**Record what this run writes**") < merge.index("**Write the merged files in place**")
    package = tmp_path / "skills" / "lib" / "1.0.0" / "lib"
    forge = tmp_path / "forge data"
    forge_version = forge / "lib" / "1.0.0"
    for path, body in ((package / "SKILL.md", b"# lib\n\n<!-- [MANUAL:notes] -->\nmine\n<!-- [/MANUAL:notes] -->\n"),
                       (package / "metadata.json", b'{"name": "lib"}\n'), (package / "references" / "api.md", b"api\n"),
                       (forge_version / "provenance-map.json", b'{"entries": []}\n'),
                       (forge / "lib" / "skill-brief.yaml", b"scope:\n  exclude: []\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    run_dir = tmp_path / "run" / "skf-update-skill-a1B2c3D4"
    run_dir.mkdir(parents=True)
    before = {p: p.read_bytes() for p in (package / "SKILL.md", package / "references" / "api.md",
                                          forge_version / "provenance-map.json", forge / "lib" / "skill-brief.yaml")}
    values = {"run_dir": str(run_dir), "skill_package": str(package), "forge_version": str(forge_version),
              "forge_data_folder": str(forge), "skill_name": "lib"}
    state = _module(RUN_STATE, "skf_update_run_state_prose")
    assert state.main(_cmd_args(begin, "runStateHelper", values)) == 0
    # the repair writes the brief, SKILL.md, a reference, the map and a new evidence report, then a check halts
    (forge / "lib" / "skill-brief.yaml").write_bytes(b"scope:\n  exclude: [pkg/x.py]\n")
    (package / "SKILL.md").write_bytes(b"# lib\n\nrepaired, [MANUAL] lost\n")
    (package / "references" / "api.md").write_bytes(b"api fixed\n")
    (forge_version / "provenance-map.json").write_bytes(b'{"entries": [{"export_name": "x"}]}\n')
    (forge_version / "evidence-report.md").write_bytes(b"## Update Operation\n")
    assert state.main(_cmd_args(rollback, "runStateHelper", values)) == 0
    assert {p: p.read_bytes() for p in before} == before and not (forge_version / "evidence-report.md").exists()
    # a run that passed every check closes the window: a later rollback undoes nothing
    run2 = tmp_path / "run" / "skf-update-skill-e5F6g7H8"
    run2.mkdir()
    values2 = {**values, "run_dir": str(run2)}
    assert state.main(_cmd_args(begin, "runStateHelper", values2)) == 0
    (package / "SKILL.md").write_bytes(b"repaired and verified\n")
    assert state.main(_cmd_args(finish, "runStateHelper", values2)) == 0
    assert state.main(_cmd_args(rollback, "runStateHelper", values2)) == 0
    assert (package / "SKILL.md").read_bytes() == b"repaired and verified\n"
    assert not (run2 / "snapshot").exists()


def test_an_interrupted_update_is_cleaned_up_by_the_next_one(tmp_path, capsys):
    """init §1b takes over a stale lock and undoes what its run left, found by the run id in the lock's owner
    (#587: clean an interrupted run at init with the run-lock stale rule, not with a late version-exists halt)."""
    calls = _lock_calls()
    guard = _slice(_read(INIT), "### 1b. Concurrency Guard", "### 2.")
    cleanup = _fence(_slice(guard, "**Clean up an interrupted update.**", "**Release contract:**"),
                     "uv run {runStateHelper} rollback")
    # the helper finds the run folder from the owner: no run id parsed or path built by hand
    for token in ('--run-root "{project-root}/_bmad-output/.skf-run"', '--owner "{stale_replaced.held_by}"',
                  '--skill "{skill_name}"', "--remove-run-dir"):
        assert token in cleanup, token
    assert "<its run id>" not in cleanup
    record = _slice(_read(MERGE), "**Record what this run writes**", "**Create the version folder**")
    begin = _fence(record, "--mode new-version")
    lock_module = _module(RUN_LOCK_HELPER, "skf_run_lock_interrupted")
    state = _module(RUN_STATE, "skf_update_run_state_interrupted")
    root = tmp_path / "project"
    forge, skills = root / "forge", root / "skills"
    (skills / "lib" / "1.0.0" / "lib").mkdir(parents=True)
    base = {"forge_data_folder": str(forge), "skill_name": "lib"}
    # run A took the lock, recorded its new version, created it, and died
    code, a = _lock_main(lock_module, calls["acquire"], {**base, "run_id": "a1B2c3D4"}, capsys)
    assert code == 0
    run_a = root / "_bmad-output" / ".skf-run" / "skf-update-skill-a1B2c3D4"
    run_a.mkdir(parents=True)
    values = {**base, "run_dir": str(run_a), "skill_group": str(skills / "lib"), "new_version": "1.0.1"}
    assert state.main(_cmd_args(begin, "runStateHelper", values)) == 0
    capsys.readouterr()
    (skills / "lib" / "1.0.1" / "lib").mkdir(parents=True)
    (forge / "lib" / "1.0.1").mkdir(parents=True)
    lock = forge / "lib" / ".skf-update.lock"
    held = json.loads(lock.read_bytes())
    lock.write_bytes((json.dumps({**held, "acquired_at": "2020-01-01T00:00:00Z"}) + "\n").encode("utf-8"))
    # run B replaces the stale lock, reads A's run id from its owner and undoes what A left
    code, b = _lock_main(lock_module, calls["acquire"], {**base, "run_id": "e5F6g7H8"}, capsys)
    assert code == 0 and b["stale_replaced"]["held_by"] == "update-skill:lib:a1B2c3D4"
    values = {"project-root": str(root), "stale_replaced.held_by": b["stale_replaced"]["held_by"],
              "skill_name": "lib"}
    assert state.main(_cmd_args(cleanup, "runStateHelper", values)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "rolled-back" and out["run_dir_removed"] is True
    assert not (skills / "lib" / "1.0.1").exists() and not (forge / "lib" / "1.0.1").exists()
    assert (skills / "lib" / "1.0.0" / "lib").is_dir() and not run_a.exists()
    # an owner of another skill, or an older SKF's owner with no run id, names no run folder: nothing changes
    for owner in ("update-skill:other:a1B2c3D4", "update-skill:lib"):
        assert state.main(_cmd_args(cleanup, "runStateHelper", {**values, "stale_replaced.held_by": owner})) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "no-run-folder", owner


def _halt_sites() -> tuple[set, set]:
    """Every status and error.phase the update-skill step files name at a HALT."""
    statuses, phases = set(), set()
    for path in (SKILL, *STEP_FILES):
        text = _read(path)
        statuses |= set(re.findall(r'(?:halt procedure: |halt procedure takes |halt procedure with )`status: '
                                   r'"([a-z-]+)"`', text))
        statuses |= set(re.findall(r"HALT[^`\n]{0,40}with status `([a-z-]+)`", text))
        statuses |= set(re.findall(r'"status": "([a-z-]+)", "phase"', text))
        phases |= set(re.findall(r'phase: "([a-z-]+:[a-z-]+)"', text)) | set(re.findall(r'"phase": "([a-z-]+:[a-z-]+)"', text))
    return statuses, phases


def test_every_halt_line_validates_against_the_schema(tmp_path):
    """Each halt prints its line through the shared emitter, with the skf_update wrapper, and every status and
    phase a halt names validates (#593: about 17 halt sites, the concurrency halt included)."""
    statuses, phases = _halt_sites()
    enum = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["status"]["enum"]
    assert statuses - {"success", "no-changes", "detect-only", "dry-run"} <= set(enum), statuses - set(enum)
    for expected in ("init:skill-name", "init:concurrency-guard", "init:stack-skill-guard", "init:validate-artifacts",
                     "init:forge-tier", "init:source-tree", "detect-changes:doc-hashes", "detect-changes:category-c",
                     "re-extract:workspace-drift", "re-extract:rescope", "merge:verify-manual-integrity",
                     "merge:snapshot", "merge:manual-plan", "write:provenance-map", "write:active-symlink"):
        assert expected in phases, expected
    assert len(phases) >= 17
    for path in (SKILL, *STEP_FILES):
        text = _read(path)
        for gone in ("emit the halt envelope per SKILL.md", "emit `SKF_UPDATE_RESULT_JSON` with", "top-level `status`"):
            assert gone not in text, (path.name, gone)
    run_dir = tmp_path / "skf-update-skill-a1B2c3D4"
    run_dir.mkdir()
    state = _module(RUN_STATE, "skf_update_run_state_halt_lines")
    for path in STEP_FILES:
        procedure = _halt_procedure(path)
        block = _fence(procedure, HALT_CALL)
        template = _sample(_heredoc(block))
        assert {"status", "phase", "path", "reason", "skill_name", "version", "previous_version",
                "update_mode"} <= set(template), path.name
        # the documented call, headless, prints the line through the shared emitter
        argv = _cmd_args(block, "runStateHelper", {"run_dir": str(run_dir)}, keep=("--emit",))
        payload = {**template, "status": "blocked", "phase": f"{path.stem}:x", "reason": "r", "path": "a/b",
                   "skill_name": "lib", "version": "1.0.0", "previous_version": "1.0.0", "update_mode": "normal"}
        proc = subprocess.run([sys.executable, str(RUN_STATE), *argv], input=json.dumps(payload),
                              capture_output=True, encoding="utf-8")
        assert proc.returncode == 0, (path.name, proc.stderr)
        summary, line = proc.stdout.splitlines()
        assert json.loads(summary)["emitted"] is True
        assert json.loads(line.split("SKF_UPDATE_RESULT_JSON: ", 1)[1])["skf_update"]["error"]["phase"] == \
            f"{path.stem}:x"
        # every status and phase a halt of this step names validates, as the helper hands it to the emitter
        for phase in sorted(p for p in phases if p.startswith(path.stem + ":")):
            payload = {**payload, "status": "halted-for-write-failure" if phase.startswith("merge:new") else "blocked",
                       "phase": phase}
            if path == WRITE:
                payload["files_written"] = []
            code, out, err = state.emit_halt(run_dir, payload, ["run-lock-not-released: a/b"])
            assert code == 0, (path.name, phase, err)
            line = json.loads(out.split("SKF_UPDATE_RESULT_JSON: ", 1)[1])
            assert line["skf_update"]["error"]["phase"] == phase and "status" not in line
            assert "run-lock-not-released: a/b" in line["skf_update"]["warnings"]
    # the first halt can fire before the run folder exists: SKILL.md's line has no --run-dir
    activation = _slice(_read(SKILL), "3. **Resolve the shared helpers and create the run folder**",
                        "4. **Resolve workflow")
    block = _fence(activation, "emit-halt")
    code, out, err = _emit(_cmd_args(block, "emitEnvelopeHelper", {}), json.loads(_heredoc(block).replace(
        "{project-root}", "/p").replace("<which helper is missing, or that stderr line>", "No space left on device")))
    assert code == 0 and json.loads(out.split(": ", 1)[1])["skf_update"]["status"] == "blocked", err


def test_headless_skips_are_deferred_for_a_person(tmp_path):
    """A headless run records an out-of-scope document or path as deferred-headless, one decision per path, and the
    next interactive run asks again (#593 item 4; W1 enhancement-1 extends it to §1c)."""
    detect = _read(DETECT)
    run_dir = tmp_path / "run"
    # §1b states the decision protocol once; §1c follows it with its own gate and fields (#600 leanness-7)
    one_b = _slice(detect, "### 1b.", "**Record for evidence report:**")
    headless = _slice(one_b, "**Headless mode (`{headless_mode}` is true):**", "\n5. ")
    assert 'action: "deferred-headless"' in headless and 'action: "skipped"' not in headless
    assert "never records a skip no person chose" in headless
    assert "except for a candidate whose `prior_action` is `deferred-headless`" in headless
    assert "Steps 4 and 5 are the decision protocol for a scope candidate, which §1c follows too" in one_b
    one_c = _slice(detect, "### 1c.", "**Record for evidence report:**")
    c_headless = _slice(one_c, "4. **Headless mode (`{headless_mode}` is true):**", "\n5. ")
    for token in ("defer each candidate as §1b step 4 does", "the gate `detect-changes.scope-expansion`",
                  "must never silently expand scope"):
        assert token in c_headless, token
    assert "uv run {emitEnvelopeHelper} record" not in one_c and "[U] Update:** HALT" not in one_c
    differences = _slice(one_c, "5. **Apply decision** as §1b step 5 does", "6. **Summary:**")
    for token in ('`category: "scope-expansion"`', "`evidence: {evidence string}` in place of `heuristic`",
                  "adds no `promoted_docs_new[]` entry", 'halts with `phase: "detect-changes:scope-reconciliation"`'):
        assert token in differences, token
    block = _fence(headless, "uv run {emitEnvelopeHelper} record")
    decision = _sample(_heredoc(block))
    assert (decision["gate"], decision["default_action"], decision["taken_action"]) == (
        "detect-changes.promoted-doc-prompt", "S", "deferred-headless")
    argv = _cmd_args(block, "emitEnvelopeHelper", {"run_dir": str(run_dir)})
    for gate in ("detect-changes.promoted-doc-prompt", "detect-changes.scope-expansion"):
        for candidate in ("docs/AGENTS.md", "llms.txt"):
            code, _out, err = _emit(argv, {**decision, "gate": gate, "evidence": {"path": candidate}})
            assert code == 0, err
    lines = (run_dir / "headless-decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4  # one per path, never collapsed
    one_c = _slice(detect, "### 1c.", "### 2. Compare")
    assert '| "deferred-headless" | null' in one_c
    # the dispatch helper reads both the deferral and the legacy headless skip as unresolved
    forge = tmp_path / "forge"
    (forge / "lib" / "1.0.0").mkdir(parents=True)
    (forge / "lib" / "1.0.0" / "drift-report-1.md").write_bytes(
        b"# Drift\n\n## Out-of-Scope Observations\n- `plugins/**` - 2 exports\n- `extras/**` - 1 export\n")
    brief = forge / "lib" / "skill-brief.yaml"
    brief.write_bytes(yaml.safe_dump({"scope": {"amendments": [
        {"action": "deferred-headless", "category": "scope-expansion", "path": "plugins/**"},
        {"action": "skipped", "category": "scope-expansion", "path": "extras/**",
         "reason": "headless: no user to prompt"}]}}).encode("utf-8"))
    call = _fence(_slice(detect, "### 1c.", "### 2. Compare"), "uv run {provenanceGapDispatchHelper} dispatch")
    code, out = _run_script(SRC / "shared" / "scripts" / "skf-provenance-gap-dispatch.py", _cmd_args(
        call, "provenanceGapDispatchHelper", {"skill_name": "lib", "baseline_version": "1.0.0",
                                              "forge_data_folder": str(forge), "brief_path": str(brief)}))
    assert code == 0 and {(c["status"], c["prior_action"]) for c in out["classified"]} == {
        ("unresolved", "deferred-headless")}


def test_a_headless_run_needs_the_skill_name(tmp_path):
    """The invocation's skill answers §1 in either mode; interactive runs pick from a list; headless halts
    input-missing (#594 update part)."""
    skill = _read(SKILL)
    assert "Bind `{requested_skill}` ← the skill name or folder path the invocation passes" in skill
    inputs = _slice(_read(CONTRACT), "| **Inputs** |", "\n")
    assert "a headless run halts `blocked` (`error.phase` `init:skill-name`, `error.reason` starting " \
           "`input-missing`)" in inputs
    one = _slice(_read(INIT), "### 1. Request Skill Path", "**Version-Aware Path Resolution:**")
    for token in ("When `{requested_skill}` is set (SKILL.md On Activation), it answers the question below in either "
                  "mode, and the prompt is not shown", 'run `uv run {skillInventoryHelper} "{skills_output_folder}"`',
                  "each `skills[]` entry whose `skf_skill` is true", "update-skill never guesses a skill",
                  '`phase: "init:skill-name"`', '`reason: "input-missing: a headless run needs the skill\'s name or '
                  'folder path as its argument"`'):
        assert token in one, token
    inventory = _module(INVENTORY_HELPER, "skf_skill_inventory_pick_list")
    skills = tmp_path / "skills folder"
    (skills / "lib" / "1.0.0" / "lib").mkdir(parents=True)
    (skills / "lib" / "1.0.0" / "lib" / "metadata.json").write_bytes(json.dumps(
        {"name": "lib", "version": "1.0.0", "generated_by": "create-skill"}).encode("utf-8"))
    (skills / "theirs").mkdir()
    (skills / "theirs" / "SKILL.md").write_bytes(b"# theirs\n")
    call = re.search(r"`(uv run \{skillInventoryHelper\} \"\{skills_output_folder\}\")`", one).group(1)
    proc = subprocess.run([sys.executable, str(INVENTORY_HELPER), *_cmd_args(call, "skillInventoryHelper", {
        "skills_output_folder": str(skills)})], capture_output=True, encoding="utf-8")
    listed = [s["name"] for s in json.loads(proc.stdout)["skills"] if s["skf_skill"]]
    assert listed == ["lib"]


def test_finished_runs_fire_on_complete_and_read_only_runs_do_not(tmp_path):
    """No-change and normal finishes write the result files and fire on_complete; detect-only and dry-run write none
    and fire nothing, and customize.toml says so (#585 update part; W1 determinism-2 and enhancement-4)."""
    hook = _read(CUSTOMIZE)
    for token in ("an update that wrote a version, or a run that found no", "It is not called for --detect-only or "
                  "--dry-run, which write no result", "nor when a run halts"):
        assert token in hook, token
    report = _read(REPORT)
    one = _slice(report, "### 1. Handle No-Change Shortcut", "### 1a.")
    assert 'with `status: "no-changes"` in the payload and `--result-dir "{forge_version}"`' in one
    assert "Then run `{onCompleteCommand}` as §5b says" in one
    for section, status in (("### 1a.", "detect-only"), ("### 1b.", "dry-run")):
        body = _slice(report, section, "→ Load")
        assert f'with `status: "{status}"` and no `--result-dir`' in body and "does not run `{onCompleteCommand}`" \
            in body, section
    five_b = _slice(report, "### 5b. Result Contract", "### 6.")
    for gone in ("Construct the envelope from in-context state", "update-skill-result-{YYYYMMDD-HHmmss}.json` (UTC "
                 "timestamp, resolution to seconds) and a copy"):
        assert gone not in five_b, gone
    emit = _fence(five_b, "uv run {emitEnvelopeHelper} emit --workflow skf-update-skill")
    payload = _sample(_heredoc(_fence(five_b, 'cat > "{run_dir}/result-context.json"')))
    run_dir = tmp_path / "skf-update-skill-a1B2c3D4"
    run_dir.mkdir()
    forge_version = tmp_path / "forge" / "lib" / "1.0.1"
    forge_version.mkdir(parents=True)
    argv = _cmd_args(emit, "emitEnvelopeHelper", {"run_dir": str(run_dir), "forge_version": str(forge_version)})
    payload = {**payload, "version": "1.0.1", "previous_version": "1.0.0", "update_mode": "normal",
               "files_written": ["SKILL.md", "metadata.json"]}
    code, out, err = _emit(argv, payload)
    assert code == 0, err
    line = json.loads(out.split("SKF_UPDATE_RESULT_JSON: ", 1)[1])["skf_update"]
    assert line["status"] == "success" and line["error"] is None
    latest = json.loads((forge_version / "update-skill-result-latest.json").read_bytes())
    assert latest["summary"]["update_status"] == "success" and latest["run_id"] == "a1B2c3D4"
    assert "{onCompleteCommand} --result-path={forge_version}/update-skill-result-latest.json" in five_b
    assert "`--detect-only`, `--dry-run` and a halt never do (customize.toml says so)" in five_b
    # a hook failure is told to the user: the line and the result files are written before the hook runs, and
    # customize.toml no longer promises it in warnings[]
    assert "the line and the result files are written before the hook runs, so they cannot carry its failure" \
        in five_b
    assert "warnings[] but never fail" not in hook and "it does not reach the result" in hook


def test_a_read_only_run_that_finds_no_change_stays_read_only():
    """detect-changes §4 sends every run that finds no change to report §1, before §5's detect-only branch: a
    --detect-only or --dry-run run there writes no result file, takes no lock and never fires on_complete (#585)."""
    report = _read(REPORT)
    one = _slice(report, "### 1. Handle No-Change Shortcut", "### 1a.")
    finished = _slice(one, "**Result files, line and hook.**", "\n")
    assert finished.startswith("**Result files, line and hook.** A normal or gap-driven run that found no change")
    guard = _slice(one, "**A read-only run stays read-only here.**", "\n")
    for token in ("When `detect_only_mode` or `dry_run_mode` is true", "detect-changes.md §4",
                  "stage no `result_contract` and write no result file", 'with `status: "no-changes"` and no '
                  "`--result-dir`", "never run `{onCompleteCommand}`", "Those modes take no run lock"):
        assert token in guard, token
    assert one.index("**Result files, line and hook.**") < one.index("**A read-only run stays read-only here.**")
    four = _slice(_read(DETECT), "### 4. Check for No-Change Shortcut", "### 5.")
    assert ("A `--detect-only` or `--dry-run` run takes this route too and stays read-only there: report.md §1 "
            "prints its line with no result file and never runs `{onCompleteCommand}`") in four
    # an interactive read-only run prints no line, so its report lists the warnings the run recorded
    for section, end in (("### 1. Handle No-Change Shortcut", "### 1a."), ("### 1a.", "### 1b."),
                         ("### 1b.", "### 2.")):
        assert "`{run_dir}/warnings.jsonl`" in _slice(report, section, end), section
    one_c = _slice(_read(HEALTH), "1c. **Remove this update's run folder**", "\n")
    assert "step 7 already printed them and wrote them into the result files" not in one_c
    assert "step 6 listed the warnings in a read-only run's report" in one_c


def test_merge_reads_the_run_state_from_disk():
    """merge §3 reads the manifest and the records step 2 and step 3 wrote to the run folder, never from memory
    (#587: state held only in context)."""
    three = _slice(_read(MERGE), "### 3. Apply Merge by Priority Order", "**Priority 1")
    for token in ("from disk, never from memory", "`{run_dir}/change-manifest.json`",
                  "`{run_dir}/reextract-records.json`", "`{run_dir}/promoted-docs.json`"):
        assert token in three, token
    assert "in-context `promoted_docs_new[]`" not in _read(MERGE)


def test_a_docs_only_skill_compares_its_document_hashes(tmp_path):
    """detect-changes reads a docs-only skill's drift with audit's compare-hashes, and §4's no-change shortcut fires
    only when every hash matches (W1 architecture-5, re-anchored by W3)."""
    detect = _read(DETECT)
    assert yaml.safe_load(_frontmatter(detect))["compareDocHashesProbeOrder"] == _probe("skf-detect-docs.py")
    one = _slice(detect, "### 1. Scan Current Source State", "### 1b.")
    for gone in ('{"degraded_mode": false, "update_mode": "normal"}` as `{run_dir}/categories.json`, so §4 reports no '
                 "change",):
        assert gone not in one
    call = _fence(one, "uv run {compareDocHashesHelper} compare-hashes")
    assert 'compare-hashes "{skill_package}/metadata.json" > "{run_dir}/doc-hashes.json"' in call
    # the helper writes the manifest from the comparison: no URL retyped into a heredoc
    assert 'cat > "{run_dir}/change-manifest.json"' not in one
    build = _fence(one, "uv run {buildChangeManifestHelper} build --doc-hashes")
    assert 'build --doc-hashes "{run_dir}/doc-hashes.json" > "{run_dir}/change-manifest.json"' in build
    assert "§4 then reports no change only when every hashed document matches" in one
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "metadata.json").write_bytes(json.dumps({"name": "docs", "source_type": "docs-only"}).encode("utf-8"))
    argv = _cmd_args(call, "compareDocHashesHelper", {"skill_package": str(package)})
    code, out = _run_script(DETECT_DOCS, argv)
    assert code == 0 and out["changed"] == [] and out["stats"]["total_tracked"] == 0
    assert "`doc-drift-not-checked: metadata.json records no doc_sources`" in one
    # one changed document: the manifest routes it to step 3, and write §2 records its new hash, so the next
    # comparison finds nothing changed and §4's no-change shortcut fires again
    doc = tmp_path / "guide.md"
    doc.write_bytes(b"v2\n")
    url = "file://" + doc.as_posix()
    (package / "metadata.json").write_bytes(json.dumps({"name": "docs", "source_type": "docs-only", "doc_sources": [
        {"url": url, "content_hash": "sha256:" + "0" * 64, "recorded_at": "2026-01-01T00:00:00+00:00"}]}).encode())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    values = {"skill_package": str(package), "run_dir": str(run_dir)}
    proc = subprocess.run([sys.executable, str(DETECT_DOCS), *_cmd_args(call, "compareDocHashesHelper", values)],
                          capture_output=True, encoding="utf-8")
    (run_dir / "doc-hashes.json").write_text(proc.stdout, encoding="utf-8")
    code, built = _run_script(BUILD_MANIFEST, _cmd_args(build, "buildChangeManifestHelper", values))
    assert code == 0 and built["no_changes"] is False and built["changed_urls"] == [url]
    refresh = _fence(_slice(_read(WRITE), "**A docs-only skill's document hashes.**", "### 3."),
                     "uv run {compareDocHashesHelper} refresh-hashes")
    assert yaml.safe_load(_frontmatter(_read(WRITE)))["compareDocHashesProbeOrder"] == _probe("skf-detect-docs.py")
    code, refreshed = _run_script(DETECT_DOCS, _cmd_args(refresh, "compareDocHashesHelper", values))
    assert code == 0 and refreshed["refreshed"] == [url]
    code, again = _run_script(DETECT_DOCS, _cmd_args(call, "compareDocHashesHelper", values))
    assert code == 0 and again["changed"] == [] and again["unchanged"] == [{"url": url}]


def test_category_c_is_the_rename_rules_by_script(tmp_path):
    """Category C runs rename-candidates: the fixed rules by script, the CCC check the only judgment (W3
    determinism-3, part of #589)."""
    detect = _read(DETECT)
    rename = _slice(detect, "**Category C: rename detection.**", "**Category D")
    call = _fence(rename, "uv run {buildChangeManifestHelper} rename-candidates")
    assert "A worker pairs" not in rename and "returns ONLY" not in rename
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "category-a.json").write_bytes(json.dumps({"category_a": {"modified": [], "added": ["pkg/new.py"],
                                                                         "deleted": ["pkg/old.py"]},
                                                          "moved_files": []}).encode("utf-8"))
    (run_dir / "extraction.json").write_bytes(json.dumps({"exports": [
        {"export_name": "f", "export_type": "function", "source_file": "pkg/new.py", "source_line": 1}]}).encode())
    (run_dir / "export-details.json").write_bytes(json.dumps({"exports": [
        {"export_name": "f", "source_file": "pkg/new.py", "params": ["x"], "return_type": None}]}).encode())
    provenance = tmp_path / "provenance-map.json"
    provenance.write_bytes(json.dumps({"entries": [{"export_name": "f", "export_type": "function",
                                                    "source_file": "pkg/old.py", "params": ["x"],
                                                    "return_type": None}]}).encode("utf-8"))
    argv = _cmd_args(call, "buildChangeManifestHelper", {
        "run_dir": str(run_dir), "provenance_map_path": str(provenance), "forge_tier": "Forge",
        "source_root": str(tmp_path)}, keep=("--extraction", "--export-details"))
    code, out = _run_script(BUILD_MANIFEST, argv)
    assert code == 0, out
    written = json.loads((run_dir / "category-c.json").read_bytes())
    assert written["category_c"]["renamed_files"] == [{"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]
    categories = _slice(detect, "**Write the category JSON**", "```bash")
    # the helpers read category-c.json themselves: its pairs are never copied by hand (determinism-3)
    assert "copied from" not in categories and "take as `--category-c` and `--ccc-pairs`" in categories
    assert '"category_c"' not in _fence(detect, 'cat > "{run_dir}/categories.json"')
    assert "to `{run_dir}/ccc-pairs.json`" in _slice(rename, "**CCC check", "\n")


def test_manual_decisions_amend_the_inventory_before_the_staged_check(tmp_path):
    """merge §4 records each [R]emove and [E]dit in a plan, the hash helper amends the inventory, and every later
    check verifies what the user approved (W3 architecture-1 and enhancement-1, with the verifier's corrections)."""
    merge = _read(MERGE)
    assert "- Never delete or modify [MANUAL] section content without the user's section 4 [R]/[E] decision" in merge
    rules = _read(REFS / "manual-section-rules.md")
    assert "without the user's merge §4 [R]emove or [E]dit decision" in rules
    four = _slice(merge, "### 4. Check for Conflicts", "### 6. Compile Merge Results")
    for token in ('{"name": "<block>", "action": "remove"}', '"content_file": "manual-edit-<block>.md"',
                  "Never type a hash", "Rebind `{manual_inventory}` ← `{run_dir}/manual-inventory.json`",
                  "every mode, a clean merge included"):
        assert token in four, token
    # the rebind runs in a step both modes run, before §6b's staged checks
    assert merge.index("Rebind `{manual_inventory}` ← `{run_dir}/manual-inventory.json`") < \
        merge.index("### 6b. Write Merged Files to Disk")
    amend = _fence(four, "uv run {hashContentHelper} manual-inventory-amend")
    staged = _fence(_slice(merge, "**Write and verify the merged SKILL.md in the staged package**", "5. **Publish"),
                    "manual-verify")
    assert "a gap-driven" not in staged
    hashes = _module(HASH_CONTENT, "skf_hash_content_amend_prose")
    package = tmp_path / "pkg"
    package.mkdir()
    original = b"# lib\n\n## Notes\n\n<!-- [MANUAL:keep] -->\nA\n<!-- [/MANUAL:keep] -->\n" \
               b"<!-- [MANUAL:drop] -->\nB\n<!-- [/MANUAL:drop] -->\n<!-- [MANUAL:edit] -->\nC\n<!-- [/MANUAL:edit] -->\n"
    (package / "SKILL.md").write_bytes(original)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    inventory = run_dir / "step1.json"
    inventory.write_bytes(json.dumps(hashes.manual_inventory(package / "SKILL.md")).encode("utf-8"))
    (run_dir / "manual-edit-edit.md").write_bytes(b"\nC, as approved\n")
    (run_dir / "manual-plan.json").write_bytes(json.dumps({"decisions": [
        {"name": "drop", "action": "remove"},
        {"name": "edit", "action": "edit", "content_file": "manual-edit-edit.md"}]}).encode("utf-8"))
    assert hashes.main(_cmd_args(amend, "hashContentHelper", {"manual_inventory": str(inventory),
                                                              "run_dir": str(run_dir)})) == 0
    staging = tmp_path / "1.0.1.skf-tmp"
    (staging / "lib").mkdir(parents=True)
    (staging / "lib" / "SKILL.md").write_bytes(
        b"# lib\n\n## Notes\n\n<!-- [MANUAL:keep] -->\nA\n<!-- [/MANUAL:keep] -->\n"
        b"<!-- [MANUAL:edit] -->\nC, as approved\n<!-- [/MANUAL:edit] -->\n")
    values = {"version_staging": str(staging), "skill_name": "lib",
              "manual_inventory": str(run_dir / "manual-inventory.json")}
    proc = subprocess.run([sys.executable, str(HASH_CONTENT), *_cmd_args(staged, "hashContentHelper", values)],
                          capture_output=True, encoding="utf-8")
    assert json.loads(proc.stdout)["ok"] is True
    # the step-1 inventory would have halted the approved merge
    proc = subprocess.run([sys.executable, str(HASH_CONTENT), *_cmd_args(staged, "hashContentHelper", {
        **values, "manual_inventory": str(inventory)})], capture_output=True, encoding="utf-8")
    assert json.loads(proc.stdout)["ok"] is False
    assert "amended" in _slice(_read(WRITE), "### 1. Verify SKILL.md Write", "```")
    # write §7 re-checks the blocks after skill-check's edits, against the same amended inventory
    recheck = _fence(_slice(_read(WRITE), "**Re-check the [MANUAL] blocks**", "**If skill-check is unavailable:**"),
                     "manual-verify")
    assert '--inventory "{manual_inventory}"' in recheck


def test_the_run_state_calls_quote_every_path():
    """Every path the calls this change adds pass sits in double quotes, as the earlier calls' do."""
    detect, merge, write, init, report = (_read(p) for p in (DETECT, MERGE, WRITE, INIT, REPORT))
    calls = [
        (_fence(detect, "uv run {compareDocHashesHelper} compare-hashes"), "compareDocHashesHelper"),
        (_fence(detect, "uv run {buildChangeManifestHelper} rename-candidates"), "buildChangeManifestHelper"),
        (_fence(detect, "uv run {provenanceGapDispatchHelper} dispatch"), "provenanceGapDispatchHelper"),
        (_apply_call(), "buildChangeManifestHelper"),
        (_fence(merge, "uv run {hashContentHelper} manual-inventory-amend"), "hashContentHelper"),
        (_fence(merge, 'manual-verify "{version_staging}/{skill_name}/SKILL.md"'), "hashContentHelper"),
        (_fence(merge, 'manual-verify "{run_dir}/SKILL.md"'), "hashContentHelper"),
        (_fence(merge, "--mode in-place"), "runStateHelper"),
        (_fence(merge, "--mode new-version"), "runStateHelper"),
        (_fence(init, "uv run {runStateHelper} rollback"), "runStateHelper"),
        (_fence(detect, "uv run {buildChangeManifestHelper} build --doc-hashes"), "buildChangeManifestHelper"),
        (_fence(write, "uv run {compareDocHashesHelper} refresh-hashes"), "compareDocHashesHelper"),
        (_fence(report, "uv run {emitEnvelopeHelper} emit --workflow"), "emitEnvelopeHelper"),
        (re.search(r"`(uv run \{skillInventoryHelper\} version next-patch [^`]*)`", report).group(1),
         "skillInventoryHelper"),
    ]
    for path in STEP_FILES:
        calls.append((_fence(_halt_procedure(path), HALT_CALL).split("<<'SKF_JSON'")[0], "runStateHelper"))
    for call, helper in calls:
        body = call.split("SKF_JSON\n", 2)[-1] if "<<'SKF_JSON'" in call and "cat >" in call else call
        assert _unquoted_placeholders(body, helper) == [], call


# --------------------------------------------------------------------------
# The leaner stage chain: no validate stage, the contract lifted (#599, #600)
# --------------------------------------------------------------------------

STAGES = ("init.md", "detect-changes.md", "re-extract.md", "merge.md", "write.md", "report.md", "health-check.md")


def _update_markdown() -> dict[str, str]:
    return {path.relative_to(UPDATE).as_posix(): _read(path) for path in sorted(UPDATE.rglob("*.md"))}


def test_the_stage_chain_has_no_validate_stage():
    """merge chains straight to write; every Stages row, step heading and nextStepFile agree (#599)."""
    assert not (REFS / "validate.md").exists()
    rows = re.findall(r"^\| (\d) \| ([^|]+) \| references/([\w-]+\.md) \| ([^|]+) \|$",
                      _slice(_read(SKILL), "## Stages", "## Invocation Contract"), re.M)
    assert [(int(n), f) for n, _, f, _ in rows] == list(enumerate(STAGES, 1))
    assert "Write" in rows[4][1] and "Report" in rows[5][1]
    for number, name in enumerate(STAGES, 1):
        text = _read(REFS / name)
        assert re.search(rf"^# Step {number}: ", text, re.M), name
        following = STAGES[number] if number < len(STAGES) else None
        if following:
            assert yaml.safe_load(_frontmatter(text))["nextStepFile"] == following, name
    for rel, text in _update_markdown().items():
        for gone in ("validate.md", "step 05", "Step 05", "step 8", "Step 8", "steps 03-06", "merge+validate",
                     "merge/validate/write", "re-extract, merge, validate"):
            assert gone not in text, (rel, gone)


def test_skill_check_runs_once_in_write():
    """One skill-check check call per update, in write.md §7, guarded and followed by the [MANUAL] re-check (#599)."""
    calls = [(rel, line) for rel, text in _update_markdown().items() for line in text.splitlines()
             if "skill-check check " in line and "npx" in line]
    assert [rel for rel, _ in calls] == ["references/write.md"], calls
    seven = _slice(_read(WRITE), "### 7. Run Post-Write Validation", "### 8.")
    assert "skill-check runs once per update, here" in seven
    assert "`npx skill-check check \"{skill_package}\" --fix --format json` **inside the §0 guard**" in seven
    assert "--no-security-scan` is passed" in seven and "--no-security-scan --" not in seven
    assert "`npx skill-check -h`" in seven
    assert 'npx skill-check diff "{skill_group}/{baseline_version}/{skill_name}" "{skill_package}"' in seven
    marks = [seven.index("**Description Guard Protocol:**"), seven.index("--fix --format json"),
             seven.index("**Re-check the [MANUAL] blocks**"), seven.index("**If skill-check is unavailable:**")]
    assert marks == sorted(marks)
    # every path §7 hands a tool is quoted, so a project path with a space reaches it whole
    for call in re.findall(r"(?:npx skill-check|uv run \{\w+\}) [^`\n]*", seven):
        assert "{skill_package}" not in call.replace('"{skill_package}', ""), call
    # the structural check skill-check would have run goes to the output validator, never by eye (determinism-10)
    unavailable = _slice(seven, "**If skill-check is unavailable:**", "\n")
    assert 'uv run {validateOutputHelper} "{skill_package}"' in unavailable
    # the row says what ran: PASS or WARN from the validator, SKIP only when none resolves
    for token in ("`Spec compliance: PASS (skf-validate-output.py)` when it reports no issue",
                  "`Spec compliance: WARN (skf-validate-output.py)` with each issue it reports otherwise",
                  "when no candidate resolves, record `Spec compliance: SKIP (skill-check unavailable, no validator)`"):
        assert token in unavailable, token
    assert "record `Spec compliance: SKIP (skill-check unavailable)`" not in unavailable
    assert yaml.safe_load(_frontmatter(_read(WRITE)))["validateOutputProbeOrder"] == _probe("skf-validate-output.py")
    assert "structural checks from step 5 are sufficient" not in seven and "Deferred from" not in _read(WRITE)


def test_write_rechecks_the_manual_blocks_after_skill_check():
    """§7's --fix and body split can edit SKILL.md after §1's gate, so §7 re-runs manual-verify and halts as §1 does,
    and never moves a section that holds a [MANUAL] block (BMad Builder re-check architecture-4)."""
    write = _read(WRITE)
    seven = _slice(write, "### 7. Run Post-Write Validation", "### 8.")
    one = _slice(write, "### 1. Verify SKILL.md Write", "### 2.")
    recheck = _slice(seven, "**Re-check the [MANUAL] blocks**", "**If skill-check is unavailable:**")
    assert _fence(recheck, "manual-verify").split() == _fence(one, "manual-verify").split()
    for token in ("HALT with status `halted-for-manual-mismatch`, as §1 does",
                  '`phase: "write:verify-manual-integrity"`', '`path: "{skill_package}/SKILL.md"`',
                  "[MANUAL] blocks changed after skill-check"):
        assert token in recheck, token
    split = _slice(seven, "If `body.max_lines` is reported", "\n")
    assert "**Never move a section that holds a `[MANUAL]` block:**" in split
    assert "only when SKILL.md holds no `[MANUAL]` block" in split
    rules = _slice(write, "## Rules", "## Steps")
    assert "§7's `skill-check check --fix` edits and body split, which moves no section that holds a `[MANUAL]` " \
           "block; §7 re-checks the [MANUAL] blocks after them" in rules
    # the rollback window closes after the last check that can halt, so a §7 halt still undoes a repair
    assert "uv run {runStateHelper} finish" not in _slice(write, "### 6. Provenance Completeness", "### 10.")
    assert "Until §10 closes the window" in _halt_procedure(WRITE)
    assert "write.md §10 already dropped the snapshot" in _read(HEALTH)
    assert "Update-skill does not run the optional post-restore" not in write


def test_write_makes_the_version_live_after_the_last_check():
    """§6 and §7 can halt, so §8 points the active link at the new version only after them, §9 moves the clone and
    §10 closes the rollback window: a [MANUAL] halt in §6 or §7 rolls back a version no reader sees yet, as §1's
    does (BMad Builder review: §7's halt ran after the flip and kept a live version with changed blocks)."""
    write = _read(WRITE)
    titles = re.findall(r"^### (\d+[a-z]?)\. (.+)$", write, re.M)
    assert titles[6:] == [("6", "Provenance Completeness"), ("7", "Run Post-Write Validation"),
                          ("8", "Update the Active Symlink"), ("8a", "Verify the Active Symlink"),
                          ("9", "Move the Workspace Clone to the Recorded Commit"),
                          ("10", "Close the Rollback Window"), ("11", "Route to Next Step")]
    assert "`{manual_recovery}` depends on the mode:" in _slice(write, "### 1. Verify SKILL.md Write", "### 2.")
    for start, end in (("### 6. Provenance Completeness", "### 7."), ("### 7. Run Post-Write Validation", "### 8.")):
        section = _slice(write, start, end)
        assert ('{manual_recovery}", with `{manual_recovery}` as §1 gives it: §8 has not pointed the `active` link '
                "at a new version yet, so this halt rolls back as §1's does.") in section, start
        assert "kept it" not in section and "restore the listed blocks" not in section, start
    procedure = _halt_procedure(WRITE)
    assert "Until §10 closes the window" in procedure
    assert "unless the `active` link already names them (§8), which keeps that version" in procedure
    eight = _slice(write, "### 8. Update the Active Symlink", "### 8a.")
    assert "now that §6 and §7 have checked the written package" in eight
    assert eight.count("Continue to §8a.") == 2
    rules = _slice(write, "## Rules", "## Steps")
    assert ("§8 points the `active` link at the new version only after §6 and §7, the last checks that can halt, so "
            "every halt in this step rolls back a version no reader sees yet") in rules
    assert "\u2014" not in _slice(rules, "- HALT immediately on verification failure", "\n")
    # one finish, in §10, once the clone moved; nothing after it halts
    assert write.count("uv run {runStateHelper} finish") == 1
    assert write.index("### 9. ") < write.index("uv run {runStateHelper} finish") < write.index("### 11. ")
    assert "never halts" in _write_9() and "HALT" not in _slice(write, "### 10. ", "### 11.")
    # the schema tells a pipeline the same order
    status = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["status"]["description"]
    assert "unless write.md §5b already made the new version the active one" not in status


# gap-driven.md stands in for steps 2 and 3 in gap-driven mode and has no Stages row yet (#600)
BRANCH_STAGES = ("gap-driven.md",)
# A step or stage file named before §: "step 5 §8", "Step 3 §0.a", "write.md §6". Another skill's step
# ("create-skill step 6 §8") is skipped.
_CITE = re.compile(r"(?<![\w-])(?:[Ss]tep (\d)|(" + "|".join(re.escape(s) for s in STAGES + BRANCH_STAGES) +
                   r"))(?:'s)? §(\d+[a-z]?(?:\.\d+|\.[a-z])?)")


def _anchors(name: str) -> set[str]:
    """The section labels a stage file defines: its numbered headings and its bold `**0.a ...**` labels."""
    text = _read(REFS / name)
    return (set(re.findall(r"^#{3,4} (\d+[a-z]?(?:\.\d+)?)[. ]", text, re.M))
            | set(re.findall(r"^\*\*(\d+\.[a-z]) ", text, re.M)))


def test_every_cited_step_section_exists():
    """Every "step N §X" and "<stage>.md §X" an update-skill file cites names a section that stage defines under
    the Stages table's numbering, spelled one way: no "Step-06", "step 05" or "step-1" (BMad Builder review: a
    stale "Step-06 §3" sent the model to report.md for a write.md rule)."""
    anchors = {name: _anchors(name) for name in STAGES + BRANCH_STAGES}
    cited = 0
    for rel, text in _update_markdown().items():
        assert not re.search(r"[Ss]teps?[- ]0\d|[Ss]tep-\d", text), rel
        for match in _CITE.finditer(text):
            if re.search(r"[a-z]+-skill'?s? $", text[max(0, match.start() - 20):match.start()]):
                continue
            target = STAGES[int(match.group(1)) - 1] if match.group(1) else match.group(2)
            assert match.group(3) in anchors[target], (rel, match.group(0))
            cited += 1
    assert cited > 100, cited
    # the unknown NEW_EXPORT bullet names the provenance write it means
    assert "write.md §3 (step 5) accepts null `source_file` / `source_line` only for these" in _read(GAP)
    # the sections the carve renumbered: no stage file cites gap-driven mode's old homes (#600 architecture-4)
    for rel, text in _update_markdown().items():
        for gone in ("§0.a", "§0a", "step 3 §0", "step 2 §0", "detect-changes §0", "re-extract §0",
                     "re-extract.md §0", "detect-changes.md §0", "step 3 should have", "step 3's spot-check"):
            assert gone not in text.lower(), (rel, gone)

def test_the_report_reads_the_validation_write_recorded():
    """report §3 renders the Validation Summary write.md recorded: [MANUAL] integrity from §1, Provenance from §6,
    Spec compliance, Diff and Security from §7 (wave-1 re-check leanness-1)."""
    write = _read(WRITE)
    summary = _slice(write, "### Validation Summary", "### Description Guard")
    for row in ("Spec compliance:", "[MANUAL] integrity:", "Confidence tiers:", "Provenance:", "Diff:", "Security:"):
        assert row in summary, row
    population = _slice(write, "**Validation Summary population:**", "\n")
    for token in ("from §1's `manual-verify` verdict", "§6 fills `Provenance`",
                  "§7 fills `Spec compliance`, `Diff` and `Security`"):
        assert token in population, token
    three = _slice(_read(REPORT), "### 3. Present Validation Findings", "### 4.")
    for token in ("write.md §1's `manual-verify` verdict", "`Provenance` from §6",
                  "`Spec compliance`, `Diff` and `Security` from §7", "| Diff |", "| Security |"):
        assert token in three, token
    assert "step 05" not in three
    assert "the Validation Summary §3 read for `validation_status`" in _slice(_read(REPORT), "### 5b.", "### 6.")
    # the derived-artifact read-back is gone: one write-error halt beside the halt procedure, and the symlink
    # check (leanness-3)
    six = _slice(write, "### 8a. Verify the Active Symlink", "### 9.")
    assert "Read back the file" not in write and "| File | Status |" not in write
    errors = _slice(write, "The halt leaves `{run_dir}` in place.", "### 0.")
    assert "A `Write` or `Edit` call in §2 to §5 that errors" in errors and '`phase: "write:artifact-write"`' in errors
    assert _fence(six, "uv run {updateActiveSymlinkHelper} verify").split() == [
        "uv", "run", "{updateActiveSymlinkHelper}", "verify", "\\", "--skill-group", "{skill_group}", "\\",
        "--version", "{version}"]


def test_the_evidence_records_live_in_the_run_folder():
    """The scope and targeted re-extraction records write §4 renders sit in the run folder, not in context, so a
    compacted context still reports a decision the run made (Workflow Rules: the run log)."""
    sink = "`{run_dir}/evidence-records.jsonl`"
    detect = _read(DETECT)
    for key, section, end in (("authoritative_files_mirror", "### 1b.", "### 1c."),
                              ("scope_reconciliation_pre", "### 1c.", "### 2."),
                              ("scope_reconciliation_post", "#### 2.2", "### 3.")):
        body = _slice(detect, section, end)
        assert f"to {sink} as one JSON line keyed `{key}`" in body, key
    assert f"to {sink} the same way, and proceed to §3" in _slice(detect, "- **[C] Continue:**", "\n")
    zero_a = _slice(_read(GAP), "### 4a. Targeted Re-Extraction Branch", "### 5.")
    assert f"to {sink} as one JSON line keyed `targeted_reextraction`" in zero_a
    assert "in workflow context" not in _slice(zero_a, "6. **Success summary:**", "\n")
    population = _slice(_read(WRITE), "**Scope and Targeted Re-Extraction population:**", "\n")
    assert f"read {sink}" in population and "`none` for a key no line holds" in population
    assert "kept for the evidence report" not in population

def test_the_invocation_contract_is_lifted_from_skill_md():
    """SKILL.md points at references/invocation-contract.md, which holds the six rows; the Gates row lists the
    gates the stages raise and the Stages table marks steps 2 and 4 Conditional (#600, architecture-5)."""
    skill = _read(SKILL)
    pointer = _slice(skill, "## Invocation Contract", "## On Activation")
    assert "`references/invocation-contract.md`" in pointer and "| **" not in pointer
    # cl100k_base reads about four characters a token in this prose: 10,000 keeps SKILL.md under 2,500 tokens
    assert len(skill) < 10_000, len(skill)
    contract = _read(CONTRACT)
    rows = re.findall(r"^\| \*\*(\w+)\*\* \|", contract, re.M)
    assert rows == ["Inputs", "Flags", "Gates", "Outputs", "Concurrency", "Headless"]
    gates = _slice(contract, "| **Gates** |", "\n")
    for token in ("init.md §4's degraded-rebuild gate [D]/[X]", "Confirm Gate [C] (init.md §8)",
                  "detect-changes.md §1b's promote prompt and §1c's scope-expansion prompt [P]/[S]/[U]",
                  "§2.2's deletion-ratio gate [C]/[B]/[A]",
                  "step 4: Confirm Gate [C] only after the user resolved [MANUAL] conflicts",
                  "a headless run with conflicts halts `halted-for-manual-mismatch`"):
        assert token in gates, token
    assert "[C if clean merge" not in contract
    assert "at step 6 or at a HALT" in _slice(contract, "| **Headless** |", "\n")
    stages = _slice(skill, "## Stages", "## Invocation Contract")
    assert "| 2 | Detect Changes | references/detect-changes.md | Conditional" in stages
    assert "| 4 | Merge | references/merge.md | Conditional" in stages


def test_merge_routes_to_write_with_one_progress_line():
    """merge §7 shows one line, not a table report.md repeats; §8 routes to write (#599 leanness-9)."""
    merge = _read(MERGE)
    seven = _slice(merge, "### 7. Report Progress", "### 8.")
    assert "| Metric | Count |" not in seven and "The report (step 6) shows the full counts" in seven
    eight = _slice(merge, "### 8. Route to Write", "```bash")
    assert "[C] Continue to Write" in eight and "Validation" not in eight
    assert "Edit/Write tools commit on call" not in merge
    for path, heading, end in ((DETECT, "### 5. Display Change Summary and Route", "This step auto-proceeds"),
                               (RE_EXTRACT, "### 5. Display Extraction Summary and Auto-Proceed", "### 6.")):
        section = _slice(_read(path), heading, end)
        assert "| Count |" not in section and "Display one line" in section, path.name
    # gap-driven.md §2 lists the gaps §1 did not route; detect-changes, which a repair never loads, keeps no copy
    assert "list each gap §1 did not route" in _slice(_read(GAP), "### 2.", "### 3.")
    assert "gap" not in _slice(_read(DETECT), "### 5. Display Change Summary and Route", "- **`detect_only_mode")
    assert "below the table" not in _read(DETECT)
    one_a = _slice(_read(REPORT), "### 1a. Handle Detect-Only Mode", "### 1b.")
    assert "§2's Changes Applied table" in one_a and "summary table from detect-changes.md" not in one_a
    assert "(routed here from detect-changes.md §5 or gap-driven.md §2)" in one_a


def test_persistent_facts_default_can_be_dropped():
    """customize.toml keeps the project-context.md default and says how to drop it; SKILL.md applies the `!`
    entry; the header names the override files from {project-root} (#596 update part)."""
    import tomllib

    toml_text = _read(UPDATE / "customize.toml")
    data = tomllib.loads(toml_text)["workflow"]
    assert data["persistent_facts"] == ["file:{project-root}/**/project-context.md"]
    assert "# Team overrides:     {project-root}/_bmad/custom/skf-update-skill.toml" in toml_text
    assert "# Personal overrides: {project-root}/_bmad/custom/skf-update-skill.user.toml" in toml_text
    assert '#   persistent_facts = ["!file:{project-root}/**/project-context.md"]' in toml_text
    assert "(uv probe, config load)" not in toml_text
    activation = _slice(_read(SKILL), "4. **Resolve workflow customization.**", "5. Load")
    assert ("an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's "
            '`"!file:{project-root}/**/project-context.md"` turns that default off') in activation


def test_the_rule_files_hold_no_copy_of_merge():
    """manual-section-rules.md keeps the marker rules merge.md does not state; init.md no longer loads it
    (#600 leanness-8); merge-conflict-rules.md is gone, since its rows only repeated merge.md's Rules and §4
    (architecture-8)."""
    rules = _read(REFS / "manual-section-rules.md")
    assert "### Conflict Types" not in rules and "### Preservation Algorithm" not in rules
    # one bold-term style for the four rules
    assert re.findall(r"^\d\. \*\*([^*]+)\*\*: ", rules, re.M) == [
        "Never delete or modify content between [MANUAL] markers without the user's merge §4 [R]emove or [E]dit "
        "decision", "Preserve marker positions", "Multiple [MANUAL] blocks", "Nested [MANUAL] forbidden"]
    assert not (REFS / "merge-conflict-rules.md").exists()
    merge = _read(MERGE)
    assert "mergeConflictRulesFile" not in merge and "merge-conflict-rules" not in merge
    assert "the [MANUAL] rules file merge.md loads" in _read(SKILL)
    init = _read(INIT)
    assert "manualSectionRulesFile" not in init and "manualSectionRulesFile" in merge

