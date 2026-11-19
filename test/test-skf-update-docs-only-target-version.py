#!/usr/bin/env python3
"""A docs-only update can take the version of the release its documents describe (#1248).

A docs-only skill has no source tree, so load-baseline.md §6c once never ran for
it and merge-write.md §6b always wrote the next patch version. These tests pin
the prose that gives such an update a version: init.md §1 checks a
`--target-version` value with Brief Skill's own check before the run lock and
ignores it in gap-driven mode; load-baseline.md §6 refuses the flag for a skill
built from source (`target-version-needs-docs-only`); §6c takes the flag, else
the skill brief's `target_version`, else its `version`, and orders it against
the skill's version through its one `version order` call, whose result binds
`{source_version_detected}`. The invocation contract, merge-write.md,
knowledge/version-paths.md and the user docs say the same. When every hashed
document matches, the run still ends `no-changes` and writes nothing: report.md
§1 says the named version was not recorded and warns
`target-version-not-recorded`, which the envelope schema lists.

The run tests execute the calls the prose spells out (each fence split first,
then filled) against the real helpers.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
REFS = SRC / "skf-update-skill" / "references"
INIT = REFS / "init.md"
LOAD_BASELINE = REFS / "load-baseline.md"
MERGE_WRITE = REFS / "merge-write.md"
CONTRACT = REFS / "invocation-contract.md"
REPORT = REFS / "report.md"
SCRIPTS = SRC / "shared" / "scripts"
SCHEMA = SCRIPTS / "schemas" / "skf-update-result-envelope.v1.json"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
VALIDATOR = SCRIPTS / "skf-validate-brief-inputs.py"
DOCS = REPO_ROOT / "docs"
VALIDATOR_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-inputs.py",
    "{project-root}/src/shared/scripts/skf-validate-brief-inputs.py",
]
ORDER_CALL = "uv run {skillInventoryHelper} version order"
CHECK_CALL = "uv run {validateBriefInputsHelper} --only target_version <<'SKF_JSON'"


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


def _fence(text: str, start: str) -> str:
    """The fenced block that holds `start`."""
    i = text.index(start)
    open_ = text.rindex("```", 0, i)
    body = text.index("\n", open_) + 1
    block = text[body:text.index("```", body)]
    assert start in block, f"{start!r} is not inside a fenced block"
    return block


def _six_c() -> str:
    return _slice(_read(LOAD_BASELINE), "### 6c. Detect the Source Version", "### 7.")


def _docs_only_paragraph() -> str:
    return _slice(_six_c(), "**A docs-only skill** has no version file", "\n")


def _target_version_paragraph() -> str:
    return _slice(_read(INIT), "**If `--target-version` was provided:**", "**If `--source-root` was provided:**")


# --------------------------------------------------------------------------
# load-baseline.md §4b, §6 and §6c
# --------------------------------------------------------------------------


def test_baseline_takes_a_docs_only_version_from_the_flag_or_the_brief():
    baseline = _read(LOAD_BASELINE)
    six = _slice(baseline, "### 6. Resolve the Source", "### 6b.")
    docs_only = _slice(six, "- **Docs-only skill**", "\n")
    assert "Skip §6b, §6c" not in docs_only
    assert "§6c reads the version this update writes from `--target-version` or the skill brief" in docs_only
    other = _slice(six, "- **Every other mode**", "\n")
    assert "target-version-needs-docs-only" in other and "run §6b" in other
    assert other.index("target-version-needs-docs-only") < other.index("run §6b")
    # the refusal of a skill built from source is §6b's halt: `blocked` at `init:source-tree`, before change detection
    assert ("HALT as §6b's **Every §6b HALT** describes, with `{source_tree_reason}` = "
            "`target-version-needs-docs-only` and `{source_tree_message}` = "
            "\"`--target-version` applies only to a docs-only skill\"") in other
    every_halt = _slice(baseline, "**Every §6b HALT** runs the halt procedure", "\n")
    assert 'status: "blocked"' in every_halt and 'phase: "init:source-tree"' in every_halt
    four_b = _slice(baseline, "### 4b.", "### 5.")
    assert "give init.md §1's `--target-version` warning and unset it" in four_b
    six_c = _six_c()
    assert "or for a docs-only skill outside gap-driven mode (§6)" in six_c
    # a docs-only run goes straight to its paragraph, before the version-file read and its "skip the rest"
    opening = _slice(six_c, "Run only when `{source_tree_status}` is `ready` or `offline`", "\n")
    order = [opening.index(token) for token in (
        "A docs-only skill reads no source and no version file: go straight to **A docs-only skill** below",
        "For any other skill, read the source's version from `{source_root}`",
        "When no version file gives one, leave `{source_version_detected}` unset and skip the rest of this section")]
    assert order == sorted(order)
    paragraph = _docs_only_paragraph()
    for token in ("Take that version from `{target_version_override}` when init.md §1 set it, else from the "
                  "skill brief `{forge_data_folder}/{skill_name}/skill-brief.yaml`",
                  "its `target_version`, else its `version`",
                  "With no `{target_version_override}` and no brief, or a brief that sets neither field, leave "
                  "`{source_version_detected}` unset and skip the rest of this section",
                  "source-version-lower: --target-version {a.normalized} is older than {version}; this update "
                  "keeps the patch-version rule",
                  "a version read from the brief adds no warning"):
        assert token in paragraph, token
    # a skill built from source never reads the brief for its version: only the docs-only paragraph names it
    assert six_c.count("skill-brief.yaml") == paragraph.count("skill-brief.yaml") == 1
    # one comparison, the one the source's version already takes: never a second call or a comparison by hand
    assert six_c.count(ORDER_CALL) == 1


@pytest.mark.parametrize("target, version, order, major_minor", [
    pytest.param("2.4.0", "1.0.3", "higher", None, id="higher-release"),
    pytest.param("1.0.0", "1.0.3", "lower", "equal", id="brief-at-the-build-version"),
    pytest.param("2.4.0", "2.4.1", "lower", "equal", id="flag-at-the-build-version"),
    pytest.param("1.9.0", "2.0.1", "lower", "lower", id="flag-on-an-older-line"),
    # the brief still at the build version once an update patched the skill: no named version, so no notice
    pytest.param("1.0.0", "1.0.4", "lower", "equal", id="brief-below-a-patched-skill"),
])
def test_the_documented_order_call_picks_the_docs_only_version(target, version, order, major_minor):
    """The docs-only paragraph runs §6c's own `version order` fence: a higher version binds
    `{source_version_detected}` ← `a.normalized`, and only a lower major or minor warns."""
    assert "run the `version order` call above with that version as `{the source's version}`" in \
        _docs_only_paragraph()
    call = _fence(_six_c(), ORDER_CALL)
    rest = call.split("uv run {skillInventoryHelper}", 1)[1].replace("\\\n", " ")
    argv = []
    # split first, fill after: a filled value never meets shlex
    for arg in shlex.split(rest):
        arg = arg.replace("{the source's version}", target).replace("{version}", version)
        assert "{" not in arg, arg
        argv.append(arg)
    proc = subprocess.run([sys.executable, str(INVENTORY), *argv], capture_output=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["order"] == order, out
    if order == "higher":
        assert out["a"]["normalized"] == target
    else:
        assert out["major_minor"] == major_minor, out


# --------------------------------------------------------------------------
# init.md §1
# --------------------------------------------------------------------------


def test_init_checks_the_target_version_before_the_lock():
    init = _read(INIT)
    frontmatter = init[4:init.index("\n---\n", 4) + 1]
    assert yaml.safe_load(frontmatter)["validateBriefInputsProbeOrder"] == VALIDATOR_PATHS
    marks = ["**If `--target-ref` was provided:**", "**If `--target-version` was provided:**",
             "**If `--source-root` was provided:**"]
    assert [init.index(m) for m in marks] == sorted(init.index(m) for m in marks)
    paragraph = _target_version_paragraph()
    for token in (CHECK_CALL, "set `{target_version_override}` to the value", 'status: "blocked"',
                  'phase: "init:target-version"', 'reason: "input-invalid: --target-version: ',
                  "(\"`--target-version` has no effect with `--from-test-report`: a gap-driven repair keeps the "
                  "version it repairs\") and leave `{target_version_override}` unset",
                  "This runs before the §1b lock"):
        assert token in paragraph, token
    lines = _fence(paragraph, CHECK_CALL).splitlines()
    assert lines[0] == CHECK_CALL and lines[-1] == "SKF_JSON"
    argv = shlex.split(lines[0].split("uv run {validateBriefInputsHelper}", 1)[1].split("<<", 1)[0])
    payload = "\n".join(lines[1:-1]) + "\n"
    assert '"<the value>"' in payload

    def check(value: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(VALIDATOR), *argv],
                              input=payload.replace('"<the value>"', json.dumps(value)),
                              capture_output=True, encoding="utf-8")

    proc = check("2.4.0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["valid"] is True
    proc = check("2.4")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["valid"] is False
    assert out["errors"][0]["message"].startswith("target_version '2.4' is a major and minor version only")
    proc = check("^2.4.0")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["valid"] is False


# --------------------------------------------------------------------------
# contract, merge-write.md and knowledge
# --------------------------------------------------------------------------


def test_contract_merge_and_knowledge_name_the_docs_only_version():
    flags_row = _slice(_read(CONTRACT), "| **Flags** |", "\n")
    assert "`--target-version <version>` (a docs-only skill, outside gap-driven mode" in flags_row
    choose = _slice(_read(MERGE_WRITE), "**Choose the version this update writes**", "**Create the version folder**")
    assert "for a docs-only skill the one `--target-version` or its skill brief names" in choose
    # a gap-driven repair keeps its version whatever the flag said
    assert "a repair keeps the version it repairs: `{new_version}` is the metadata.json `version`" in choose
    # --dry-run never reaches merge-write.md §6b: its report names the folder from the same §6c value
    dry = _slice(_read(REPORT), "### 1b. Handle Dry-Run Mode", "### 2.")
    assert "`{dry_run_version}` names the folder the run would create" in dry
    assert "`{source_version_detected}` when load-baseline.md §6c recorded one" in dry
    us = _slice(_read(SRC / "knowledge" / "version-paths.md"),
                "**Update-skill (US)** writes each new version into a folder of its own", "\n")
    assert "the skill brief's `target_version`" in us


# --------------------------------------------------------------------------
# user docs
# --------------------------------------------------------------------------


def test_user_docs_name_the_flag():
    workflows = _slice(_read(DOCS / "workflows.md"), "### Update Skill (US)", "**Agent:**")
    assert "`--target-version <version>`" in workflows
    assert "`target-version-needs-docs-only`" in workflows
    assert "`@Ferris US <name> --target-version <version>`" in _read(DOCS / "concepts.md")
    trouble = _read(DOCS / "troubleshooting.md")
    blocked = _slice(trouble, "### Update Skill stops with `blocked` before detecting changes", "\n### ")
    assert "- `target-version-needs-docs-only`:" in blocked
    assert "or when `--target-version` is passed for a skill that is not docs-only" in blocked
    exists = _slice(trouble, "### Update Skill stops with `halted-for-write-failure` because the version already "
                             "exists", "\n### ")
    assert "`--target-version`" in exists


# --------------------------------------------------------------------------
# report.md §1 and the envelope schema: a named version no document change carries
# --------------------------------------------------------------------------


def test_no_change_run_reports_the_unrecorded_version():
    """A docs-only run that names a higher version but whose documents all match ends `no-changes` and writes
    nothing (detect-changes.md §4); report.md §1 says the version was not recorded and warns, as it does for
    `--target-ref`, in every mode that reaches it, `--detect-only` and `--dry-run` included."""
    one = _slice(_read(REPORT), "### 1. Handle No-Change Shortcut", "### 1a.")
    notice = _slice(one, "When `{source_moved}` is true, add before the recommendation:", "\n")
    # a paragraph of its own: `{source_moved}`, which gates the paragraph before it, is never true for a
    # docs-only skill
    added = _slice(one, "For a docs-only skill, when `{source_version_detected}` is set", "\n")
    assert "For a docs-only skill" not in notice
    # the notice and the warning hang on `{source_version_detected}` alone: a brief at or below the skill's
    # version leaves it unset (§6c's Otherwise bullet), so that no-change run gets neither
    assert added.count("`{source_version_detected}` is set") == 1
    assert "- **Otherwise** leave `{source_version_detected}` unset." in _six_c()
    for token in ("**The move to `{source_version_detected}` was not recorded**",
                  # a document that could not be fetched or has no hash is not compared (detect-changes.md §1)
                  "an update writes a new version only when a document it tracks changed, and none that it could "
                  "check did",
                  "add `target-version-not-recorded: no document {skill_name} tracks changed, so "
                  "{source_version_detected} was not written; the skill stays at {version}` to `warnings[]`",
                  "with `{version}` the metadata.json `version`",
                  "load-baseline.md §6c bound it to the version `--target-version` or the skill brief named"):
        assert token in added, token
    # filled as a run at 1.0.4 that named 2.4.0 fills it, the entry reads as the matrix gives it
    entry = added.split("add `", 1)[1].split("` to `warnings[]`", 1)[0]
    assert entry.replace("{source_version_detected}", "2.4.0").replace("{version}", "1.0.4") == (
        "target-version-not-recorded: no document {skill_name} tracks changed, so 2.4.0 was not written; "
        "the skill stays at 1.0.4")
    # it sits beside the `--target-ref` notice, right after it
    assert "target-ref-not-recorded" in notice
    assert one[one.index(notice) + len(notice):].startswith("\n\n" + added)
    assert "\u2014" not in added  # no em dash
    finished = _slice(one, "**Result files, line and hook.**", "\n")
    assert "(`target-ref-not-recorded` and `target-version-not-recorded` among them)" in finished
    # a read-only run gets the same notice: it holds no mode condition and comes before the read-only paragraph,
    # which prints the line and writes no result file; §6c's value reaches it through run-context.json
    read_only = _slice(one, "**A read-only run stays read-only here.**", "\n")
    assert "detect_only_mode" not in added and "dry_run_mode" not in added
    assert one.index(added) < one.index(read_only)
    assert "write no result file" in read_only
    assert 'print the line as §1a does, with `status: "no-changes"`' in read_only
    baseline = _read(LOAD_BASELINE)
    eight = _slice(baseline, "### 8. Confirmation Gate", "```")
    assert "**Record the run context** first, in every mode (`--detect-only` and `--dry-run` too)" in eight
    assert '"source_version_detected": "{source_version_detected}"' in _fence(baseline, '"source_version_detected"')
    warnings = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["warnings"]["description"]
    assert ("target-ref-not-recorded, target-version-not-recorded (report.md §1: a docs-only run named a higher "
            "version but no document changed, so nothing was written)") in warnings
    # the no-change route writes no version: detect-changes.md §4 skips steps 3 to 5 in every mode
    four = _slice(_read(REFS / "detect-changes.md"), "### 4. Check for No-Change Shortcut", "### 5.")
    assert "Skip steps 3-5" in four and "A `--detect-only` or `--dry-run` run takes this route too" in four
