#!/usr/bin/env python3
"""Rename Skill contract: the inputs a run binds once and honours in either mode
(#594), the per-run flag beside the standing setting for the official-source
gate (#594, #596), the helpers resolved before the first question with no
in-prompt fallback (#599), and one home for the headless contract with lean
stage files and one manifest flag name (#600), and the w3 re-check findings
(#591): one helper call for the package rename and the in-file rewrite, and
the manifest backup as a file in the run folder.

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
import re
import subprocess
import sys
import tomllib
from pathlib import Path

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
    for rel, helpers in ((SELECT, ("{manifestOpsHelper}", "{skillInventoryHelper}", "{renameNameValidator}",
                                   "{runLockHelper}")),
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
    assert ("bind from it `renamed_versions`, `files_rewritten`, `rewrite_counts` ← `counts`, `package_warnings` "
            "and `missing_files`") in write


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
    assert "all four stay bound for the rest of the run" in start
    # §1 is the only place select.md resolves a helper.
    after = select[select.index("### 2. Read Export Manifest"):]
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
    for helper in ("{manifestOpsHelper}", "{skillInventoryHelper}", "{renameNameValidator}", "{runLockHelper}",
                   "{emitEnvelopeHelper}"):
        calls = re.findall(rf"^\s*(\S+(?: \S+)?) {re.escape(helper)} ", body, re.M)
        assert calls and set(calls) == {"uv run"}, (helper, calls)


def test_each_helper_call_that_prints_no_json_halts_with_its_phase():
    select = _read(SELECT)
    for start, end, phase in (("### 2. Read Export Manifest", "### 3. ", "select:read-manifest"),
                              ("### 3. List Available Skills", "### 4. ", "select:list-skills"),
                              ("### 5. Ask for New Name", "### 6. ", "select:validate-new-name"),
                              ("### 7. Enumerate Affected Versions", "### 8. ", "select:affected-versions")):
        section = _section(select, start, end)
        halts = [line for line in section.splitlines() if "no json" in line.lower() and "HALT (exit code 4" in line]
        assert halts, start
        assert all(f'`halt_reason: "write-failed"`, `emit-halt` phase `{phase}`' in line for line in halts), start
    row = next(line for line in _read(EXIT_CODES).splitlines() if line.startswith("| 4 "))
    assert "the run-lock, envelope, manifest or inventory helper is missing" in row
    assert "step 1 §2, §3, §5 and §7" in row


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
    assert "in your team or personal customization of skf-rename-skill" in halt
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
    comment = _section(toml, "# --- Optional safety scalar ---", "force_source_authority_in_headless =")
    assert FLAG in comment and "standing approval" in comment and "TOML boolean" in comment
    binding = next(line for line in _read(SKILL).splitlines() if "`{forceSourceAuthorityInHeadless}` ←" in line)
    assert 'is `"true"` or the TOML boolean `true`' in binding, "a TOML bool true must not halt"


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
    hook = _section(toml, "# Optional post-completion hook", "on_complete =")
    for needle in ("a shell command, run from {project-root}", "report step 3",
                   "--result-path=<the per-run result file the shared", "skipped when the emitter wrote no result",
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
    assert "an entry prefixed `!` drops each earlier entry it names and loads nothing itself" in activation
    assert f"`{drop}` turns that default off" in activation


def test_the_manifest_backup_is_a_file_in_the_run_folder():
    """w3 determinism-2: the backup is copied, never held in context, and the restore reads it back."""
    manifest = _section(_read(EXECUTE), "### 6. Update Export Manifest", "### 7. ")
    assert 'cp "{skills_output_folder}/.export-manifest.json" "{run_dir}/export-manifest.backup.json"' in manifest
    assert ('uv run {atomicWriteHelper} write --target "{skills_output_folder}/.export-manifest.json" '
            '< "{run_dir}/export-manifest.backup.json"') in manifest
    for stale in ("manifest_backup", "hold its exact text", "SKF_MANIFEST_BACKUP", "Read the manifest again"):
        assert stale not in manifest, stale
    for call in ("uv run {manifestOpsHelper} {skills_output_folder} get {new_name}",
                 "uv run {manifestOpsHelper} {skills_output_folder} get {old_name}"):
        assert call in manifest, call
    report = _read(REPORT)
    assert '"{run_dir}/rename-rewrite.json" "{run_dir}/export-manifest.backup.json" && rmdir "{run_dir}"' in report


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
