#!/usr/bin/env python3
"""Prose pins: refine-architecture applies its document scope in every step.

Step 2 (gap analysis) section 2b builds the in-scope and out-of-scope skill
sets and lists the technologies the architecture names that no skill covers.
These tests keep the step files on that contract:

- section 2b names Step 03 and Step 04 as consumers of the scope sets and
  Step 05 as the consumer of `{unverified_technologies}`;
- a derived scope that leaves skills out or keeps an ambiguous one (a skill
  named only through a common-word alias) is confirmed once, before section
  4 loads the API surfaces: the gate's default is a listed option, the Why
  column and a headless run's log name the term that named each skill, the
  cancel tokens halt with exit 6 ahead of the edit branch, and a
  `--scope-skills` scope or the safe default shows no gate;
- a technology counts as covered as the mentions helper matches a skill;
- section 6 names the technologies with no skill and appends the
  `[RA-SCOPE]` block that steps 4 and 5 read back;
- improvements sections 3 and 4 compare in-scope skills and in-scope pairs
  only, and anything that involves an out-of-scope skill goes under
  `[RA-OUT-OF-SCOPE]`, never `[RA-IMPROVEMENTS]`;
- compile inserts only in-scope improvements, recovers `[RA-SCOPE]`, and
  writes the "Not verified (no skill)" row, the VS Coverage row (only with a
  VS report, `not recorded` when that run never reached its coverage step,
  and naming the report by file name only) and a [CS] or [QS] next step;
- the report parses the same rows, shows them and points to [CS] or [QS]
  before [SS];
- SKILL.md lists the gate in the Stages table and the Gates row, says in the
  Flags and Headless rows that `--scope-skills` skips it, and names it in the
  exit 6 row;
- every state block compile reads back is one a step writes.

It also pins how the steps read the [VS] feasibility report and the scope
through the shared helpers (#590, #598):

- init runs skf-validate-feasibility-report.py `--locate` before its prompt
  and offers the report it finds as the default, reads a given report path
  through the same helper's path mode, halts `input-invalid` on a report
  that breaks the contract, caches the helper's JSON as the only source for
  the report, and records it in the `[RA-VS]` state block; the input flags
  apply in every mode, and `--vs-report-path none` refines without a report;
- issue detection reads the verdicts from that JSON, matches the tokens
  exactly, keys the Plausible rule on the token, and scopes the verdicts by
  the pair lists; a lost JSON is read again through the helper, and a report
  [VS] rewrote meanwhile halts with exit 8;
- gap analysis runs skf-comention-pairs.py `mentions` once (documented-pair
  candidates, the Mermaid note, the derived scope), splits the pairs once
  with skf-enumerate-stack-skills.py `scope` (naming a `--scope-skills`
  name that is no inventory skill), and reads `language` from the inventory;
- compile fills the VS Coverage row from the JSON's `coverageMeasured`;
- the helper calls fit the helpers' CLIs and quote every placeholder they
  pass, and every key the steps read is one the feasibility helper emits.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RA = REPO_ROOT / "src" / "skf-refine-architecture"
REFS = RA / "references"
SKILL = RA / "SKILL.md"
INIT = REFS / "init.md"
GAP = REFS / "gap-analysis.md"
ISSUES = REFS / "issue-detection.md"
IMPROVEMENTS = REFS / "improvements.md"
COMPILE = REFS / "compile.md"
REPORT = REFS / "report.md"
RULES = REFS / "refinement-rules.md"
FEASIBILITY_HELPER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-validate-feasibility-report.py"
COMENTION_HELPER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-comention-pairs.py"

NOT_VERIFIED = "Not verified (no skill)"
VS_COVERAGE = "VS Coverage"
STATE_BLOCK_RE = re.compile(r"<!-- (\[RA-[A-Z-]+\])")
OPTION_RE = re.compile(r"\[([A-Z])\]")
GATE_DEFAULT_RE = re.compile(r"GATE \[default: ([A-Z])\]")


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


def _gap_scope() -> str:
    return _slice(_read(GAP), "### 2b. Establish Document Scope", "### 3.")


def _scope_gate() -> str:
    return _slice(_gap_scope(), "**Confirm a derived scope.**", "**Technologies with no skill.**")


def _unverified_rule() -> str:
    return _slice(_gap_scope(), "**Technologies with no skill.**", "Store `{in_scope_skills}`")


def _gap_report() -> str:
    return _slice(_read(GAP), "### 6. Report Gaps & Store Findings", "### 7.")


def _improvements_compare() -> str:
    return _slice(_read(IMPROVEMENTS), "### 3. Compare Skill API Surfaces", "### 4.")


def _improvements_synergies() -> str:
    return _slice(_read(IMPROVEMENTS), "### 4. Detect Cross-Library Synergies", "### 5.")


def _improvements_store() -> str:
    return _slice(_read(IMPROVEMENTS), "### 6. Report Improvements & Store Findings", "### 7.")


def _compile_base() -> str:
    return _slice(_read(COMPILE), "### 1. Prepare the Original as Base", "### 2.")


def _compile_improvements() -> str:
    return _slice(_read(COMPILE), "### 4. Insert Improvement Suggestions", "### 5.")


def _compile_summary() -> str:
    return _slice(_read(COMPILE), "### 5. Add Refinement Summary Section", "### 6.")


def _report_parse() -> str:
    return _slice(_read(REPORT), "### 1. Load Refined Document", "### 2.")


def _report_summary() -> str:
    return _slice(_read(REPORT), "### 2. Display Summary", "### 3.")


def _report_next_steps() -> str:
    return _slice(_read(REPORT), "### 3. Present Next Steps", "### 4.")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "expected YAML frontmatter"
    return text.split("\n---\n", 1)[0]


def _init_inputs() -> str:
    return _slice(_read(INIT), "### 1. Accept Input Documents", "### 2.")


def _issue_vs() -> str:
    return _slice(_read(ISSUES), "### 4. Incorporate VS Report", "### 5.")


def _gap_claims() -> str:
    return _slice(_read(GAP), "### 2. Extract Integration Claims from Architecture", "### 2b.")


def _gap_split() -> str:
    return _slice(_read(GAP), "### 3. Split the Library Pairs by Scope", "### 4.")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feasibility_helper():
    return _load("ra_scope_feasibility_helper", FEASIBILITY_HELPER)


def _comention_helper():
    return _load("ra_scope_comention_helper", COMENTION_HELPER)


def _table_rows(text: str) -> dict[str, list[str]]:
    """First cell (bold markers stripped) -> all cells, for each table row."""
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.startswith("|") or set(line) <= {"|", "-", " "}:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows[cells[0].strip("*")] = cells
    return rows


def _bullet(text: str, lead: str) -> str:
    """The one bullet line of `text` that starts with `- {lead}`."""
    lines = [line for line in text.splitlines() if line.startswith(f"- {lead}")]
    assert len(lines) == 1, f"expected one bullet starting {lead!r}, found {len(lines)}"
    return lines[0]


# --- Step 2: scope sets and their consumers ---


def test_scope_sets_name_every_consumer():
    store = _slice(_gap_scope(), "Store `{in_scope_skills}`", "\n\n")
    assert "`{unverified_technologies}`" in store
    assert "Step 03 (issue detection)" in store
    assert "Step 04 (improvements)" in store
    assert "Step 05 (compile)" in store
    assert "Step 03 (issue detection) reuses them." not in _read(GAP), (
        "the old sentence named Step 03 as the only consumer"
    )


def test_scope_gate_shows_only_for_a_derived_scope_to_confirm():
    gate = _scope_gate()
    condition = gate.splitlines()[0]
    assert "derived (no `{scope_skills}`)" in condition
    assert "`{out_of_scope_skills}` is not empty or an in-scope skill is ambiguous" in condition
    assert "`--scope-skills`" in condition and "safe default" in condition, (
        "the gate must say that a --scope-skills scope and the safe default skip it"
    )


def test_a_common_word_alias_makes_a_skill_ambiguous():
    # A repository or folder basename such as `core` or `ai` is an alias, so
    # "core services" names a skill built from vuejs/core: the gate lists it.
    derive = _bullet(_gap_scope(), "**Otherwise derive:**")
    assert "names only through a repository or folder alias that is also a common word" in derive
    assert "the confirmation below lists it as ambiguous, not as named" in derive
    [in_scope] = [row for row in _scope_gate().splitlines() if row.startswith("| {skill} | In scope |")]
    assert "named as `{term}` in {paragraph_count} paragraph(s)" in in_scope
    assert "named only as the common word `{term}`" in in_scope
    assert "`{term}` is the skill's name or the alias that names it" in _scope_gate().splitlines()[0]


def test_scope_gate_runs_after_the_split_and_before_the_api_surfaces_load():
    text = _read(GAP)
    split = text.index("`{out_of_scope_skills}` = inventory skills not in `{in_scope_skills}`")
    safe_default = text.index("**Safe default:**")
    gate = text.index("**Confirm a derived scope.**")
    surfaces = text.index("### 4. Load Skill API Surfaces")
    assert split < safe_default < gate < surfaces
    assert "before §4 loads the API surfaces" in _scope_gate()


def test_scope_gate_default_is_a_listed_option():
    gate = _scope_gate()
    select = [line for line in gate.splitlines() if "**Select:**" in line]
    assert len(select) == 1, "the gate needs exactly one Select line"
    options = OPTION_RE.findall(select[0])
    assert options == ["C", "X"], f"unexpected menu options: {options}"
    defaults = GATE_DEFAULT_RE.findall(gate)
    assert defaults == ["C"], f"expected one GATE [default: C], found {defaults}"
    assert defaults[0] in options


def test_scope_gate_headless_keeps_the_derived_sets_and_logs_them():
    gate_line = [line for line in _scope_gate().splitlines() if "GATE [default: C]" in line][0]
    assert "wait for the user's choice" in gate_line
    assert "If `{headless_mode}`: keep the derived sets and auto-proceed with [C]" in gate_line
    log = re.search(r'log: "(headless: [^"]+)"', gate_line)
    assert log, "the headless default must log its decision"
    assert log.group(1).startswith("headless: auto-confirm derived document scope")
    assert "{in_scope_skills}" in log.group(1) and "{out_of_scope_skills}" in log.group(1)
    assert "giving each in-scope skill its Why from the table" in gate_line, "the log shows each match"


def test_scope_gate_cancel_halts_before_the_edit_branch():
    gate = _scope_gate()
    branches = [line for line in gate.splitlines() if line.startswith("- IF ")]
    leads = ("- IF C:", "- IF cancel / exit / [X] / q / :q:", "- IF the input names skills:", "- IF anything else:")
    assert len(branches) == len(leads), branches
    for branch, lead in zip(branches, leads):
        assert branch.startswith(lead), f"expected a branch starting {lead!r} here, found {branch!r}"
    cancel = branches[1]
    assert "exit code 6" in cancel and '`halt_reason: "user-cancelled"`' in cancel
    assert "pre-empt the edit branch" in cancel


def test_scope_gate_edits_move_skills_between_the_sets():
    edit = _bullet(_scope_gate(), "IF the input names skills")
    assert "into `{in_scope_skills}`" in edit
    assert "`-skill_name` moves it out" in edit
    assert "recompute `{out_of_scope_skills}`" in edit
    assert "not an inventory skill" in edit
    assert "refuse an edit that would leave `{in_scope_skills}` empty" in edit
    assert "redisplay the table and the menu" in edit


def test_unverified_technologies_rule():
    rule = _unverified_rule()
    assert "`{unverified_technologies}` = " in rule
    assert "that no inventory skill covers" in rule
    assert "Programming languages, protocols and data formats do not count" in rule
    assert "deprecated, removed or being replaced" in rule
    assert "in order of first mention" in rule
    assert "`--scope-skills` and the edits above leave it unchanged" in rule


def test_a_technology_is_covered_as_the_mentions_helper_matches():
    # Exact equality put `Next.js` under "Not verified (no skill)" while the
    # mentions helper put a `next` skill in scope from the same words.
    rule = _unverified_rule()
    assert "is the technology's name, compared case-insensitively" not in rule
    assert "when §2's matching rule (case-insensitive, at word boundaries, each occurrence read" in rule
    assert "inside the technology's name as the document writes it, so a `next` skill covers `Next.js`" in rule
    assert "equals that name once case, spaces, hyphens, dots and underscores are ignored" in rule
    # The examples hold for the helper: its matcher finds `next` in Next.js,
    # while React Router and Tailwind CSS need the second rule.
    helper = _comention_helper()
    for text, skill, named in (("Next.js", "next", True), ("React Router", "react-router", False),
                               ("Tailwind CSS", "tailwindcss", False)):
        skills = helper.parse_skills(f'[{{"name": "{skill}"}}]')
        assert (helper.mentions(f"We use {text}.\n", skills)["mentioned"] == [skill]) is named, text
        assert f"`{skill}` skill covers `{text}`" in rule


def test_gap_report_names_unverified_technologies_and_stores_the_scope():
    report = _gap_report()
    assert "Three signals are not inferable" in report
    signal = _bullet(report, "**The architecture names technologies with no skill")
    assert "`{unverified_technologies}`" in signal
    assert "[CS] or [QS]" in signal and "re-running [RA]" in signal
    block = _slice(report, "Append the scope under a `<!-- [RA-SCOPE] ... -->` block", "\n\n")
    for field in ("`{in_scope_skills}`", "`{out_of_scope_skills}`", "`{unverified_technologies}`"):
        assert field in block, f"the [RA-SCOPE] block must record {field}"
    assert "how the scope was set" in block
    assert "Step 04 and Step 05 read the block back" in block


# --- Step 4: improvements stay inside the scope ---


def test_improvements_compare_in_scope_skills_only():
    compare = _improvements_compare()
    assert "For each skill in `{in_scope_skills}`:" in compare
    assert "For each skill in the inventory" not in compare
    routing = _slice(compare, "**Scope routing (from Step 02 §2b):**", "\n\n")
    assert "`{out_of_scope_skills}`" in routing
    assert "`[RA-SCOPE]` block" in routing, "step 4 must recover the sets after a context loss"
    assert "**Out-of-Scope** bucket" in routing


def test_improvements_examine_in_scope_pairs_only():
    synergies = _improvements_synergies()
    assert "Examine the pairs in `{in_scope_pairs}`" in synergies
    assert "both in `{in_scope_skills}`" in synergies
    assert "A pair in `{out_of_scope_pairs}` is out of scope" in synergies
    assert "skip it" in synergies
    assert "Examine pairs of skills for" not in synergies


def test_improvements_store_out_of_scope_findings_apart():
    store = _improvements_store()
    assert "Report the in-scope improvement count" in store
    signal = _bullet(store, "**Out-of-scope improvements or synergies were set aside")
    assert "`--scope-skills`" in signal
    assert "Store the **in-scope** improvement findings" in store
    assert "`<!-- [RA-IMPROVEMENTS] ... -->`" in store
    assert "under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker" in store


# --- Step 5: compile and the Refinement Summary ---


def test_compile_inserts_only_in_scope_improvements():
    first = _compile_improvements().split("\n\n")[1]
    assert first.startswith("For each in-scope improvement finding from Step 04")
    assert "`[RA-IMPROVEMENTS]`" in first
    assert "`[RA-OUT-OF-SCOPE]` and never enter the refined document" in first


def test_compile_recovers_the_scope_block():
    recovery = _slice(_compile_base(), "**Scope recovery:**", "\n\n")
    assert "`{unverified_technologies}`" in recovery
    assert "`<!-- [RA-SCOPE] -->`" in recovery
    assert "exit code 8" in recovery and '`halt_reason: "recovery-failed"`' in recovery


def test_refinement_summary_rows():
    summary = _compile_summary()
    rows = _table_rows(summary)
    labels = list(rows)
    assert labels[-3:] == ["Skills Used as Evidence", NOT_VERIFIED, VS_COVERAGE], labels
    assert rows[NOT_VERIFIED][1:] == ["{unverified_count}", "{unverified_technologies}"]
    assert rows[VS_COVERAGE][1] == "{vs_coverage}"
    rule = _slice(summary, f"The {NOT_VERIFIED} row is always written", "\n\n")
    assert "reads `none`" in rule
    assert "only when a VS report was used (`vs_report_available` is true)" in rule
    assert "`coveragePercentage`" in rule and "`not recorded`" in rule
    # The helper decides whether coverage was measured: a VS run that stopped
    # before its coverage step leaves coveragePercentage: 0, which must not read as 0%.
    assert "from the report JSON Step 01 §1 cached (`{vs_report}`), never from the report file" in rule
    assert "followed by `%` when its `coverageMeasured` is true" in rule
    assert "`not recorded` when `coverageMeasured` is false" in rule
    assert "frontmatter" not in rule, "the row is filled from the helper's JSON, not the report's frontmatter"
    assert "{vs_report_path}" not in rows[VS_COVERAGE][2], "the refined document is shared: no local path"
    assert "`{vs_report_name}`" in rows[VS_COVERAGE][2]
    assert "`{vs_report_name}` is the file name of the JSON's `path`" in rule


def test_refinement_summary_next_step_points_to_cs_or_qs():
    next_steps = _bullet(_compile_summary(), "**Next Steps:**")
    assert "When `{unverified_technologies}` is not empty, add one line before [SS]" in next_steps
    assert "**[CS] Create Skill** or **[QS] Quick Skill**" in next_steps
    assert "re-run **[RA]**" in next_steps


# --- Step 6: the report carries the same rows and next step ---


def test_report_parses_the_new_rows():
    parse = _slice(_report_parse(), "**Extract metrics from the Refinement Summary section:**", "\n\n")
    assert f"from the Count and Breakdown cells of the table's {NOT_VERIFIED} row" in parse
    assert "`unverified_count`" in parse and "`unverified_technologies`" in parse
    assert f"`vs_coverage` from the Count cell of its {VS_COVERAGE} row" in parse
    assert f"leave the {VS_COVERAGE} row out of the summary below" in parse


def test_report_shows_the_new_rows():
    rows = _table_rows(_report_summary())
    assert rows[NOT_VERIFIED][1] == "{unverified_count} ({unverified_technologies})"
    assert rows[VS_COVERAGE][1] == "{vs_coverage}"


def test_row_labels_match_between_compile_and_report():
    compiled = set(_table_rows(_compile_summary()))
    shown = set(_table_rows(_report_summary()))
    assert {NOT_VERIFIED, VS_COVERAGE} <= compiled & shown


def test_report_next_steps_point_to_cs_or_qs_before_ss():
    next_steps = _report_next_steps()
    condition = next_steps.index("{IF unverified_count > 0:}")
    stack_skill = next_steps.index("2. **[SS] Stack Skill**")
    assert condition < stack_skill, "the [CS]/[QS] line must come before the [SS] step"
    block = _slice(next_steps, "{IF unverified_count > 0:}", "\n\n")
    assert "{unverified_technologies}" in block
    assert "**[CS] Create Skill** or **[QS] Quick Skill**" in block
    assert "before moving on to **[SS] Stack Skill**" in block


# --- SKILL.md and the state blocks ---


def test_skill_md_lists_the_scope_gate():
    text = _read(SKILL)
    stages = _slice(text, "## Stages", "## Invocation Contract")
    step_2 = [line for line in stages.splitlines() if line.startswith("| 2 |")]
    assert step_2 == ["| 2 | Gap Analysis | references/gap-analysis.md | Conditional (confirm a derived scope) |"]
    gates = [line for line in text.splitlines() if line.startswith("| **Gates** |")]
    assert len(gates) == 1 and "step 2: Scope Confirm Gate [C] continue / [X] cancel" in gates[0]
    flags = [line for line in text.splitlines() if line.startswith("| **Flags** |")]
    assert len(flags) == 1 and "so step 2 asks no scope confirmation" in flags[0]
    headless = [line for line in text.splitlines() if line.startswith("| **Headless** |")]
    assert len(headless) == 1 and "`--scope-skills` skips the step 2 scope confirmation" in headless[0]
    exit_codes = _slice(text, "## Exit Codes", "## Result Contract")
    exit_6 = [line for line in exit_codes.splitlines() if line.startswith("| 6 ")]
    assert len(exit_6) == 1 and "step 2 §2b scope confirmation `[X]`" in exit_6[0]


def test_every_state_block_compile_reads_is_written_by_a_step():
    written = set()
    for path in (INIT, GAP, ISSUES, IMPROVEMENTS):
        written |= set(STATE_BLOCK_RE.findall(_read(path)))
    read_back = set(STATE_BLOCK_RE.findall(_compile_base()))
    assert {"[RA-GAPS]", "[RA-ISSUES]", "[RA-IMPROVEMENTS]", "[RA-SCOPE]", "[RA-VS]"} <= read_back
    assert read_back <= written, f"compile reads blocks no step writes: {sorted(read_back - written)}"
    assert "[RA-OUT-OF-SCOPE]" not in read_back, "out-of-scope records never enter the refined document"
    for path in (GAP, ISSUES, IMPROVEMENTS):
        assert "`<!-- [RA-OUT-OF-SCOPE] ... -->` marker" in _read(path), f"{path.name} must record out-of-scope findings"


# --- Step 1: the [VS] report through the feasibility helper (#590) ---


def test_init_binds_the_feasibility_helper():
    frontmatter = _frontmatter(_read(INIT))
    installed = "'{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'"
    dev = "'{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'"
    assert "validateFeasibilityReportProbeOrder:" in frontmatter
    assert installed in frontmatter and dev in frontmatter
    assert frontmatter.index(installed) < frontmatter.index(dev), "installed path first"


def test_no_step_builds_the_report_file_name_or_parses_the_report():
    for path in sorted(RA.rglob("*.md")):
        text = _read(path)
        assert "feasibility-report-{" not in text, f"{path.name} builds the report file name"
        assert "Auto-Probe VS Report" not in text, path.name
        assert "Parse the `## Integration Verdicts`" not in text, path.name
        assert "Load the VS feasibility report" not in text, path.name


def test_the_probe_runs_before_the_prompt():
    inputs = _init_inputs()
    probe = inputs.index(
        'uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"'
    )
    prompt = inputs.index('"**Refine Architecture: Evidence-Backed Refinement**')
    assert probe < prompt
    assert "Unless `--vs-report-path` was passed, run the probe before asking anything" in inputs
    assert "Found the [VS] report from {vs_report_date}: press Enter to use it, or give another path." in inputs
    assert "`{vs_report_date}` is the date in the probe's `generatedAt`" in inputs


def test_the_input_flags_apply_in_every_mode():
    inputs = _init_inputs()
    first = inputs.split("\n\n")[1]
    assert first.startswith("`--architecture-doc <path>` and `--vs-report-path <path>` apply in every mode")
    assert "in an interactive run as in headless" in first
    assert "Ask only for what no flag answered" in inputs
    assert "consume it at the VS validation below" not in inputs


def test_vs_report_path_none_refines_without_a_report():
    # A found -latest report would otherwise be used in headless, and a broken
    # one halts before the prompt: `none` is the way to skip it in any mode.
    inputs = _init_inputs()
    skip = _slice(inputs, "**Refine without a report.**", "\n\n")
    assert "`--vs-report-path none` answers the report question as typing `none` at the prompt does" in skip
    assert "in every mode: skip the probe and the path mode below, use no report" in skip
    assert '"VS report skipped (--vs-report-path none)."' in skip
    assert inputs.index("**Refine without a report.**") < inputs.index("**Find the [VS] report first.**")
    record = _slice(inputs, "**Record the VS report.**", "\n\n")
    assert "`none` was typed or passed with `--vs-report-path`" in record
    [flags] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Flags** |")]
    assert "`--vs-report-path none` refines without a report and skips the search for one" in flags


def test_headless_uses_the_report_it_finds_and_logs_it():
    [gate] = [line for line in _init_inputs().splitlines() if line.startswith("Wait for user input.")]
    assert "**GATE [default: use args]:**" in gate
    assert 'headless takes it and logs "headless: using the [VS] report found at {path}"' in gate
    assert '"headless: no [VS] report for {project_name}; issue detection will use skill data only"' in gate


def test_a_given_report_path_goes_through_the_path_mode():
    inputs = _init_inputs()
    path_mode = _slice(inputs, "**Read a report path.**", "\n\n**Unusable VS report.**")
    assert 'uv run {validateFeasibilityReportHelper} "{vs_report_path}"' in path_mode
    assert "exactly as `--locate` does and prints the same JSON" in path_mode
    assert "- **1:** HALT as **Unusable VS report** says below." in path_mode
    retry = _bullet(path_mode, "**2**")
    assert retry.startswith("- **2** with a JSON (the file is missing or could not be read")
    assert "run the probe above if it has not run, and ask the report question again" in retry
    assert "run the probe above and take its outcome as if `--vs-report-path` had not been passed" in retry
    assert "- **2 with no JSON:** a malformed call, as for the probe: fix it and run it again." in path_mode


def test_an_unusable_report_halts_input_invalid():
    inputs = _init_inputs()
    probe = _slice(inputs, "Branch on its exit code:", "\n\n**Read a report path.**")
    assert "- **1** (the report breaks the contract) **or 2** with a JSON" in probe
    assert "HALT as **Unusable VS report** says below" in _bullet(probe, "**1**")
    # argparse's own exit 2 (an unquoted path with a space, say) prints no
    # JSON and says nothing about the report: it must not halt input-invalid.
    malformed = _bullet(probe, "**2 with no JSON**")
    assert "argparse refused the call itself" in malformed and "fix the call and run it again" in malformed
    assert "HALT" not in malformed
    halt = _slice(inputs, "**Unusable VS report.**", "\n\n")
    assert 'HALT (exit code 2, `halt_reason: "input-invalid"`)' in halt
    assert "never interpreted" in halt
    for key in ("`schemaVersionOk`", "`missingHeadings`", "`orderViolations`", "`verdictTableFound`",
                "`duplicateVerdictTableLine`", "`unknownTokens`", "`error`"):
        assert key in halt, key
    assert ("Re-run [VS] to write a current report, pass another one with `--vs-report-path <path>`, "
            "or refine without one with `--vs-report-path none`.") in halt


def test_the_helper_json_is_the_only_report_source():
    record = _slice(_init_inputs(), "**Record the VS report.**", "\n\n")
    assert "Cache the JSON of the report this run uses as `{vs_report}`" in record
    assert "the run's only source for the report" in record
    assert "`vs_report_available` to true when there is one (its `status` is `ok`)" in record
    unavailable = _slice(_init_inputs(), "If `{validateFeasibilityReportHelper}` has no existing candidate", "\n\n")
    assert "no report is read" in unavailable
    assert "Neither the report's file name nor its verdict table is ever worked out by hand." in unavailable


def test_the_state_file_records_the_vs_report():
    reset = _slice(_read(INIT), "### 3c. Reset RA State File", "### 4.")
    block = _slice(reset, "Then append a `<!-- [RA-VS] ... -->` block", "\n\n")
    for needle in ("`path`", "`generatedAt`", "`coveragePercentage`", "`coverageMeasured`", "`none`"):
        assert needle in block, needle
    assert "Step 03 reads the report again from that `path` and checks its `generatedAt`" in block


def test_feasibility_helper_calls_fit_its_cli():
    # The helper has no subcommands, so the repo-wide helper-call contract test
    # skips it: parse each call here with the helper's own parser.
    helper = _feasibility_helper()
    pattern = r"^uv run \{validateFeasibilityReportHelper\} (.+)$"
    calls = re.findall(pattern, _read(INIT) + _read(ISSUES), re.M)
    assert len(calls) == 3, calls
    for call in calls:
        argv = [re.sub(r"\{[^{}]*\}", "value", word) for word in shlex.split(call)]
        helper._build_parser().parse_args(argv)


HELPER_CALL_RE = re.compile(r"^uv run \{[A-Za-z]+Helper\} (.+)$", re.M)


def test_helper_calls_quote_every_placeholder():
    # An unquoted path that holds a space becomes two arguments: argparse
    # exits 2 with no JSON, which step 1 would read as an unusable report.
    calls = [call for path in sorted(REFS.glob("*.md")) for call in HELPER_CALL_RE.findall(_read(path))]
    assert len(calls) >= 6, calls
    for call in calls:
        assert "{" not in re.sub(r'"[^"]*"', "", call), f"quote each placeholder of: {call}"


# The report JSON keys the steps name; each must be one the helper emits.
REPORT_KEYS = ("status", "path", "generatedAt", "schemaVersionOk", "missingHeadings", "orderViolations",
               "verdictTableFound", "duplicateVerdictTableLine", "unknownTokens", "pairVerdicts",
               "overallVerdict", "coveragePercentage", "coverageMeasured")


def test_the_report_keys_the_steps_read_are_the_helpers(tmp_path):
    helper = _feasibility_helper()
    located, _ = helper.locate_report(str(tmp_path), "Demo")
    report = tmp_path / "report.md"
    report.write_text("# Not a feasibility report\n", encoding="utf-8")
    validated, _ = helper.validate_report(str(report))
    prose = _init_inputs() + _issue_vs() + _compile_summary() + _compile_base()
    for key in REPORT_KEYS:
        assert f"`{key}`" in prose, key
        assert key in located and key in validated, key


# --- Step 3: VS verdicts by their token, scoped by the pair lists ---


def test_issue_detection_reads_the_cached_json():
    vs = _issue_vs()
    read = _slice(vs, "**Read the verdicts from `{vs_report}`**", "\n\n")
    assert "`pairVerdicts`" in read and "`unknownTokens`" in read
    assert "never read the report file by hand" in read
    assert "compare it exactly as written (tokens are case-sensitive)" in read
    assert "(match case-insensitively)" not in vs


def test_issue_detection_reads_a_lost_report_again_or_halts():
    # A lost JSON is read again through the helper this step binds, and the
    # re-read must be the report the run started from.
    assert "validateFeasibilityReportProbeOrder:" in _frontmatter(_read(ISSUES))
    recover = _slice(_issue_vs(), "**Recover the report JSON.**", "**Scope filter")
    assert "the `[RA-VS]` block" in recover
    assert "resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`" in recover
    assert 'uv run {validateFeasibilityReportHelper} "{vs_report_path}"' in recover
    assert "exits 0 with the `generatedAt` the block records" in recover
    assert "When it exits non-zero with a JSON, or its `generatedAt` differs" in recover
    assert 'HALT (exit code 8, `halt_reason: "recovery-failed"`)' in recover
    assert "An exit 2 with no JSON is a malformed call, as in Step 01: fix it and run it again." in recover
    assert "the same helper gives the same JSON" not in _read(ISSUES)


def test_verdicts_are_promoted_by_their_exact_token():
    promote = _slice(_issue_vs(), "**Promote the in-scope verdicts by their token:**", "\n\n")
    leads = [line.split(":**")[0] for line in promote.splitlines() if line.startswith("- ")]
    assert leads == ["- **`Risky`", "- **`Blocked`", "- **`Plausible`", "- **`Verified`"]
    assert "never phrases in the rationale text" in _bullet(promote, "**`Plausible`")


RATIONALE_PHRASES = ("no direct API evidence", "weak evidence")


def test_the_plausible_rule_keys_on_the_token():
    for path in (ISSUES, RULES):
        for phrase in RATIONALE_PHRASES:
            assert phrase not in _read(path), f"{path.name} still keys on the rationale phrase {phrase!r}"
    rules = _slice(_read(RULES), "### VS Report Integration", "---")
    assert "each rule keys on the token alone" in rules
    assert "- `Plausible` verdicts become **potential issues**" in rules
    assert "RISKY" not in rules and "BLOCKED" not in rules, "the tokens are case-sensitive"
    severity = _slice(_read(ISSUES), "**Severity classification:**", "\n\n")
    assert "- **Minor:** `Plausible` VS verdicts" in severity


def test_issue_detection_scopes_verdicts_by_the_pair_lists():
    scope = _slice(_issue_vs(), "**Scope filter", "\n\n")
    assert "`{in_scope_pairs}`" in scope and "`{out_of_scope_pairs}`" in scope
    assert "`[RA-SCOPE]` block" in scope
    assert "either library in `{out_of_scope_skills}`" not in scope


# --- Step 2: scope and documented pairs through the helpers (#598) ---


def test_gap_analysis_binds_its_helpers():
    frontmatter = _frontmatter(_read(GAP))
    for key, script in (("comentionProbeOrder:", "skf-comention-pairs.py"),
                        ("enumerateStackSkillsProbeOrder:", "skf-enumerate-stack-skills.py")):
        assert key in frontmatter
        installed = f"'{{project-root}}/_bmad/skf/shared/scripts/{script}'"
        dev = f"'{{project-root}}/src/shared/scripts/{script}'"
        assert frontmatter.index(installed) < frontmatter.index(dev), "installed path first"


def test_the_mentions_helper_runs_once_with_aliases():
    claims = _gap_claims()
    assert _read(GAP).count("uv run {comentionHelper} mentions") == 1
    assert 'uv run {comentionHelper} mentions --doc "{architecture_doc}" --skills -' in claims
    assert "`source_repo_basename` and `source_root_basename`" in claims
    assert "Cache its JSON as `{doc_mentions}`" in claims


def test_documented_pairs_come_from_the_candidates():
    claims = _gap_claims()
    documented = _slice(claims, "**Documented pairs.**", "\n\n")
    assert "`{doc_mentions}.candidates[]`" in documented
    assert "a lead-in one included" in documented
    assert "`unit_excerpt`" in documented and "not mere co-mention" in documented
    assert "prose-based co-mention analysis" not in claims


def test_the_mermaid_note_follows_the_fenced_blocks():
    note = _slice(_gap_claims(), "**Mermaid limitation:**", "\n\n")
    assert "`{doc_mentions}.fenced_blocks[]` has the info string `mermaid`" in note
    assert "`{doc_mentions}.fenced_only`" in note
    assert "blocks are present" not in note


def test_the_derived_scope_comes_from_the_mentions():
    scope = _gap_scope()
    derive = _bullet(scope, "**Otherwise derive:**")
    assert "`{in_scope_skills}` = `{doc_mentions}.mentioned` plus `{doc_mentions}.fenced_only`" in derive
    assert "primary technology" not in scope
    given = _bullet(scope, "**If `{scope_skills}` was provided**")
    assert "verbatim" not in given
    assert "§3 checks each name against the inventory" in given
    assert "`mentioned` and `fenced_only` are both empty" in _slice(scope, "**Safe default:**", "\n\n")


def test_scope_skills_names_are_checked_not_used_verbatim():
    hint = _slice(_init_inputs(), "**Scope hint (optional, `--scope-skills`):**", "\n\n")
    assert "authoritative in-scope skill set" not in hint
    assert "Step 02 §3 checks each against the inventory" in hint


def test_the_pairs_are_split_once_after_the_gate():
    text = _read(GAP)
    call = 'uv run {enumerateStackSkillsHelper} scope --skills "{inventory_names}" --in-scope "{in_scope_names}"'
    assert text.count("uv run {enumerateStackSkillsHelper} scope") == 1
    assert text.index("**Confirm a derived scope.**") < text.index(call) < text.index("### 4. Load Skill API Surfaces")
    split = _gap_split()
    for binding in ("`{in_scope_skills}` ← `in_scope`", "`{out_of_scope_skills}` ← `out_of_scope`",
                    "`{in_scope_pairs}` ← `in_scope_pairs`", "`{out_of_scope_pairs}` ← `out_of_scope_pairs`"):
        assert binding in split, binding
    unknown = _bullet(split, "When `unknown` is not empty")
    assert '"Not an inventory skill, left out of the scope: {unknown}."' in unknown
    assert "`pair_count` equals `skill_inventory.pair_count`" in split


def test_gap_routing_reads_the_pair_lists():
    cross = _slice(_read(GAP), "### 5. Cross-Reference: Identify Gaps", "### 6.")
    assert "For each pair in `{in_scope_pairs}` or `{out_of_scope_pairs}` (from §3)" in cross
    routing = _slice(cross, "**Scope routing (from §3):**", "\n\n")
    assert "A pair in `{out_of_scope_pairs}` does not go to the gap list" in routing
    assert "Only pairs in `{in_scope_pairs}` proceed to gap classification" in routing


def test_the_scope_block_holds_the_pair_lists():
    block = _slice(_gap_report(), "Append the scope under a `<!-- [RA-SCOPE] ... -->` block", "\n\n")
    assert "`{in_scope_pairs}`" in block and "`{out_of_scope_pairs}`" in block
    assert "Step 03, Step 04 and Step 05 read the block back" in block


def test_language_comes_from_the_inventory():
    surfaces = _slice(_read(GAP), "### 4. Load Skill API Surfaces for Cross-Reference", "### 5.")
    assert "From metadata.json (read in parent" not in surfaces
    assert "each skill's `language`" in surfaces
    assert "Do not open `metadata.json` in the parent." in surfaces


# --- Step 5 and SKILL.md ---


def test_compile_recovers_the_vs_report_block():
    recovery = _slice(_compile_base(), "**VS report recovery:**", "\n\n")
    assert "`<!-- [RA-VS] -->`" in recovery
    assert "`coverageMeasured`" in recovery and "`none`" in recovery
    assert "exit code 8" in recovery and '`halt_reason: "recovery-failed"`' in recovery


def test_skill_md_names_the_vs_report_halt():
    exit_codes = _slice(_read(SKILL), "## Exit Codes", "## Result Contract")
    [exit_2] = [line for line in exit_codes.splitlines() if line.startswith("| 2 ")]
    assert "a [VS] report that breaks the feasibility-report contract" in exit_2
    assert exit_2.rstrip(" |").endswith("→ `input-invalid`")
    [exit_8] = [line for line in exit_codes.splitlines() if line.startswith("| 8 ")]
    assert "step 3 §4 (the [VS] report cannot be read again, or [VS] rewrote it during the run)" in exit_8
    [headless] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Headless** |")]
    assert "without `--vs-report-path` step 1 uses the [VS] report it finds" in headless
