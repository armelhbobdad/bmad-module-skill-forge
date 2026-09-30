#!/usr/bin/env python3
"""Prose pins: refine-architecture applies its document scope in every step.

Step 2 (gap analysis) section 2b builds the in-scope and out-of-scope skill
sets and lists the technologies the architecture names that no skill covers.
These tests keep the step files on that contract:

- section 2b names Step 03 and Step 04 as consumers of the scope sets and
  Step 05 as the consumer of `{unverified_technologies}`;
- a derived scope that leaves skills out is confirmed once, before section 4
  loads the API surfaces: the gate's default is a listed option, a headless
  run keeps the derived sets and logs the decision, the cancel tokens halt
  with exit 6 ahead of the edit branch, and a `--scope-skills` scope or the
  safe default shows no gate;
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
- every state block compile reads back is one an analysis step writes.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RA = REPO_ROOT / "src" / "skf-refine-architecture"
REFS = RA / "references"
SKILL = RA / "SKILL.md"
GAP = REFS / "gap-analysis.md"
ISSUES = REFS / "issue-detection.md"
IMPROVEMENTS = REFS / "improvements.md"
COMPILE = REFS / "compile.md"
REPORT = REFS / "report.md"

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


def test_scope_gate_shows_only_for_a_derived_scope_that_leaves_skills_out():
    gate = _scope_gate()
    condition = gate.splitlines()[0]
    assert "derived (no `{scope_skills}`)" in condition
    assert "`{out_of_scope_skills}` is not empty" in condition
    assert "`--scope-skills`" in condition and "safe default" in condition, (
        "the gate must say that a --scope-skills scope and the safe default skip it"
    )


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
    assert "match no inventory skill" in rule
    assert "Programming languages, protocols and data formats do not count" in rule
    assert "deprecated, removed or being replaced" in rule
    assert "in order of first mention" in rule
    assert "`--scope-skills` and the edits above leave it unchanged" in rule


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
    assert "Examine pairs of in-scope skills (both skills in `{in_scope_skills}`)" in synergies
    assert "A pair with an out-of-scope skill is out of scope" in synergies
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
    assert "`stepsCompleted` does not include `coverage`" in rule, (
        "a VS run that stopped before its coverage step leaves coveragePercentage: 0, which must not read as 0%"
    )
    assert "{vs_report_path}" not in rows[VS_COVERAGE][2], "the refined document is shared: no local path"
    assert "`{vs_report_name}`" in rows[VS_COVERAGE][2]
    assert "`{vs_report_name}` is the file name of `{vs_report_path}`" in rule


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
    for path in (GAP, ISSUES, IMPROVEMENTS):
        written |= set(STATE_BLOCK_RE.findall(_read(path)))
    read_back = set(STATE_BLOCK_RE.findall(_compile_base()))
    assert {"[RA-GAPS]", "[RA-ISSUES]", "[RA-IMPROVEMENTS]", "[RA-SCOPE]"} <= read_back
    assert read_back <= written, f"compile reads blocks no step writes: {sorted(read_back - written)}"
    assert "[RA-OUT-OF-SCOPE]" not in read_back, "out-of-scope records never enter the refined document"
    for path in (GAP, ISSUES, IMPROVEMENTS):
        assert "`<!-- [RA-OUT-OF-SCOPE] ... -->` marker" in _read(path), f"{path.name} must record out-of-scope findings"
