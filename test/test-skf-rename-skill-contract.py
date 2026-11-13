#!/usr/bin/env python3
"""Rename Skill contract: the inputs a run binds once and honours in either mode
(#594), the per-run flag beside the standing setting for the official-source
gate (#594, #596), the helpers resolved before the first question with no
in-prompt fallback (#599), and one home for the headless contract with lean
stage files and one manifest flag name (#600), and the w3 re-check findings
(#591): one helper call for the package rename and the in-file rewrite, and
the manifest backup as a file in the run folder. The step 5b gate adds two:
a copy `npx skills add` installed under the old name is named in the plan,
recorded as a warning and given its reinstall step in the report, and the
verify-failed halt says how to recover.

Step prose is not executed by any test, so most checks pin the prose an agent
follows. The source-authority decision is also run through the shared emitter,
filled in as an agent fills it for each reason the step names, and the
envelope it builds is checked against the rename schema.

test-skf-ownership-gates.py covers the rest of the run: the ownership gate,
the run lock, every halt site against the schema's exit codes, the dry-run and
success envelopes and the recovery after a manifest re-key.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
RENAME = SRC / "skf-rename-skill"
SKILL = "src/skf-rename-skill/SKILL.md"
SELECT = "src/skf-rename-skill/references/select.md"
EXECUTE = "src/skf-rename-skill/references/execute.md"
REPORT = "src/skf-rename-skill/references/report.md"
EXIT_CODES = "src/skf-rename-skill/references/exit-codes.md"
CONTRACT = "src/skf-rename-skill/references/invocation-contract.md"
CUSTOMIZE = RENAME / "customize.toml"
EMITTER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
SCHEMA = json.loads((SRC / "shared" / "scripts" / "schemas" / "skf-rename-skill-result-envelope.v1.json")
                   .read_text(encoding="utf-8"))
PREFIX = "SKF_RENAME_SKILL_RESULT_JSON: "
FLAG = "--acknowledge-official"
# Each probe order select.md §1 resolves, and the helper it names in the start-run halt.
SELECT_HELPERS = {
    "runLockProbeOrder": ("{runLockHelper}", "skf-run-lock.py"),
    "emitEnvelopeProbeOrder": ("{emitEnvelopeHelper}", "skf-emit-result-envelope.py"),
    "manifestOpsProbeOrder": ("{manifestOpsHelper}", "skf-manifest-ops.py"),
    "skillInventoryProbeOrder": ("{skillInventoryHelper}", "skf-skill-inventory.py"),
    "skillRosterProbeOrder": ("{skillRosterHelper}", "skf-skill-roster.py"),
}


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` (which occurs once) up to marker `end`."""
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _row(text: str, aspect: str) -> str:
    [row] = [line for line in text.splitlines() if line.startswith(f"| **{aspect}** |")]
    return row


def _frontmatter(rel: str) -> str:
    return _read(rel).split("\n---\n", 1)[0]


def _body(rel: str) -> str:
    return _read(rel).split("\n---\n", 1)[1]


# --------------------------------------------------------------------------
# #600: one home for the headless contract, lean stage files
# --------------------------------------------------------------------------

def test_skill_md_points_at_the_lifted_contract():
    skill = _read(SKILL)
    for lifted in ("## Result Contract", "| **Flags** |", "| **Inputs** |", "| **Gates** |", "| **Headless** |",
                   "| **Concurrency** |", "SKF_RENAME_SKILL_RESULT_JSON: {"):
        assert lifted not in skill, lifted
    pointer = _section(skill, "## Invocation Contract", "## On Activation")
    assert "`references/invocation-contract.md`" in pointer and "`references/exit-codes.md`" in pointer
    assert "Interactive runs do not need them." in pointer
    contract = _read(CONTRACT)
    for aspect in ("Inputs", "Flags", "Gates", "Outputs", "Concurrency", "Headless", "Exit codes"):
        assert _row(contract, aspect), aspect
    flags = _row(contract, "Flags")
    for flag in ("`--headless`", "`-H`", "`--dry-run`", f"`{FLAG}`"):
        assert flag in flags, flag
    assert "## Result Contract (Headless)" in contract


def test_stage_files_stay_under_their_budgets():
    """The prepass budgets (SKILL.md 2,500 tokens, a single-purpose reference 9,000), on its chars/4 fallback."""
    for rel, budget in ((SKILL, 2500), (SELECT, 9000), (EXECUTE, 9000)):
        assert len(_read(rel)) // 4 < budget, rel


def test_frontmatter_names_each_helper_in_one_line():
    """leanness-1: a frontmatter comment names its helper and the sections that call it, nothing more."""
    for rel, helpers in ((SELECT, ("{manifestOpsHelper}", "{skillInventoryHelper}", "{skillRosterHelper}",
                                   "{renameNameValidator}", "{runLockHelper}")),
                         (EXECUTE, ("{atomicWriteHelper}", "{manifestOpsHelper}", "{rebuildManagedSectionsHelper}",
                                    "{rewriteSkillNameHelper}", "{verifyNoTraceHelper}", "{skillInventoryHelper}",
                                    "{runLockHelper}"))):
        comments = [line for line in _frontmatter(rel).splitlines() if line.startswith("#")]
        for helper in helpers:
            assert len([c for c in comments if c.startswith(f"# {helper}")]) == 1, (rel, helper)
        # One shared two-line preamble, then one line per helper.
        assert len(comments) <= len(helpers) + 2, rel
        for internal in ("fall back", "Git Bash", "semver", "fsync", "region split", "atomicity-critical"):
            assert internal not in _frontmatter(rel), (rel, internal)


def test_execute_keeps_what_the_model_acts_on():
    """leanness-1: the docstring copies are gone; the calls, the bound fields and the safety clauses stay."""
    execute = _read(EXECUTE)
    assert execute.count("Git Bash") == 1, "the ln -s reason is given once"
    assert "../" not in execute, "the relative link example is described in words"
    for internal in ("_HEADER_SLOT", "`source_repo`", "`co_import_files`", "temporary name", "mklink /J",
                     "Quick Skill's `source_package`", "reads it back to check the markers"):
        assert internal not in execute, internal
    section2 = _section(execute, "### 2. Rename the Packages and Rewrite the Name", "### 3. ")
    for name in ("SKILL.md", "metadata.json", "context-snippet.md", "provenance-map.json"):
        assert f"- **{name}**" in section2, name
    assert "`rename` in `renamer`" in section2, "why the rewrite helper exists"
    assert "names them in `package_warnings` and `missing_files` and goes on" in section2
    assert "**Rollback on any other exit than 0:**" in section2
    verify = _section(execute, "### 5. Verify", "### 6. ")
    for field in ("`clean`", "`hard_matches`", "`body_warnings`", "`dir_violations`"):
        assert field in verify, field
    replace = _section(execute, "3. **Replace the section.**", "4. **On per-file failure**")
    assert "Feed the staged body to the helper on stdin" in replace


def test_execute_renames_and_rewrites_in_one_call():
    """w3 determinism-1: the per-version move and the per-file rewrite are one helper call; an absent
    package or file is named, and only a failed move or rewrite rolls back."""
    execute = _read(EXECUTE)
    section2 = _section(execute, "### 2. Rename the Packages and Rewrite the Name", "### 3. ")
    calls = [line for line in section2.splitlines() if "{rewriteSkillNameHelper}" in line and "uv run" in line]
    assert calls == ['uv run {rewriteSkillNameHelper} --skill-group "{new_skill_group}" \\'], calls
    assert '--result-to "{run_dir}/rename-rewrite.json"' in section2, "the record survives in the run folder"
    assert "when that package is there" in section2
    assert "Only a move, a rewrite or the record write that fails stops it" in section2
    assert "When stdout holds no JSON (a usage error or a traceback), `{error.path}` is `{new_skill_group}`" in section2
    for stale in ("mv {new_skill_group}", "Invoke it once per file", "Check that the target file exists first",
                  "section2_warnings", "section3_warnings"):
        assert stale not in execute, stale
    for phase in ("`emit-halt` phase `execute:inner-rename`", "`emit-halt` phase `execute:rewrite`"):
        assert phase in section2, phase
    record = _section(execute, "### 3. Record the Rewrite", "### 4. ")
    for binding in ("`renamed_versions` ← `renamed_versions`", "`rewrite_counts` ← `counts`"):
        assert binding in record, binding
    assert ("Its `files_rewritten` (the `{kind, path}` of each file it wrote), `package_warnings` and "
            "`missing_files` stay in `{run_dir}/rename-rewrite.json` for step 3.") in record
    row = next(line for line in _read(EXIT_CODES).splitlines() if line.startswith("| 4 "))
    assert "step 2 §2 (inner-dir rename, file content update or the record it writes to the run folder)" in row and "§3 (file content update)" not in row


def test_the_report_reads_the_rewrite_record_back():
    """The batch's record in the run folder is what step 3 reports from, never a copy carried in context."""
    stored = _section(_read(EXECUTE), "### 9. Store Results in Context", "### 10. ")
    for name in ("renamed_versions", "files_rewritten", "rewrite_counts", "package_warnings", "missing_files"):
        assert f"- `{name}`" not in stored, name
    assert ("§2's record, `{run_dir}/rename-rewrite.json`, holds `renamed_versions`, `files_rewritten`, `counts`, "
            "`package_warnings` and `missing_files`: step 3 reads them there.") in stored
    write = _section(_read(REPORT), "### 1. Write the Result Files and the Envelope", "### 2. ")
    assert write.index("Read `{run_dir}/rename-rewrite.json`") < write.index("```bash")
    assert ("bind from it `renamed_versions`, `rewrite_counts` ← `counts`, `package_warnings` and "
            "`missing_files`") in write
    # determinism-3: the emitter reads `files_rewritten` from the record, so the report never binds it, and a
    # refusal that names the record takes the warning path at once: a retry of the payload cannot fix it.
    assert "files_rewritten" not in write
    assert ("When its `message` names the record, `rename-rewrite.json`, which a retry cannot fix, or it still exits "
            "non-zero, or prints no line, the rename stays committed: show its stderr message as a warning") in write


def test_execute_binds_one_manifest_flag():
    """#600: section 6 binds manifest_rekeyed, the name section 9, the report and the envelope read."""
    manifest = _section(_read(EXECUTE), "### 6. Update Export Manifest", "### 7. ")
    assert manifest.count("`manifest_rekeyed = false`") == 1 and manifest.count("`manifest_rekeyed = true`") == 1
    for rel in (SKILL, SELECT, EXECUTE, REPORT, CONTRACT):
        assert "manifest_updated" not in _read(rel), rel
    assert '"manifest_rekeyed": <manifest_rekeyed>' in _read(REPORT)


# --------------------------------------------------------------------------
# #599: every helper resolved before the first question, no in-prompt fallback
# --------------------------------------------------------------------------

def test_select_resolves_every_helper_it_calls_before_the_first_question():
    select = _read(SELECT)
    start = _section(select, "### 1. Start the Run", "### 2. ")
    for order, (helper, script) in SELECT_HELPERS.items():
        assert f"`{helper}` ← first existing path in `{{{order}}}`" in start, helper
        assert f"`{script}`" in start, script
    assert "all five stay bound for the rest of the run" in start
    # §1 is the only place select.md resolves a helper.
    after = select[select.index("### 2. Read the Skill Roster"):]
    assert "first existing path in" not in after


def test_select_has_no_in_prompt_fallback():
    body = _body(SELECT)
    for fallback in ("fall back", "in-prompt", "in the prompt", "cannot run", "no existing candidate**",
                     "without `{skillInventoryHelper}`", "Python/`uv` unavailable", "python3 "):
        assert fallback not in body, fallback
    assert "fall back" not in _frontmatter(SELECT)
    rule = _section(_read(SKILL), "## Workflow Rules", "## Stages")
    assert "achieve the outcome in your main context thread" not in rule
    assert ("Every helper is required: select.md §1, §5's validator call and execute.md §0 halt (exit 4) "
            "without one") in rule


def test_every_select_helper_call_runs_with_uv():
    """determinism-3: one interpreter, so a host that cannot run the helpers stops at §1."""
    body = _body(SELECT)
    for helper in ("{manifestOpsHelper}", "{skillInventoryHelper}", "{skillRosterHelper}", "{renameNameValidator}",
                   "{runLockHelper}", "{emitEnvelopeHelper}"):
        calls = re.findall(rf"^\s*(\S+(?: \S+)?) {re.escape(helper)} ", body, re.M)
        assert calls and set(calls) == {"uv run"}, (helper, calls)


def test_each_helper_call_that_prints_no_json_halts_with_its_phase():
    select = _read(SELECT)
    for start, end, phase in (("### 2. Read the Skill Roster", "### 3. ", "select:list-skills"),
                              ("### 5. Ask for New Name", "### 6. ", "select:validate-new-name"),
                              ("### 7. Enumerate Affected Versions", "### 8. ", "select:affected-versions")):
        section = _section(select, start, end)
        halts = [line for line in section.splitlines() if "no json" in line.lower() and "HALT (exit code 4" in line]
        assert halts, start
        assert all(f'`halt_reason: "write-failed"`, `emit-halt` phase `{phase}`' in line for line in halts), start
    row = next(line for line in _read(EXIT_CODES).splitlines() if line.startswith("| 4 "))
    assert "the run-lock, envelope, manifest, inventory or roster helper is missing" in row
    assert "step 1 §2, §5 and §7 (the skill roster cannot be read" in row


# --------------------------------------------------------------------------
# #594: inputs bound once and honoured in either mode
# --------------------------------------------------------------------------

def test_activation_binds_the_invocation_once():
    activation = _section(_read(SKILL), "2. **Bind the invocation once**, in every mode:", "3. **Resolve workflow")
    for binding in ("`{headless_mode}`", "`{acknowledge_official}`: true if `--acknowledge-official` was passed",
                    "`{dry_run}`: true if `--dry-run` was passed", "`{old_name_arg}` and `{new_name_arg}`",
                    "each null when absent"):
        assert binding in activation, binding
    # Every flag the contract lists is bound here.
    for flag in re.findall(r"`(--[a-z-]+)`", _row(_read(CONTRACT), "Flags")):
        assert f"`{flag}`" in activation, flag


def test_supplied_names_answer_their_questions_in_either_mode():
    """enhancement-2: "rename cognee to cognee-ai" asks nothing that it already answered."""
    select = _read(SELECT)
    ask_old = _section(select, "### 4. Ask Which Skill", "### 4a. Ownership Check")
    assert "When `{old_name_arg}` is set, it is the input below in either mode, and the question is not shown." \
        in ask_old
    assert ask_old.index("`{old_name_arg}` is set") < ask_old.index("**Which skill would you like to rename?**")
    assert '`halt_reason: "input-missing"`' in ask_old and '`halt_reason: "input-invalid"`' in ask_old
    assert "say that it matches no listed skill, display the §3 list and ask again" in ask_old
    listing = _section(select, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "Display the list only when §4 asks for the skill" in listing
    assert "When `{old_name_arg}` is set and it is in `{not_skf_output}`" in listing
    ask_new = _section(select, "### 5. Ask for New Name", "### 6. Source Authority Check")
    assert "When `{new_name_arg}` is set, it is the candidate in either mode, and the question is not shown." \
        in ask_new
    assert ask_new.index("`{new_name_arg}` is set") < ask_new.index("**What is the new name for this skill?**")
    assert "Interactive: display the message and ask the question above again, also when the candidate came " \
           "from `{new_name_arg}`." in ask_new
    for rel in (SELECT, EXECUTE):
        assert "If `{headless_mode}` and old skill name was provided" not in _read(rel)


def test_stages_and_gates_match_the_stage_files():
    """architecture-8: step 2 asks nothing, and the gate map names the §6 gate with its headless default."""
    skill = _read(SKILL)
    assert "| 2 | Execute Rename | references/execute.md | Yes |" in skill
    assert "Do not re-prompt the user" in _read(EXECUTE)
    gates = _row(_read(CONTRACT), "Gates")
    order = [gates.index(gate) for gate in ("Input Gate [use args] x2", "Source-Authority Gate", "Confirm Gate [Y]")]
    assert order == sorted(order)
    assert "headless default: HALT `source-authority-blocked` unless `--acknowledge-official`" in gates
    assert "Step 2 asks nothing." in gates


# --------------------------------------------------------------------------
# #594 and #596: the per-run flag beside the standing setting
# --------------------------------------------------------------------------

def _source_authority() -> str:
    return _section(_read(SELECT), "### 6. Source Authority Check", "### 7. ")


def test_the_flag_answers_the_source_authority_gate_for_one_run():
    gate = _source_authority()
    assert ("When `{acknowledge_official}` is true, `--acknowledge-official` answers this warning for this run in "
            "either mode") in gate
    assert "proceed only when `{forceSourceAuthorityInHeadless}` is true" in gate
    halt = next(line for line in gate.splitlines() if '"source-authority-blocked"' in line)
    assert f"pass `{FLAG}` with the invocation" in halt, "the halt says how to proceed"
    assert ('or set `force_source_authority_in_headless = "true"` under `[workflow]` in '
            '`{project-root}/_bmad/custom/skf-rename-skill.toml` (or `.user.toml`) to approve every headless rename '
            "of an official skill.") in halt
    assert "customize.toml" not in halt, "never the DO-NOT-EDIT base file"
    assert halt.index("`{acknowledge_official}` is true") < halt.index('"source-authority-blocked"')
    row = next(line for line in _read(EXIT_CODES).splitlines() if line.startswith("| 5 "))
    assert f"without `{FLAG}` or `force_source_authority_in_headless`" in row
    headless = _row(_read(CONTRACT), "Headless")
    assert f"pass `{FLAG}` to proceed for one run" in headless
    assert "in `customize.toml`" not in headless


def test_the_setting_stays_a_standing_approval():
    """#596 decision: force_source_authority_in_headless is kept beside the flag."""
    toml = CUSTOMIZE.read_text(encoding="utf-8")
    assert tomllib.loads(toml)["workflow"]["force_source_authority_in_headless"] == ""
    comment = _section(toml, "# --- Optional safety scalar ---", '\nforce_source_authority_in_headless = ""')
    assert FLAG in comment and "standing approval" in comment and "TOML boolean" in comment
    binding = next(line for line in _read(SKILL).splitlines() if "`{forceSourceAuthorityInHeadless}` ←" in line)
    assert 'is `"true"` or the TOML boolean `true`' in binding, "a TOML bool true must not halt"


def test_the_setting_is_written_under_the_workflow_table():
    """#1108: the resolver reads `--key workflow`, so a key written above the `[workflow]` line lands at the
    file's root, never reaches the gate and warns nothing. The comment, the halt, the Headless row and the docs
    give the `[workflow]` form, and TOML bears the comment's two lines out."""
    toml = CUSTOMIZE.read_text(encoding="utf-8")
    comment = " ".join(line.lstrip("#").strip() for line in _section(
        toml, "# --- Optional safety scalar ---", '\nforce_source_authority_in_headless = ""').splitlines())
    for token in ("records the decision in its headless_decisions. In {project-root}/_bmad/custom/"
                  "skf-rename-skill.toml (or .user.toml) write it under the table, as two lines: `[workflow]` then "
                  '`force_source_authority_in_headless = "true"`.',
                  "A key above the `[workflow]` line is ignored without a warning, and headless renames of an "
                  "official skill keep halting."):
        assert token in comment, token
    # The comment's two lines, written as an override file, set the key the gate reads.
    lines = re.search(r"as two lines: `(\[workflow\])` then `([^`]+)`", comment).groups()
    assert tomllib.loads("\n".join(lines))["workflow"] == {"force_source_authority_in_headless": "true"}
    # The same key without the table line parses, but `workflow` holds no setting: the gate keeps halting.
    bare = tomllib.loads(lines[1])
    assert bare == {"force_source_authority_in_headless": "true"}
    assert "force_source_authority_in_headless" not in bare.get("workflow", {})
    halt = next(line for line in _source_authority().splitlines() if '"source-authority-blocked"' in line)
    assert ('set `force_source_authority_in_headless = "true"` under `[workflow]` in '
            "`{project-root}/_bmad/custom/skf-rename-skill.toml` (or `.user.toml`)") in halt
    headless = _row(_read(CONTRACT), "Headless")
    assert ('The `force_source_authority_in_headless = "true"` setting, written under `[workflow]` in '
            "`{project-root}/_bmad/custom/skf-rename-skill.toml` (or `.user.toml`), is a standing approval for "
            "every headless run.") in headless
    assert "(SKILL.md On Activation step 3 names the files)" not in headless
    docs = next(line for line in _read("docs/workflows.md").splitlines() if line.startswith("- Rename Skill: pass"))
    assert docs.endswith('Write it as two lines, `[workflow]` then `force_source_authority_in_headless = "true"`.')


def _decision_reasons() -> list[str]:
    gate = _source_authority()
    m = re.search(r"`\{source_authority_reason\}` ← `([^`]+)` when `\{acknowledge_official\}` is true, else `([^`]+)`",
                  gate)
    assert m, "the decision names why the gate resolved"
    return [m.group(1), m.group(2)]


def test_each_reason_reaches_the_envelope(tmp_path):
    """The documented decision, with each reason the step names, is recorded and emitted, and validates."""
    reasons = _decision_reasons()
    assert reasons == [f"{FLAG} flag", "force_source_authority_in_headless override"]
    [template] = re.findall(r"<<'SKF_DECISION'\n(.*?)\nSKF_DECISION\n", _source_authority(), re.S)
    for index, reason in enumerate(reasons):
        run_dir = tmp_path / f"skf-rename-skill-20261001T000000Z-0000000{index}"
        decision = json.loads(template.replace("{source_authority_reason}", reason))
        record = subprocess.run([sys.executable, str(EMITTER), "record", "--workflow", "skf-rename-skill",
                                 "--run-dir", str(run_dir), "--decision"],
                                input=json.dumps(decision).encode("utf-8"), capture_output=True, timeout=60)
        assert record.returncode == 0, record.stderr
        payload = {"status": "dry-run", "old_name": "demo", "new_name": "demo-kit", "versions_renamed": ["1.0.0"],
                   "manifest_rekeyed": False, "context_files_updated": [], "halt_reason": None}
        emit = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-rename-skill",
                               "--run-dir", str(run_dir)],
                              input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=60)
        assert emit.returncode == 0, emit.stderr
        [line] = emit.stdout.decode("utf-8").splitlines()
        envelope = json.loads(line.removeprefix(PREFIX))
        assert not list(Draft202012Validator(SCHEMA).iter_errors(envelope))
        assert envelope["headless_decisions"] == [{"gate": "source-authority", "default_action": "halt",
                                                   "taken_action": "proceed", "reason": reason}]


# --------------------------------------------------------------------------
# #596: the hook comments say when each hook runs and what on_complete runs
# --------------------------------------------------------------------------

def test_hook_comments_match_activation_and_the_report():
    toml = CUSTOMIZE.read_text(encoding="utf-8")
    prepend = _section(toml, "# Steps to run in On Activation step 3", "activation_steps_prepend =")
    assert "after config load and headless" in prepend and "uv probe" not in toml
    append = _section(toml, "# Steps to run at the end of On Activation", "activation_steps_append =")
    assert "just before select.md loads" in append
    # #1111: SKILL.md names the step the entries precede, as the comment does.
    step3 = " ".join(_section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ").split())
    assert step3.endswith("then, before step 4 loads select.md, execute each entry in "
                          "`workflow.activation_steps_append` in order."), step3[-160:]
    assert "after activation completes" not in step3
    hook = _section(toml, "# Optional post-completion hook", "on_complete =")
    for needle in ("a shell command, run from {project-root}", "report step 3",
                   '--result-path="<the per-run result file the shared', "skipped when the emitter wrote no result",
                   "a --dry-run never", "never fails the rename"):
        assert needle in hook, needle
    report = _section(_read(REPORT), "### 3. Post-Completion Hook (optional)", "### 4. ")
    assert "and `{result_path}` is not null, run it as a shell command from `{project-root}`" in report
    assert "never fail the workflow on a hook error" in report


def test_the_project_context_default_stays_and_says_how_to_drop_it():
    """#596 decision: keep the persistent_facts default and document the override that turns it off."""
    toml = CUSTOMIZE.read_text(encoding="utf-8")
    assert tomllib.loads(toml)["workflow"]["persistent_facts"] == ["file:{project-root}/**/project-context.md"]
    drop = '"!file:{project-root}/**/project-context.md"'
    comment = _section(toml, "# Persistent facts the workflow keeps in mind", "\npersistent_facts =")
    assert "{project-root}/_bmad/custom/skf-rename-skill.toml" in comment and drop in comment
    activation = _section(_read(SKILL), "3. **Resolve workflow customization.**", "4. Load, read the full file")
    # The customization helper applies the drop (#1106), and the step says so.
    assert "`--facts` has applied each `!` entry, which drops each earlier entry it names" in activation
    assert "the bundled default loads every `project-context.md` under `{project-root}`" in activation


def test_the_manifest_backup_is_a_file_in_the_run_folder():
    """w3 determinism-2: the backup is copied, never held in context, and the restore reads it back."""
    manifest = _section(_read(EXECUTE), "### 6. Update Export Manifest", "### 7. ")
    assert ('cp "{skills_output_folder}/.export-manifest.json" "{run_dir}/export-manifest.backup.json" '
            '2> "{run_dir}/call.err"') in manifest
    assert ('uv run {atomicWriteHelper} write --target "{skills_output_folder}/.export-manifest.json" '
            '< "{run_dir}/export-manifest.backup.json"') in manifest
    for stale in ("manifest_backup", "hold its exact text", "SKF_MANIFEST_BACKUP", "Read the manifest again"):
        assert stale not in manifest, stale
    for call in ("uv run {manifestOpsHelper} {skills_output_folder} get {new_name}",
                 "uv run {manifestOpsHelper} {skills_output_folder} get {old_name}"):
        assert call in manifest, call
    report = _read(REPORT)
    assert ('"{run_dir}/rename-rewrite.json" "{run_dir}/export-manifest.backup.json" "{run_dir}/call.err" '
            '&& rmdir "{run_dir}"') in report


def test_the_report_lists_what_it_shows():
    """w3 leanness-6: the report names its values and fixes; the model lays them out."""
    report = _section(_read(REPORT), "### 2. Render the Report", "### 3. ")
    assert "```" not in report, "no layout template"
    for value in ("`renamed_versions`", "`rewrite_counts`", "`manifest_rekeyed`", "`context_files_updated`",
                  "`context_files_failed`", "`{forge_left_in_place}`", "`package_warnings`", "`missing_files`",
                  "`{run_warnings}`", "`verification_warnings`", "`deletion_errors`", "`{headless_decisions}`",
                  "`{result_path}`"):
        assert value in report, value
    for fix in ("Re-run `[EX] Export Skill` to retry the managed section rebuild for these files.",
                "Remove the remnants by hand with `rm -rf {path}`.", "re-run `@Ferris SF`",
                "this rename is a LOCAL operation only"):
        assert fix in report, fix


# --------------------------------------------------------------------------
# #1158 architecture-1: each context file is rebuilt with its own skill root
# --------------------------------------------------------------------------

REBUILD_PY = SRC / "shared" / "scripts" / "skf-rebuild-managed-sections.py"
OVERRIDE_GROUP = '[--skill-root-override "{snippet_skill_root_override}"]'


def _rebuild_calls() -> list[str]:
    """§7's fenced `{rebuildManagedSectionsHelper}` calls, backslash continuations joined."""
    calls, joined, fence = [], "", False
    for line in _section(_read(EXECUTE), "### 7. Rebuild Context Files", "### 8. ").split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            continue
        if line.rstrip().endswith("\\"):
            joined += line.rstrip()[:-1].strip() + " "
            continue
        joined += line.strip()
        if "{rebuildManagedSectionsHelper}" in joined:
            calls.append(" ".join(joined.split()))
        joined = ""
    return calls


def _documented_argv(call: str, values: dict, override: str | None) -> list[str]:
    """A documented call filled in as an agent fills it, without a shell: a list value is one argument per item."""
    call = call.replace(OVERRIDE_GROUP, OVERRIDE_GROUP[1:-1] if override else "")
    argv = []
    for word in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call)):
        whole = re.fullmatch(r"@@(\w+)@@", word)
        if whole and isinstance(values[whole.group(1)], list):
            argv.extend(values[whole.group(1)])
        else:
            argv.append(re.sub(r"@@(\w+)@@", lambda m: str(values[m.group(1)]), word))
    assert argv[:2] == ["python3", str(REBUILD_PY)], argv
    return [sys.executable, *argv[1:]]


@pytest.mark.parametrize("override", [None, "skills/"], ids=["ide-roots", "override"])
def test_two_ides_give_each_context_file_its_own_skill_root(tmp_path, override):
    """With ides [claude-code, codex], AGENTS.md lists the renamed skill under Codex's `.agents/skills/`, not the root
    of the first target, and --skill-root-override still wins for both. The values hold no `skill_root`: a bare
    `{skill_root}` reaching assemble would fail to fill, as nothing in rename binds it."""
    text = _section(_read(EXECUTE), "### 7. Rebuild Context Files", "### 8. ")
    assert "{skill_root}" not in text
    assert "its skill root `{target_skill_root}` is that entry's own `skill_root`" in text
    skills = tmp_path / "skills"
    package = skills / "beta" / "2.0.0" / "beta"
    package.mkdir(parents=True)
    (package / "context-snippet.md").write_bytes(
        b"[beta v2.0.0]|root: .claude/skills/beta/\n|IMPORTANT: beta v2.0.0: read SKILL.md before writing beta code.\n")
    (package / "metadata.json").write_bytes(json.dumps({"name": "beta", "skill_type": "single"}).encode("utf-8"))
    record = {"ides": ["claude-code"], "last_exported": "2026-01-01", "status": "active"}
    (skills / ".export-manifest.json").write_bytes(json.dumps(
        {"schema_version": "2", "exports": {"beta": {"active_version": "2.0.0", "versions": {"2.0.0": record}}}}
    ).encode("utf-8"))
    for name, root in (("CLAUDE.md", ".claude/skills/"), ("AGENTS.md", ".agents/skills/")):
        (tmp_path / name).write_bytes((
            "# Project\n\n<!-- SKF:BEGIN updated:2026-01-01 -->\n[SKF Skills]|1 skills|0 stack\n|\n"
            f"|[old-beta v2.0.0]|root: {root}old-beta/\n<!-- SKF:END -->\n").encode("utf-8"))
    resolve, check, assemble, replace = _rebuild_calls()
    values = {"rebuildManagedSectionsHelper": str(REBUILD_PY), "ides": "claude-code,codex",
              "skills_output_folder": str(skills), "old_name": "old-beta", "new_name": "beta",
              "snippet_skill_root_override": override or ""}
    proc = subprocess.run(_documented_argv(resolve, values, override), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    targets = json.loads(proc.stdout)["targets"]
    assert [(t["context_file"], t["skill_root"]) for t in targets] == [
        ("CLAUDE.md", ".claude/skills/"), ("AGENTS.md", ".agents/skills/")]
    values["target_paths"] = [str(tmp_path / t["context_file"]) for t in targets]
    roots = {}
    for target in targets:
        path = tmp_path / target["context_file"]
        values.update(context_path=str(path), target_skill_root=target["skill_root"])
        for call in (check, assemble):
            proc = subprocess.run(_documented_argv(call, values, override), capture_output=True, timeout=60)
            assert proc.returncode == 0, proc.stdout + proc.stderr
        command, _, source = replace.partition(" < ")
        with open(source.strip().strip('"').replace("{context_path}", str(path)), "rb") as staged:
            proc = subprocess.run(_documented_argv(command, values, override), stdin=staged, capture_output=True,
                                  timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        Path(str(path) + ".skf-content").unlink()
        roots[target["context_file"]] = re.findall(r"\|root: (\S+)beta/", path.read_bytes().decode("utf-8"))
    assert roots == {"CLAUDE.md": [override or ".claude/skills/"], "AGENTS.md": [override or ".agents/skills/"]}


# --------------------------------------------------------------------------
# step 5b: the copy `npx skills add` installed under the old name
# (enhancement-1), and the verify-failed recovery (determinism-1)
# --------------------------------------------------------------------------

INSTALLED_ROOTS = "{the skill_root of each target_context_files entry, each quoted}"
INSTALLED_RECORD = ('uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" '
                    '--warning "installed-copy-not-renamed: {path}"')


def _installed_copies() -> str:
    delete = _section(_read(EXECUTE), "### 8. Delete Old Directories", "### 9. ")
    assert delete.index("guarded-delete") < delete.index("**Installed copies.**"), "checked after the delete"
    return delete[delete.index("**Installed copies.**"):]


def _installed_check() -> str:
    """The one bash block that lists the copies: the shell skips the skills folder and dedupes, not the model."""
    copies = _installed_copies()
    start = copies.index("```bash\n") + len("```bash\n")
    return copies[start:copies.index("```", start)]


def test_the_rename_names_the_installed_copies_it_leaves():
    """The rows point at `{skill_root}{new_name}/`, but no step renames the copy `npx skills add`
    installed under the old name: step 2 finds it, the envelope warns, and the report says how to reinstall."""
    copies = _installed_copies()
    assert ("When `snippet_skill_root_override` is unset in `config.yaml`, list the copies under the `skill_root` "
            "of the `target_context_files` entries") in copies
    check = _installed_check()
    for token in (f"for root in {INSTALLED_ROOTS}; do", '[ "{project-root}/${root}" -ef "{skills_output_folder}" ] '
                  "&& continue", 'copy="{project-root}/${root}{old_name}"', "done | sort -u"):
        assert token in check, token
    assert "Bind `installed_copies` to the lines it prints" in copies
    assert "It skips a skill root that is the skills folder itself, where the path is `{old_skill_group}`" in copies
    assert INSTALLED_RECORD in copies
    stored = _section(_read(EXECUTE), "### 9. Store Results in Context", "### 10. ")
    for name in ("installed_copies", "target_version"):
        assert f"- `{name}`:" in stored, name
    report = _section(_read(REPORT), "### 2. Render the Report", "### 3. ")
    # Each copy is shown once, in the next steps with its fix, not again among the warnings.
    assert ("`{run_warnings}`, as warnings, except a `{run_warnings}` entry that starts with "
            "`installed-copy-not-renamed:`, which the next steps name.") in report
    steps = report[report.index("Close with the next steps:"):]
    for token in ("For each path in `installed_copies`", "the rebuilt rows point at the same folder under `{new_name}`",
                  "run `npx skills add {new_skill_group}/{version}/{new_name}`, then reload the IDE.",
                  "`{version}` is `target_version`, else the first of `renamed_versions` (newest first)",
                  "`{new_skill_group}` is absolute, as export requires"):
        assert token in steps, token
    plan = _section(_read(SELECT), "### 8. Confirmation Gate", "### 9. ")
    assert ("Copies installed in your IDE skill folders (`npx skills add`) are not renamed;\n"
            "  unless `snippet_skill_root_override` is set, the report names any it finds.") in plan
    # select.md binds new_skill_group absolute, and renamed_versions keeps affected_versions' newest-first order.
    assert "- `new_skill_group`: absolute path `{skills_output_folder}/{new_name}`" in _read(SELECT)
    assert "`affected_versions` = `result.affected_versions` (newest first)" in _read(SELECT)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="runs the documented check through bash")
def test_the_installed_copy_check_finds_a_folder_or_a_link_and_the_envelope_carries_it(tmp_path):
    """A copy is a folder, or a link (a dangling one included); a missing path is no copy, a root two
    targets share is listed once, and the skills folder's own old group (a delete that failed) is
    skipped. Each copy found reaches the envelope's existing `warnings`, which the rename schema accepts."""
    project = tmp_path / "project"
    (project / ".claude" / "skills" / "cognee").mkdir(parents=True)
    (project / ".cursor" / "skills").mkdir(parents=True)
    (project / ".cursor" / "skills" / "cognee").symlink_to(project / "gone")
    (project / ".agents" / "skills").mkdir(parents=True)
    (project / "skills" / "cognee").mkdir(parents=True)  # the old skill group a failed delete left
    roots = '".claude/skills/" ".cursor/skills/" ".agents/skills/" "skills/" ".claude/skills/"'
    check = (_installed_check().replace(INSTALLED_ROOTS, roots).replace("{project-root}", project.as_posix())
             .replace("{skills_output_folder}", (project / "skills").as_posix()).replace("{old_name}", "cognee"))
    run = subprocess.run(["bash", "-c", check], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    found = run.stdout.splitlines()
    assert found == [f"{project.as_posix()}/.claude/skills/cognee", f"{project.as_posix()}/.cursor/skills/cognee"]
    run_dir = tmp_path / "skf-rename-skill-20261003T000000Z-00000000"
    for path in found:
        warning = INSTALLED_RECORD.split('--warning "', 1)[1].rstrip('"').replace("{path}", path)
        record = subprocess.run([sys.executable, str(EMITTER), "record", "--run-dir", str(run_dir),
                                 "--warning", warning], capture_output=True, timeout=60)
        assert record.returncode == 0, record.stderr
    # A finished rename's versions come from the rewrite record step 2 staged in the run folder (#1180).
    (run_dir / "rename-rewrite.json").write_text(json.dumps({"renamed_versions": ["1.0.0"], "files_rewritten": []}),
                                                 encoding="utf-8")
    payload = {"status": "success", "old_name": "cognee", "new_name": "cognee-ai",
               "manifest_rekeyed": True, "context_files_updated": ["CLAUDE.md"], "halt_reason": None}
    emit = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-rename-skill",
                           "--run-dir", str(run_dir)],
                          input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=60)
    assert emit.returncode == 0, emit.stderr
    [line] = emit.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line.removeprefix(PREFIX))
    assert not list(Draft202012Validator(SCHEMA).iter_errors(envelope))
    assert envelope["warnings"] == [f"installed-copy-not-renamed: {path}" for path in found]
    assert envelope["versions_renamed"] == ["1.0.0"]


def test_a_verify_failed_halt_says_how_to_recover():
    """determinism-1 (a skill named after its library cannot be renamed, as docs/troubleshooting.md
    says) is accepted as a written exception by the maintainer's 2026-10-03 decision: the halt names
    the ways out the guide gives, and points at the guide, instead of leaving the user at the rollback."""
    verify = _section(_read(EXECUTE), "### 5. Verify", "### 6. ")
    [halt] = [line for line in verify.splitlines() if "**Verification failed.**" in line]
    for token in ("Old skill is intact.", "edit it in the old skill's file, then re-run the rename.",
                  "or `{old_name}` is a word of the snippet template itself, such as `api`, `root` or `data`",
                  "the skill cannot be renamed: create it again as `{new_name}` with `[BS] Brief Skill` and "
                  "`[CS] Create Skill`.", "The troubleshooting guide's `verify-failed` entry has the details.",
                  'HALT (exit code 5, `halt_reason: "verify-failed"`'):
        assert token in halt, token
    # The halt and the guide name the same three cases.
    guide = (REPO / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    entry = guide[guide.index("### Rename Skill stops with `verify-failed`"):]
    entry = entry[:entry.index("\n### ")]
    for case in ("Such a skill cannot be renamed. Create it again under the new name with Brief Skill and "
                 "Create Skill.",
                 "edit or remove it in the old skill's file, then re-run the rename.",
                 "edit that line in the old skill's snippet, then re-run.",
                 "When the old name is a label or fixed word of the snippet template itself (`api`, `root`, `data`), "
                 "the skill cannot be renamed"):
        assert case in entry, case


# --------------------------------------------------------------------------
# #1180: the roster, the source authority and the manifest entry come from
# helpers, never from a file the step reads or a join it makes by hand
# --------------------------------------------------------------------------

ROSTER = SRC / "shared" / "scripts" / "skf-skill-roster.py"
INVENTORY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"
MANIFEST_OPS = SRC / "shared" / "scripts" / "skf-manifest-ops.py"
SKF_MARK = {"generated_by": "create-skill"}


def _fenced(text: str, needle: str) -> list[str]:
    """The fenced lines of `text` that hold `needle`, stripped."""
    lines, fence = [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        elif fence and needle in line:
            lines.append(line.strip())
    return lines


def _argv(call: str, prefix: str, values: dict) -> list[str]:
    """A documented call after `prefix`, its placeholders filled and its stderr redirect left out."""
    words = shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call.removeprefix(prefix)))
    if words[-2:-1] == ["2>"]:
        words = words[:-2]
    return [re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], w) for w in words]


def _json_run(script: Path, argv: list[str]) -> tuple[int, dict | None]:
    proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, timeout=60)
    try:
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return proc.returncode, None


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def test_select_takes_the_roster_from_one_helper_call(tmp_path):
    """determinism-2: §2 is one roster call, §3 keys its halts and its list on the roster's fields, and no
    step reads the manifest, filters `skf_skill` or joins against the manifest by hand."""
    select = _read(SELECT)
    roster = _section(select, "### 2. Read the Skill Roster", "### 3. ")
    [call] = _fenced(roster, "{skillRosterHelper}")
    assert call == ('uv run {skillRosterHelper} skills "{skills_output_folder}" --forge-data-folder '
                    '"{forge_data_folder}" 2> "{run_dir}/call.err"')
    halts = [line for line in roster.splitlines() if "HALT (exit code" in line]
    assert len(halts) == 2
    assert halts[0].startswith("- **`code` is `manifest-corrupt`**") and (
        '`halt_reason: "manifest-corrupt"`, `emit-halt` phase `select:read-manifest`, with its `path` as `path`'
        in halts[0])
    assert halts[1].startswith("- **Any other error, or no JSON on stdout**") and (
        '`halt_reason: "write-failed"`, `emit-halt` phase `select:list-skills`' in halts[1])
    listing = _section(select, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "**If `empty` is true**" in listing and "`{not_skf_output}` ← `not_skf_output`" in listing
    assert ("one line per entry of `skills` as `{name} ({version_count} versions, active: {active_version})`, "
            "with \"(not in manifest)\" appended when its `in_manifest` is false") in listing
    for rel in (SELECT, EXECUTE, REPORT):
        for stale in ("manifest_exists", "manifest.exports", "skf_skill", "result.manifest"):
            assert stale not in _read(rel), (rel, stale)
    # The documented call, filled in as an agent fills it.
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _write(skills / "cognee" / "0.6.0" / "cognee" / "metadata.json", SKF_MARK)
    _write(skills / "cognee" / "0.5.0" / "cognee" / "metadata.json", SKF_MARK)
    _write(skills / "draft" / "1.0.0" / "draft" / "metadata.json", SKF_MARK)
    _write(skills / "module-skill" / "SKILL.md", "# a module's own skill\n")
    _write(skills / ".export-manifest.json", {"schema_version": "2", "exports": {
        "cognee": {"active_version": "0.6.0", "versions": {"0.6.0": {"status": "active"}}}, "gone": {}}})
    values = {"skills_output_folder": str(skills), "forge_data_folder": str(forge)}
    code, out = _json_run(ROSTER, _argv(call, "uv run {skillRosterHelper} ", values))
    assert code == 0 and out["status"] == "ok"
    assert (out["manifest_exists"], out["empty"], out["not_skf_output"]) == (True, False, ["module-skill"])
    assert [(s["name"], s["version_count"], s["in_manifest"]) for s in out["skills"]] == [
        ("cognee", 2, True), ("draft", 1, False)]
    assert "manifest" not in out


def test_source_authority_comes_from_resolve_and_no_file_is_read(tmp_path):
    """determinism-6: §6 binds `source_authority` from the `resolve` object; it never opens metadata.json."""
    source = _section(_read(SELECT), "### 6. Source Authority Check", "### 7. ")
    [call] = _fenced(source, "{skillInventoryHelper}")
    assert call == ('uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {old_name} '
                    '--forge-data-folder "{forge_data_folder}"')
    assert "From its `resolve` object bind `{source_authority}` ← `source_authority`" in source
    assert "never by opening the file" in source and "When the call fails, treat `source_authority` as absent." in source
    for stale in ("{source_metadata}", "paths.metadata", "field of that file", "there is no `metadata.json` to read"):
        assert stale not in source, stale
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _write(skills / "demo" / "1.0.0" / "demo" / "metadata.json", {**SKF_MARK, "source_authority": "official"})
    values = {"skills_output_folder": str(skills), "old_name": "demo", "forge_data_folder": str(forge)}
    argv = _argv(call, "uv run {skillInventoryHelper} ", values)
    code, out = _json_run(INVENTORY, argv)
    assert code == 0 and out["resolve"]["source_authority"] == "official"
    (skills / "demo" / "1.0.0" / "demo" / "metadata.json").unlink()
    code, out = _json_run(INVENTORY, argv)
    assert code == 0 and out["resolve"]["source_authority"] is None


def test_the_manifest_entry_is_checked_by_the_helper_before_the_backup(tmp_path):
    """determinism-1: §6 asks `get` for `exports.{old_name}` before the backup and branches on its status."""
    manifest = _section(_read(EXECUTE), "### 6. Update Export Manifest", "### 7. ")
    get = 'uv run {manifestOpsHelper} {skills_output_folder} get {old_name} 2> "{run_dir}/call.err"'
    assert _fenced(manifest, "get {old_name} 2>") == [get]
    assert manifest.index(get) < manifest.index('cp "{skills_output_folder}/.export-manifest.json"')
    assert "Branch on the `status` it prints, whatever its exit code:" in manifest
    branches = manifest[manifest.index("Branch on the `status`"):manifest.index("1. **Back up the manifest file**")]
    not_found = next(line for line in branches.splitlines() if line.startswith("- **`not_found`**"))
    assert "set `manifest_rekeyed = false` and skip both items below" in not_found
    failed = next(line for line in branches.splitlines() if line.startswith("- **`error`, or no JSON on stdout**"))
    assert "bind `{manifest_error}` ← its `error`, or the helper's stderr read from `{run_dir}/call.err`" in failed
    assert "take the rollback below with `{manifest_restore}` set to `unchanged`" in failed
    assert "- **`ok`**: go on with both items below." in branches
    for stale in ("manifest_exists", "Manifest update skipped", "when the manifest has no `exports.{old_name}`"):
        assert stale not in manifest, stale
    # The documented call against each state of the manifest.
    skills = tmp_path / "skills"
    skills.mkdir()
    argv = _argv(get, "uv run {manifestOpsHelper} ", {"skills_output_folder": str(skills), "old_name": "demo"})
    assert _json_run(MANIFEST_OPS, argv)[1]["status"] == "not_found", "no manifest"
    _write(skills / ".export-manifest.json", {"schema_version": "2", "exports": {"other": {}}})
    assert _json_run(MANIFEST_OPS, argv)[1]["status"] == "not_found", "no entry"
    _write(skills / ".export-manifest.json", {"schema_version": "2", "exports": {"demo": {"active_version": "1.0.0"}}})
    assert _json_run(MANIFEST_OPS, argv) == (0, {"status": "ok", "skill": "demo", "entry": {"active_version": "1.0.0"}})
    _write(skills / ".export-manifest.json", "{not json")
    code, out = _json_run(MANIFEST_OPS, argv)
    assert (code, out["status"]) == (1, "error") and out["error"]
    _write(skills / ".export-manifest.json", "[]")
    assert _json_run(MANIFEST_OPS, argv)[1] is None, "a manifest of the wrong shape prints no JSON: the rollback"
