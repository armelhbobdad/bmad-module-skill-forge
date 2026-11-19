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

Last, a docs-only update compares a document recorded with a null hash
(#1267): detect-changes.md §1 passes `compare-hashes --fetch-null`, which
audit-skill's doc-drift step does not, HALTs `blocked` when it compared no
document, and a no-change report says how many tracked documents match their
recorded hashes from the counts `build --doc-hashes` writes.

The run tests execute the calls the prose spells out (each fence split first,
then filled) against the real helpers.
"""

from __future__ import annotations

import hashlib
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
DETECT = REFS / "detect-changes.md"
WRITE_META = REFS / "write-metadata.md"
AUDIT_DRIFT = SRC / "skf-audit-skill" / "references" / "doc-drift.md"
SCRIPTS = SRC / "shared" / "scripts"
SCHEMA = SCRIPTS / "schemas" / "skf-update-result-envelope.v1.json"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
VALIDATOR = SCRIPTS / "skf-validate-brief-inputs.py"
DETECT_DOCS = SCRIPTS / "skf-detect-docs.py"
BUILD_MANIFEST = SCRIPTS / "skf-build-change-manifest.py"
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


# --------------------------------------------------------------------------
# #1267: a docs-only update compares a null hash and stops when it compared none
# --------------------------------------------------------------------------

COMPARE_CALL = "uv run {compareDocHashesHelper} compare-hashes"
BUILD_CALL = "uv run {buildChangeManifestHelper} build --doc-hashes"
COUNTS = "{docs_unchanged} of {docs_tracked} tracked documents match their recorded hashes."
COUNTS_NOT_CHECKED = ("{docs_unchanged} of {docs_tracked} tracked documents match their recorded hashes; "
                      "{docs_not_checked} could not be checked (see Warnings).")


def _detect_one() -> str:
    return _slice(_read(DETECT), "### 1. Scan Current Source State", "### 2.")


def _run_call(call: str, helper: str, script: Path, values: dict) -> dict:
    """Run a documented `uv run {helper} ... > "<file>"` line against `script`, split first and filled after, and
    write its stdout to the filled redirect target, as the step does. Returns the JSON it wrote."""
    line = call.strip()
    assert line.count(" > ") == 1, line
    command, target = line.split(" > ", 1)

    def fill(arg: str) -> str:
        for key, value in values.items():
            arg = arg.replace("{" + key + "}", value)
        assert "{" not in arg, arg
        return arg

    argv = [fill(arg) for arg in shlex.split(command.split("uv run {" + helper + "}", 1)[1])]
    (out,) = [fill(arg) for arg in shlex.split(target)]
    proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    Path(out).write_text(proc.stdout, encoding="utf-8")
    return json.loads(proc.stdout)


def _docs_only_skill(tmp_path: Path, name: str, doc_sources: list | None) -> dict:
    """A docs-only skill package and a run folder, `doc_sources` left out when None."""
    package, run_dir = tmp_path / name / "pkg", tmp_path / name / "run"
    package.mkdir(parents=True)
    run_dir.mkdir()
    meta = {"name": "docs", "source_type": "docs-only"}
    if doc_sources is not None:
        meta["doc_sources"] = doc_sources
    (package / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"skill_package": str(package), "run_dir": str(run_dir)}


def _documents(tmp_path: Path) -> dict:
    """The matrix's documents: A and C hashed and matching, B null and readable, D null and unreadable, E hashed
    and unreadable. Returns each one's `doc_sources` entry and URL."""
    docs = tmp_path / "docs"
    docs.mkdir()
    entries = {}
    for name, body, hashed in (("A", b"a one\n", True), ("B", b"b one\n", False), ("C", b"c one\n", True),
                               ("D", None, False), ("E", None, True)):
        path = docs / f"{name.lower()}.md"
        if body is not None:
            path.write_bytes(body)
        content_hash = ("sha256:" + hashlib.sha256(body or b"gone\n").hexdigest()) if hashed else None
        entries[name] = {"url": "file://" + path.as_posix(), "content_hash": content_hash}
    return entries


def test_a_docs_only_update_compares_null_hashes_and_halts_when_it_compared_none(tmp_path):
    one = _detect_one()
    call = _fence(one, COMPARE_CALL)
    assert "--fetch-null" in call
    # audit-skill keeps skipping a null hash: there is no baseline to grade drift against
    assert "--fetch-null" not in _fence(_read(AUDIT_DRIFT), COMPARE_CALL)
    halt = "**When `stats.changed` + `stats.unchanged` is 0**"
    assert halt in one
    # the exit-2 halt and the nothing-compared halt
    assert one.count('phase: "detect-changes:doc-hashes"') == 2
    for token in ("re-run once the documents can be reached", "`metadata.json records no doc_sources`",
                  "joined by `, `", "**No document of `{skill_name}` could be compared.**",
                  "re-create the skill with `[CS] Create Skill` to record their hashes"):
        assert token in one, token
    # with --fetch-null skipped_null_hash is empty, and the halt replaces the no-doc_sources warning
    assert "`doc-not-hashed: {url}`" not in one and "doc-drift-not-checked" not in one
    # the halt comes before the warnings and before the manifest build, in every mode
    assert one.index(halt) < one.index("Otherwise add `doc-fetch-failed: {url} ({reason})`") < one.index(BUILD_CALL)
    assert "detect_only_mode" not in _slice(one, halt, "\n") and "dry_run_mode" not in _slice(one, halt, "\n")
    assert "passes `--fetch-null`" in _read(WRITE_META)
    workflows = _slice(_read(DOCS / "workflows.md"), "### Update Skill (US)", "**Agent:**")
    headless = _slice(workflows, "**Headless:**", "\n")
    assert "`detect-changes:doc-hashes`" in headless and "could not be checked" in headless
    docs = _documents(tmp_path)
    # row 1: A matches, B (null) can now be read, so it is changed and the manifest routes it to step 3
    values = _docs_only_skill(tmp_path, "row1", [docs["A"], docs["B"]])
    compared = _run_call(call, "compareDocHashesHelper", DETECT_DOCS, values)
    assert compared["unchanged"] == [{"url": docs["A"]["url"]}]
    assert [(e["url"], e["old_hash"]) for e in compared["changed"]] == [(docs["B"]["url"], None)]
    assert compared["changed"][0]["new_hash"] == "sha256:" + hashlib.sha256(b"b one\n").hexdigest()
    assert compared["skipped_null_hash"] == []
    built = _run_call(_fence(one, BUILD_CALL), "buildChangeManifestHelper", BUILD_MANIFEST, values)
    assert built["no_changes"] is False and built["changed_urls"] == [docs["B"]["url"]]
    # row 3: D (null) and E both fail to fetch, so nothing was compared and §1 HALTs
    values = _docs_only_skill(tmp_path, "row3", [docs["D"], docs["E"]])
    compared = _run_call(call, "compareDocHashesHelper", DETECT_DOCS, values)
    assert compared["stats"]["changed"] + compared["stats"]["unchanged"] == 0
    assert [(e["url"], e["old_hash"]) for e in compared["fetch_failed"]] == \
        [(docs["D"]["url"], None), (docs["E"]["url"], docs["E"]["content_hash"])]
    assert all(e["reason"] for e in compared["fetch_failed"]) and compared["skipped_null_hash"] == []
    # row 4: no doc_sources at all, so §1 HALTs with the no-doc_sources list
    values = _docs_only_skill(tmp_path, "row4", None)
    compared = _run_call(call, "compareDocHashesHelper", DETECT_DOCS, values)
    assert compared["stats"]["total_tracked"] == 0
    assert compared["stats"]["changed"] + compared["stats"]["unchanged"] == 0


def test_a_docs_only_no_change_report_counts_its_documents(tmp_path):
    four = _slice(_read(DETECT), "### 4. Check for No-Change Shortcut", "### 5.")
    assert "for a docs-only skill, when every document §1 compared matched" in four
    four_counts = _slice(four, "For a docs-only skill, say", "\n")
    one = _slice(_read(REPORT), "### 1. Handle No-Change Shortcut", "### 1a.")
    report_counts = _slice(one, "For a docs-only skill (`mode` is `docs-only`", "\n")
    for paragraph in (four_counts, report_counts):
        for token in (f'"{COUNTS}"', f'"{COUNTS_NOT_CHECKED}"', "when `docs_not_checked` is above 0",
                      "`{run_dir}/change-manifest.json`"):
            assert token in paragraph, token
        assert "\u2014" not in paragraph  # no em dash
    assert 'in place of "Source code matches provenance map exactly."' in four_counts
    assert 'replace the sentence that starts "Source code matches provenance map exactly"' in report_counts
    # after the gap-driven replacement, before the `{source_moved}` notice the target-version paragraph follows
    assert one.index("In gap-driven mode") < one.index(report_counts) < one.index("When `{source_moved}` is true")
    # §1's counts reach the manifest the report reads them from
    assert '"docs_tracked", "docs_unchanged", "docs_not_checked"' in _detect_one()
    build = _fence(_detect_one(), BUILD_CALL)
    call = _fence(_detect_one(), COMPARE_CALL)
    docs = _documents(tmp_path)

    def counts(name: str, doc_sources: list) -> tuple:
        values = _docs_only_skill(tmp_path, name, doc_sources)
        _run_call(call, "compareDocHashesHelper", DETECT_DOCS, values)
        built = _run_call(build, "buildChangeManifestHelper", BUILD_MANIFEST, values)
        c = built["counts"]
        return built["no_changes"], (c["docs_tracked"], c["docs_unchanged"], c["docs_not_checked"])

    # row 2: A matches and D (null) still cannot be read
    assert counts("row2", [docs["A"], docs["D"]]) == (True, (2, 1, 1))
    filled = COUNTS_NOT_CHECKED.replace("{docs_unchanged}", "1").replace("{docs_tracked}", "2") \
        .replace("{docs_not_checked}", "1")
    assert filled == "1 of 2 tracked documents match their recorded hashes; 1 could not be checked (see Warnings)."
    # row 5: A and C match
    assert counts("row5", [docs["A"], docs["C"]]) == (True, (2, 2, 0))
    assert COUNTS.replace("{docs_unchanged}", "2").replace("{docs_tracked}", "2") == \
        "2 of 2 tracked documents match their recorded hashes."
