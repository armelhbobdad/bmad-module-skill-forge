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
- the mentions helper, not the prose, decides which technologies a skill
  covers, and gives the term that named each skill for the gate;
- section 6 names the technologies with no skill and appends the
  `[RA-SCOPE]` block that steps 4 and 5 read back;
- improvements sections 3 and 4 compare in-scope skills and in-scope pairs
  only, and anything that involves an out-of-scope skill goes under
  `[RA-OUT-OF-SCOPE]`, never `[RA-IMPROVEMENTS]`;
- compile inserts only in-scope improvements, recovers `[RA-SCOPE]`, and
  writes the "Not verified (no skill)" row, the VS Coverage row (only with a
  VS report, `not recorded` when that run never reached its coverage step,
  and naming the report by file name only) and a [CS] or [QS] next step;
- the report takes what it shows from the record of the draft's build
  (never from a Refinement Summary), repeats no count table (the review
  showed it, and a headless run reads the counts in its result line) and
  points to [CS] or [QS] before [SS];
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
- a missing feasibility, enumerate or mentions helper, or an enumerate or
  mentions call that fails, halts with exit 3 at its own phase (#599)
  instead of a skipped report, a hand walk or hand co-mention facts, and
  exit-codes.md names the three phases;
- issue detection joins the verdicts to the inventory and the scope with
  skf-check-preservation.py `verdicts`, which reads the report again,
  routes a row naming no skill out of scope, gives each in-scope row the
  tier its token raises (the Plausible rule keys on the token), and reports
  a report [VS] rewrote meanwhile, or rules that no longer pass step 1's
  check, which halt with exit 8;
- gap analysis runs skf-comention-pairs.py `mentions` once, on the analysis
  copy that sets an earlier RA pass aside (documented-pair candidates, the
  Mermaid note, the derived scope, the technologies no skill covers),
  splits the pairs once with skf-enumerate-stack-skills.py `scope` (naming
  a `--scope-skills` name that is no inventory skill), and reads
  `language` from the inventory;
- compile fills the VS Coverage row from the JSON's `coverageMeasured`;
- the helper calls fit the helpers' CLIs and quote every placeholder they
  pass, and every key the steps read is one the feasibility helper emits.

And it pins the split of the rules a team may swap from the ones it may not
(#596, #599, #600):

- refinement-rules.md, which `refinement_rules_path` replaces, holds only
  house style: six tables (types, severity and value tiers, the VS token
  mapping) under the headings init checks, with the bundled tiers equal to
  the preservation script's defaults; the steps classify from it and restate
  no type, tier or token mapping;
- a copy's tiers follow the rules that let the script count them, which
  init checks with the script's `rules` subcommand: each rule is run
  against the script, as a broken tier set and as a renamed one that fills
  its own counts;
- the Finding Storage contract lives in the fixed finding-storage.md, which
  steps 2 to 4 bind, and a finding an approved review dropped is recorded
  beside the output and left out of a later run on the refined document (an
  improvement only for the capability it named);
- the per-refinement walkthrough is [R] at the step 5 review gate, step 6 has
  no menu, step 4 reads the capabilities step 2 collected instead of a
  second subagent round, and the split names the skills a run left out of
  scope in an `out_of_scope_skills` warning.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

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
STORAGE = REFS / "finding-storage.md"
CUSTOMIZE = RA / "customize.toml"
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
    return _slice(_read(COMPILE), "### 4. Plan the Improvement Suggestions", "### 5.")


def _compile_summary() -> str:
    return _slice(_read(COMPILE), "### 5. Add Refinement Summary Section", "### 6.")


def _report_parse() -> str:
    return _slice(_read(REPORT), "### 1. Load the Run's Numbers", "### 2.")


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
    first = _scope_gate().splitlines()[0]
    assert "`{term}` is the skill's name or the alias that names it" in first
    # determinism-7: the helper gives the term, so the gate re-derives nothing from excerpts.
    assert "`{doc_mentions}.skills[].terms[]`" in first and "paragraphs[]` show where" not in first
    assert "its `terms[]` holds only `alias` entries" in derive
    helper = _comention_helper()
    skills = helper.parse_skills('[{"name": "vue-core", "aliases": ["core"]}]')
    [skill] = helper.mentions("The core services start first.\n", skills)["skills"]
    assert skill["terms"] == [{"term": "core", "kind": "alias", "paragraph_count": 1, "heading_count": 0,
                               "fenced_count": 0}]


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
    assert "`{unverified_technologies}` = `{doc_mentions}.unverified_technologies`" in rule
    assert "that no inventory skill covers" in rule
    assert "`--scope-skills` and the edits above leave it unchanged" in rule
    # Which strings are technologies is the step's call, staged before the helper runs.
    staged = _bullet(_gap_claims(), "`{run_dir}/technologies.json`")
    for needle in ("libraries, frameworks, databases, services and tools", "in order of first mention",
                   "Programming languages, protocols and data formats do not count",
                   "deprecated, removed or being replaced"):
        assert needle in staged, needle


def test_the_mentions_helper_decides_what_a_skill_covers():
    # determinism-6: the coverage test is the helper's, so the prose restates no matching rule.
    rule = _unverified_rule()
    assert "§2's matching rule" not in rule and "once case, spaces, hyphens" not in rule
    assert "no step compares a technology with a skill by hand" in rule
    assert '--technologies "{run_dir}/technologies.json"' in _gap_claims()
    # The examples the prose gave hold for the helper, one way only.
    helper = _comention_helper()
    skills = helper.parse_skills(json.dumps(["next", "react-router", "tailwindcss", "storybook-react-vite"]))
    covered = {t["name"]: [c["skill"] for c in t["covered_by"]]
               for t in helper.mentions("", skills, ["Next.js", "React Router", "Tailwind CSS", "React"])["technologies"]}
    assert covered == {"Next.js": ["next"], "React Router": ["react-router"], "Tailwind CSS": ["tailwindcss"],
                       "React": []}


def test_an_alias_inside_a_longer_name_covers_nothing():
    # Step 5b RA determinism-1: an `alias-contained` entry leaves the technology unverified, as the
    # derived scope judges common-word aliases, unless the document shows the alias is that technology.
    rule = _unverified_rule()
    for needle in ("`covered_by` entry of kind `alias-contained`", "does not cover the technology",
                   "stays in `{unverified_technologies}`", "the derived scope above judges common-word aliases"):
        assert needle in rule, needle
    helper = _comention_helper()
    skills = helper.parse_skills(json.dumps([{"name": "oms-ai", "aliases": ["ai"]}]))
    out = helper.mentions("", skills, ["Azure AI Search"])
    assert out["technologies"][0]["covered_by"] == [{"skill": "oms-ai", "term": "ai", "kind": "alias-contained"}]
    assert out["unverified_technologies"] == ["Azure AI Search"]


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


def _compile_recovery() -> str:
    return _slice(_compile_base(), "**Context recovery check:**", "\n\n")


def test_compile_recovers_the_scope_block():
    recovery = _compile_recovery()
    assert "`{unverified_technologies}` (Step 02 §2b), which the plan (§6) needs: the `<!-- [RA-SCOPE] -->` block" in recovery
    assert "When a block is still missing" in recovery
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


def test_report_reads_what_it_shows_from_the_run():
    # An input refined before can hold an older Refinement Summary, so the
    # report reads the build record and the run's state, never the document.
    parse = _slice(_report_parse(), "**Bind what §2 and §3 show from the files:**", "\n\n")
    assert "`unverified_count` from `counts.unverified`" in parse
    assert "`unverified_technologies` from its `unverified_technologies` (comma-separated, or `none`)" in parse
    # The counts the dropped table showed are bound no more.
    for gone in ("vs_coverage", "`skill_count`", "`gap_count`", "counts.improvement_tiers"):
        assert gone not in parse, gone
    assert "Extract metrics from the Refinement Summary section" not in _read(REPORT)


def _schema() -> dict:
    return json.loads(_read(REPO_ROOT / "src" / "shared" / "scripts" / "schemas"
                            / "skf-refine-architecture-result-envelope.v1.json"))


HEADLESS_COUNTS = ("gap_count", "issue_count", "improvement_count", "unverified_count")


def test_an_interactive_report_repeats_no_count_table():
    # Maintainer decision 2026-10-02: the step 5 review just showed the
    # Refinement Summary, so the final report shows no `| Metric | Count |` table.
    shown = _report_summary()
    assert "| Metric | Count |" not in shown and _table_rows(shown) == {}
    assert "Show no count table: the step 5 review showed every count" in shown
    # The review the sentence names does show it.
    review = _slice(_read(COMPILE), "### 7. Present the Draft for Review", "### 8.")
    assert "{Display the `summary` of `{applyResult}`" in review


def test_a_headless_run_keeps_the_counts_in_its_result():
    shown = _report_summary()
    assert "a headless run's result line (§4) carries" in shown
    properties = _schema()["properties"]
    contract = _slice(_read(REFS / "exit-codes.md"), "## Result Envelope", "## Emitting a Halt")
    for key in HEADLESS_COUNTS:
        assert f"`{key}`" in shown and key in properties and f"`{key}`" in contract, key
    # Every line the emitter prints must carry them.
    assert set(HEADLESS_COUNTS) <= set(_schema()["required"])


def test_the_summary_rows_live_in_compile_only():
    compiled = set(_table_rows(_compile_summary()))
    assert {NOT_VERIFIED, VS_COVERAGE} <= compiled
    assert not set(_table_rows(_report_summary())), "the report repeats no row of the Refinement Summary"


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
    exit_codes = _slice(_read(RA / "references" / "exit-codes.md"), "| Code |", "## Result Envelope")
    exit_6 = [line for line in exit_codes.splitlines() if line.startswith("| 6 ")]
    assert len(exit_6) == 1 and "step 2 §2b scope confirmation `[X]`" in exit_6[0]


def test_every_state_block_compile_reads_is_written_by_a_step():
    written = set()
    for path in (INIT, GAP, ISSUES, IMPROVEMENTS, STORAGE):
        written |= set(STATE_BLOCK_RE.findall(_read(path)))
    read_back = set(STATE_BLOCK_RE.findall(_compile_base()))
    assert {"[RA-GAPS]", "[RA-ISSUES]", "[RA-IMPROVEMENTS]", "[RA-DISMISSED]", "[RA-SCOPE]", "[RA-VS]"} <= read_back
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
    assert "Unless `--vs-report-path` was passed, run the probe (the first command) before asking anything" in inputs
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
    # One list of exit codes serves the probe and the path mode, which differ only on exit 2 with a JSON.
    inputs = _init_inputs()
    modes = _slice(inputs, "Unless `--vs-report-path` was passed, run the probe", "\n\n**Unusable VS report.**")
    assert 'uv run {validateFeasibilityReportHelper} "{vs_report_path}"' in modes
    assert "exactly as `--locate` does and prints the same JSON" in modes
    assert inputs.count("Branch on its exit code:") == 1
    halt = _bullet(modes, "**1**")
    assert "HALT as **Unusable VS report** says below" in halt
    retry = _bullet(modes, "**2** with a JSON from the path mode")
    assert "(the file is missing or could not be read" in retry
    assert "run the probe above if it has not run, and ask the report question again" in retry
    assert "run the probe above and take its outcome as if `--vs-report-path` had not been passed" in retry


def test_an_unusable_report_halts_input_invalid():
    inputs = _init_inputs()
    probe = _slice(inputs, "Branch on its exit code:", "\n\n**Unusable VS report.**")
    assert "- **1** (the report breaks the contract), or **2** with a JSON from the probe" in probe
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
    assert "Cache the JSON of the report this run uses as `{vs_report}`: no step reads the report file by hand" in record
    assert "`vs_report_available` to true when there is one (its `status` is `ok`)" in record
    assert "helper is unavailable" not in record


def test_a_missing_feasibility_helper_halts_instead_of_skipping_the_report():
    # #599: no run goes on without the report it was meant to read; `none` needs no helper.
    find = _slice(_init_inputs(), "**Find the [VS] report first.**", "\n\n")
    assert find.startswith("**Find the [VS] report first.** Unless `--vs-report-path none` was passed, resolve")
    assert ('If no candidate exists, or `uv` cannot start it, HALT (exit code 3, `halt_reason: "resolution-failure"`) '
            "at phase `init:feasibility-validator`") in find
    assert "`skf-validate-feasibility-report.py` is not installed" in find
    assert "refine without a report with `--vs-report-path none`" in find
    text = _read(INIT)
    assert "vs_report_not_read" not in text and "VS report not read: the feasibility-report helper" not in text


RESOLUTION_HALT = 'HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `{}`'


def test_a_missing_or_failing_inventory_or_mentions_helper_halts():
    # #599: no step lists the skills or finds the mentions by hand; a call that fails halts too.
    claims = _gap_claims()
    run = _slice(claims, "**Run the mentions helper once.**", "\n\n")
    assert ("If no candidate exists, `uv` cannot start it, or the command below exits non-zero, "
            + RESOLUTION_HALT.format("gap-analysis:comention")) in run
    assert "{its first stderr line, or with no candidate: `skf-comention-pairs.py` is not installed." in run
    assert "On exit 1 (its stderr names a staged input it refuses), fix that file and run the command once more before halting" in run
    assert "No step finds the mentions by hand" in run
    gap = _read(GAP)
    for gone in ("Graceful degradation", "derive the pairs from the inventory"):
        assert gone not in gap, gone
    # Step 03 reads no pair list: it passes the scope to the `verdicts` join.
    assert ("§5 and Step 04 §4 read these two pair lists instead of checking each pair's scope again; Step 03 §4 "
            "passes `{in_scope_skills}` to the `verdicts` join") in _gap_split()
    scan = _slice(_read(INIT), "### 2. Scan Skills Folder", "```bash")
    assert ("If no candidate exists, `uv` cannot start it, or the command below exits non-zero (a "
            "`{skills_output_folder}` that does not exist, say), " + RESOLUTION_HALT.format("init:inventory")) in scan
    assert "{its first stderr line, or with no candidate: `skf-enumerate-stack-skills.py` is not installed." in scan
    assert "No step walks `{skills_output_folder}` by hand" in scan
    assert "**Fallback path" not in _read(INIT)
    codes = _slice(_read(REFS / "exit-codes.md"), "| Code |", "## Result Envelope")
    [exit_3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    assert ("a helper is not installed, cannot start or fails: step 1 §2 (`skf-enumerate-stack-skills.py`, phase "
            "`init:inventory`), step 2 §2 (`skf-comention-pairs.py`, phase `gap-analysis:comention`)") in exit_3
    assert "step 1 §1 (`skf-validate-feasibility-report.py`, phase `init:feasibility-validator`)" in exit_3


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
    assert len(calls) == 2, calls
    assert "{validateFeasibilityReportHelper}" not in _read(ISSUES), "step 3 reads the report through `verdicts`"
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
               "coveragePercentage", "coverageMeasured")


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


VERDICTS_CALL = ('uv run {preservationScript} verdicts --report "{vs_report_path}" --generated-at "{vs_generated_at}" '
                 '--skills "{run_dir}/skill-terms.json" --in-scope "{in_scope_names}" --rules "{refinementRulesData}"')


def test_issue_detection_joins_the_verdicts_with_the_script():
    # determinism-5: one call joins the rows to the inventory and the scope.
    vs = _issue_vs()
    assert VERDICTS_CALL in vs and _read(ISSUES).count("verdicts --report") == 1
    assert "preservationScript: 'scripts/skf-check-preservation.py'" in _frontmatter(_read(ISSUES))
    join = _slice(vs, "**Join the verdicts to the scope.**", "\n\n")
    for needle in ("(`pairVerdicts`) again through the shared feasibility-report reader",
                   "the skill names and aliases in `{run_dir}/skill-terms.json` (Step 02 §2)",
                   "the scope Step 02 §3 settled", "the VS Report Integration table of `{refinementRulesData}`"):
        assert needle in join, needle
    for gone in ("**Scope filter", "**Read the verdicts from `{vs_report}`**", "Map each pair's `lib_a`"):
        assert gone not in vs, gone
    assert "(match case-insensitively)" not in vs
    # Step 02 stages the skill terms both helpers read.
    assert "Step 03 §4 reads it too" in _bullet(_gap_claims(), "`{run_dir}/skill-terms.json`")


def test_issue_detection_halts_when_the_verdicts_are_gone():
    # The report the run started from, read again; a rewrite, or rules that no longer pass, halt.
    assert "validateFeasibilityReportProbeOrder:" not in _frontmatter(_read(ISSUES))
    vs = _issue_vs()
    assert "read them from the `[RA-VS]` and `[RA-SCOPE]` blocks of the RA state file" in vs
    stale = _bullet(vs, "**1** (`status: \"stale\"`)")
    assert 'HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `issue-detection:vs-report`' in stale
    assert ("the report this run started from is gone ([VS] rewrote it during this run, or it cannot be read "
            "again), or the refinement rules no longer pass step 1's check") in stale
    missing = _bullet(vs, "**3**")
    assert 'HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `issue-detection:vs-report`' in missing
    assert "- **2 with no JSON:**" not in vs and "**2 with no JSON:** a malformed call" in vs


VS_TOKENS = ("Blocked", "Risky", "Plausible", "Verified")


def _rules_vs() -> str:
    return _slice(_read(RULES), "## VS Report Integration", "\n## ")


def test_verdicts_are_promoted_by_their_exact_token():
    # One home for the token mapping: the rules file a team may swap, which the script reads.
    promote = _bullet(_issue_vs(), "**0:**")
    assert "whose `raises` names a tier is an issue of that tier" in promote
    assert "never phrases in the rationale text" in promote
    assert not TIER_RE.search(_issue_vs()), "the mapping is not restated"
    script = _load("ra_scope_verdict_rules", PRESERVATION_SCRIPT)
    assert script.check_rules(str(RULES))["vs_raises"] == {"Verified": None, "Plausible": "Minor", "Risky": "Major",
                                                           "Blocked": "Critical"}
    rows = _table_rows(_rules_vs())
    assert [token for token in rows if token.startswith("`")] == [f"`{token}`" for token in VS_TOKENS]
    assert rows["`Verified`"][1] == "No issue"


RATIONALE_PHRASES = ("no direct API evidence", "weak evidence")


def test_the_plausible_rule_keys_on_the_token():
    for path in (ISSUES, RULES):
        for phrase in RATIONALE_PHRASES:
            assert phrase not in _read(path), f"{path.name} still keys on the rationale phrase {phrase!r}"
    rules = _rules_vs()
    assert "each rule keys on the token alone" in rules
    assert _table_rows(rules)["`Plausible`"][1].startswith("A **Minor**, potential issue")
    assert "RISKY" not in rules and "BLOCKED" not in rules, "the tokens are case-sensitive"
    severity = _slice(_read(ISSUES), "**Severity:**", "\n\n")
    assert "one tier of the Issue Severity table of `{refinementRulesData}`" in severity
    assert "a VS-sourced issue takes the tier its verdict's row raises" in severity


def test_issue_detection_scopes_verdicts_by_the_scope():
    vs = _issue_vs()
    assert "`{in_scope_names}` every name in `{in_scope_skills}`, comma-separated" in vs
    routed = _bullet(vs, "**0:**")
    assert "Record every `out_of_scope` row" in routed and "informational Out-of-Scope bucket" in routed
    assert "either library in `{out_of_scope_skills}`" not in vs


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
    assert ('uv run {comentionHelper} mentions --doc "{analysis_doc}" --skills "{run_dir}/skill-terms.json" '
            '--technologies "{run_dir}/technologies.json"') in claims
    assert "with any earlier Refine Architecture pass set aside (Step 01 §1b)" in claims
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


def test_existence_is_read_from_the_saved_inventory():
    # Step 5b RA determinism-2 and its review: step 1 saves the inventory once, each step 2 subagent
    # reads its skill's exports[] from that file and its references/ for signatures, and step 3 checks
    # that a named export exists by membership in the file's list, so no copy of the names decides it.
    scan = _slice(_read(INIT), "### 2. Scan Skills Folder", "### 3.")
    assert '--pairs --reliability > "{run_dir}/skill-inventory.json"' in scan
    assert "as `skill_inventory`" in scan
    surfaces = _slice(_read(GAP), "### 4. Load Skill API Surfaces for Cross-Reference", "### 5.")
    for needle in ("`exports[]` from the `skills[]` entry of that name in `{run_dir}/skill-inventory.json`",
                   "`references/*.md` for the signatures SKILL.md lacks", "no name the list lacks",
                   "Only when the list is empty (a stack skill, or `exports_source` `unknown`)"):
        assert needle in surfaces, needle
    assert "Hand each its skill's `exports[]`" not in surfaces, "the parent still types each export list"
    verify = _slice(_read(ISSUES), "### 3. Verify Claims Against Skill API Surfaces", "### 4.")
    for needle in ("membership lookup in the skill's `exports[]` in `{run_dir}/skill-inventory.json`",
                   "fails on existence only when that list lacks the name",
                   "judge only the signature, protocol or types the claim states",
                   "When that list is empty", "never taking a missing name as proof"):
        assert needle in verify, needle


def test_language_comes_from_the_inventory():
    surfaces = _slice(_read(GAP), "### 4. Load Skill API Surfaces for Cross-Reference", "### 5.")
    assert "From metadata.json (read in parent" not in surfaces
    assert "each skill's `language`" in surfaces
    assert "Do not open `metadata.json` in the parent." in surfaces


# --- Step 5 and SKILL.md ---


def test_compile_recovers_the_vs_report_block():
    recovery = _compile_recovery()
    assert "which the VS Coverage row (§5) needs: the `<!-- [RA-VS] -->` block" in recovery
    assert "`coverageMeasured`" in recovery and "`none`" in recovery
    assert "exit code 8" in recovery and '`halt_reason: "recovery-failed"`' in recovery


def test_skill_md_names_the_vs_report_halt():
    exit_codes = _slice(_read(RA / "references" / "exit-codes.md"), "| Code |", "## Result Envelope")
    [exit_2] = [line for line in exit_codes.splitlines() if line.startswith("| 2 ")]
    assert "a [VS] report that breaks the feasibility-report contract" in exit_2
    assert exit_2.rstrip(" |").endswith("→ `input-invalid`")
    [exit_8] = [line for line in exit_codes.splitlines() if line.startswith("| 8 ")]
    assert ("step 3 §4 (the [VS] report cannot be read again, or [VS] rewrote it during the run, or the refinement "
            "rules no longer pass step 1's check)") in exit_8
    [headless] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Headless** |")]
    assert "without `--vs-report-path` step 1 uses the [VS] report it finds" in headless


# --- The rules file holds house style only (#596, #600) ---

RULE_TABLES = ("Gap Classification", "Issue Classification", "Issue Severity", "VS Report Integration",
               "Improvement Classification", "Improvement Value")
BUNDLED_TYPES = ("Missing Integration Path", "Undocumented Data Flow", "Absent Bridge Layer", "API Mismatch",
                 "Protocol Contradiction", "Language Boundary Ignored", "Type Incompatibility",
                 "Unused Capability", "Cross-Library Synergy", "Alternative Pattern")
TIER_RE = re.compile(r"\b(?:Critical|Major|Minor|High|Medium|Low)\b")
PRESERVATION_SCRIPT = RA / "scripts" / "skf-check-preservation.py"


def _rules_tiers(table: str) -> list[str]:
    # The last table runs to the end of the file, so close the text with a heading.
    rows = _table_rows(_slice(_read(RULES) + "\n## end", f"## {table}\n", "\n## "))
    return [label for label in rows if label not in {"Severity", "Value"}]


def test_the_rules_file_says_what_a_copy_can_change():
    text = _read(RULES)
    headings = re.findall(r"^## (.+)$", text, re.M)
    assert headings == ["What a Copy Can Change", *RULE_TABLES], headings
    copy = _slice(text, "## What a Copy Can Change", "\n---")
    for needle in ("replaces this whole file", "severity and value tiers", "which tier each [VS] verdict raises",
                   "keeps the six tables below under their headings", "Step 01 halts on a copy that lacks one",
                   "`references/finding-storage.md`", "the document scope of Step 02 §2b"):
        assert needle in copy, needle
    # The storage contract and the steps' method left the swappable file.
    for gone in ("Finding Storage", "ra-state-", "Detection Method", "skill_inventory.pairs"):
        assert gone not in text, gone
    improvements = _slice(text, "## Improvement Classification", "|")
    assert "each in-scope skill (Step 02 §2b)" in improvements


def test_step_1_checks_the_tables_the_steps_read():
    # The script holds the check, so init runs it instead of applying the rules by hand.
    check = _slice(_read(INIT), "### 4. Check the Refinement Rules", "### 5.")
    assert 'uv run {preservationScript} rules --rules "{refinementRulesData}"' in check
    assert "six tables the steps read" in check
    assert 'HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:rules`' in check
    assert "Extract:" not in _read(INIT)
    script = _load("ra_scope_rule_tables", PRESERVATION_SCRIPT)
    assert script.RULE_TABLES == RULE_TABLES and set(script.VS_TOKENS) == set(VS_TOKENS)
    assert script.check_rules(str(RULES))["status"] == "ok"


def test_the_steps_classify_with_the_loaded_rules():
    binding = "refinementRulesData: '{refinementRulesPath}'"
    for path in (INIT, GAP, ISSUES, IMPROVEMENTS, COMPILE):
        text = _read(path)
        assert binding in _frontmatter(text), path.name
        assert "Reference Refinement Rules" not in text and "Extract:" not in text, path.name
    assert "Type the gap by the Gap Classification of `{refinementRulesData}`" in _read(GAP)
    assert "type it by the Issue Classification of `{refinementRulesData}`" in _read(ISSUES)
    assert ("type each improvement by the Improvement Classification of `{refinementRulesData}` and give it one "
            "tier of its Improvement Value table") in _read(IMPROVEMENTS)
    for path in (SKILL, INIT, GAP, ISSUES, IMPROVEMENTS, COMPILE, REPORT, STORAGE):
        text = _read(path)
        for name in BUNDLED_TYPES:
            assert name not in text, f"{path.name} restates the bundled type {name!r}"
        if path != COMPILE:
            assert not TIER_RE.search(text), f"{path.name} restates a bundled tier: {TIER_RE.search(text).group(0)}"
    # Compile shows the bundled tiers only as the example rows of the Changes Made table.
    rows = [line for line in _read(COMPILE).splitlines() if TIER_RE.search(line)]
    assert [row.split(" | ")[0] for row in rows] == ["| Issues Flagged", "| Improvements Suggested"]


def test_compile_and_the_report_take_the_tiers_from_the_rules():
    text = _read(COMPILE)
    assert "a tier of the Issue Severity table of `{refinementRulesData}`" in _slice(text, "### 3.", "### 4.")
    assert "a tier of the Improvement Value table of `{refinementRulesData}`" in _slice(text, "### 4.", "### 5.")
    summary = _compile_summary()
    assert "a `{<tier>_count}` for each severity and value tier" in summary
    # Section 5 and section 6 read the one list Step 01's `rules` check printed.
    assert "breakdowns name each tier of `{rule_tiers}` (its `issue`, then its `improvement` list)" in summary
    assert "of the Issue Severity and Improvement Value tables" not in summary
    build = _slice(text, "### 6. Build the Draft", "### 7.")
    assert '`tiers` (`{"issue": [...], "improvement": [...]}`: `{rule_tiers}`' in build
    assert "Bind `{rule_tiers}` ← `tiers`".lower() in _read(INIT).lower()
    parse = _report_parse()
    assert "`counts.issue_tiers`, which lists the severity tiers of the refinement rules, most severe first" in parse
    # The report shows no count table (the review showed it), so no tier breakdown either.
    assert "counts.improvement_tiers" not in _report_summary()
    assert "{IF the first tier of `counts.issue_tiers`, the most severe, counts any issue:}" in _report_next_steps()


def test_the_bundled_tiers_are_the_scripts_defaults():
    # The bundled rules and the preservation script agree, so a plan built
    # from the bundled file places and counts exactly as before.
    script = _load("ra_scope_preservation", PRESERVATION_SCRIPT)
    assert _rules_tiers("Issue Severity") == script.DEFAULT_TIERS["issue"]
    assert _rules_tiers("Improvement Value") == script.DEFAULT_TIERS["improvement"]
    vs = _table_rows(_rules_vs())
    severities = set(_rules_tiers("Issue Severity"))
    for token in VS_TOKENS[:3]:
        raised = re.match(r"A \*\*([A-Za-z]+)\*\*", vs[f"`{token}`"][1])
        assert raised and raised.group(1) in severities, token


def _rules_comment() -> str:
    comment = _slice(_read(CUSTOMIZE), "# House-style refinement rules.", 'refinement_rules_path = ""')
    return " ".join(line.removeprefix("#").strip() for line in comment.splitlines())


def test_a_copy_learns_the_tier_rules_and_step_1_checks_them():
    # Each tier becomes a {<tier>_count} the preservation script fills, so the
    # names it cannot count are named where a copy is written and checked.
    script = _load("ra_scope_preservation", PRESERVATION_SCRIPT)
    fixed = sorted({name.removesuffix("_count") for name in script.REQUIRED_PLACEHOLDERS} | {"unverified", "skill"})
    copy = _slice(_read(RULES), "## What a Copy Can Change", "\n---")
    check = _slice(_read(INIT), "### 4. Check the Refinement Rules", "### 5.")
    comment = _rules_comment()
    for needle in ("starts with a letter and holds only the letters A to Z, digits and spaces",
                   "each VS Report Integration row raises a tier of the Issue Severity table, or no issue"):
        assert needle in copy, needle
    assert "no two tiers share a name, ignoring case, in one table or across the two" in copy
    assert "its tiers follow the rules the file's first section states" in check
    assert sorted(name.removesuffix("_count") for name in script.RESERVED_COUNTS) == fixed
    for name in fixed:
        assert name.capitalize() in copy and name in comment, name
    for needle in ("a tier name starts with a letter and holds only the letters A to Z, digits and spaces",
                   "no two tiers share a name (ignoring case), severity and value tiers included",
                   "each VS Report Integration row raises a tier of Issue Severity, or no issue",
                   "step 1 halts on a copy that lacks a table or whose tiers break these rules",
                   "Fixed whatever the copy says: what each step looks for"):
        assert needle in comment, needle
    assert ('(`status: "violations"`: it lacks a table or breaks a tier rule), or **2** with a JSON (`error` says '
            'why the file cannot be read): HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase '
            '`init:rules`') in check
    # What a step looks for is fixed: the types only label it.
    assert "What each step looks for is fixed" in copy and "a finding no type fits takes the closest type" in copy


def _apply_with_tiers(tmp_path, severity: list[str], value: list[str], raised: str) -> tuple[int, dict]:
    """Run compile's apply on a plan with these tiers: one gap, and one issue of the tier `raised`."""
    doc = tmp_path / "architecture.md"
    doc.write_bytes(b"# App\n\n## Data Layer\n\nLoro stores documents.\n")
    counts = ", ".join(f"{tier}: {{{re.sub(r'[ ]+', '_', tier.lower())}_count}}" for tier in [*severity, *value])
    summary = ("## Refinement Summary\n\nGaps: {gap_count}, issues: {issue_count}, "
               f"improvements: {{improvement_count}}\n\n{counts}\n")
    plan = {"entries": [
        {"id": "gap-1", "kind": "gap", "anchor": None, "skills": ["loro", "fastapi"],
         "block": "#### RA: Loro <-> FastAPI Integration Path"},
        {"id": "issue-1", "kind": "issue", "tier": raised, "anchor": None, "skills": ["loro"],
         "block": "> [!WARNING] **Issue Detected by Refine Architecture**"},
    ], "summary": summary, "unverified_technologies": [], "skill_count": 2,
        "tiers": {"issue": severity, "improvement": value}}
    plan_path = tmp_path / "insertion-plan.json"
    plan_path.write_bytes(json.dumps(plan).encode("utf-8"))
    proc = subprocess.run(
        [sys.executable, str(PRESERVATION_SCRIPT), "apply", "--original", str(doc), "--plan", str(plan_path),
         "--draft", str(tmp_path / "draft.md"), "-o", str(tmp_path / "apply.json")],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


BROKEN_TIERS = [
    pytest.param(["High", "Medium", "Low"], ["High", "Medium", "Low"], "High", 1,
                 "an issue tier and an improvement tier share a name", id="one-set-for-severity-and-value"),
    pytest.param(["Must-fix", "Later"], ["High", "Low"], "Must-fix", 0, "Must-fix: {must-fix_count}",
                 id="punctuation"),
    pytest.param(["1st", "2nd"], ["High", "Low"], "1st", 0, "1st: {1st_count}", id="leading-digit"),
    pytest.param(["Gap", "Later"], ["High", "Low"], "Later", 0, "Gaps: 0,", id="a-fixed-count-name"),
    pytest.param(["Critical", "Major", "Minor"], ["High", "Medium", "Low"], "Severe", 1, "tier-unknown",
                 id="a-vs-row-raising-no-severity-tier"),
]


@pytest.mark.parametrize(("severity", "value", "raised", "code", "symptom"), BROKEN_TIERS)
def test_each_tier_rule_guards_a_summary_the_script_could_not_count(tmp_path, severity, value, raised, code, symptom):
    # A copy that broke the rule would never build (exit 1, which fixing the
    # plan cannot help) or would build a summary with a wrong or unfilled count.
    exit_code, result = _apply_with_tiers(tmp_path, severity, value, raised)
    assert exit_code == code, result
    if code:
        assert symptom in json.dumps(result["problems"]), result["problems"]
    else:
        assert symptom in result["summary"], result["summary"]
        assert result["counts"]["gap"] == 1


def test_a_renamed_tier_set_fills_its_own_counts(tmp_path):
    exit_code, result = _apply_with_tiers(tmp_path, ["Blocker", "Should fix"], ["Worth it", "Later on"], "should fix")
    assert exit_code == 0, result
    assert result["counts"]["issue_tiers"] == {"Blocker": 0, "Should fix": 1}
    assert result["counts"]["improvement_tiers"] == {"Worth it": 0, "Later on": 0}
    assert "Gaps: 1, issues: 1, improvements: 0" in result["summary"]
    assert "Blocker: 0, Should fix: 1, Worth it: 0, Later on: 0" in result["summary"]
    assert "{" not in result["summary"]


# --- Finding storage is fixed (#596) ---


def test_finding_storage_lives_in_a_fixed_file():
    text = _read(STORAGE)
    assert "No customization replaces it" in text.splitlines()[0]
    assert "`{forge_data_folder}/ra-state-{project_name}.md`" in text
    assert "**complete formatted findings**" in text and "never only counts" in text
    for block in ("[RA-GAPS]", "[RA-ISSUES]", "[RA-IMPROVEMENTS]", "[RA-OUT-OF-SCOPE]", "[RA-DISMISSED]"):
        assert f"`<!-- {block} ... -->`" in text, block
    for path in (GAP, ISSUES, IMPROVEMENTS):
        step = _read(path)
        assert "findingStorageData: 'references/finding-storage.md'" in _frontmatter(step), path.name
        assert "as `{findingStorageData}` says" in step, path.name
        assert "Finding Storage rule (refinement rules)" not in step, path.name
    toml = _read(CUSTOMIZE)
    comment = _slice(toml, "# House-style refinement rules.", 'refinement_rules_path = ""')
    for needle in ("references/finding-storage.md", "six tables", "A copy replaces that whole file"):
        assert needle in comment, needle


# --- A finding the review drops stays dropped (#587 follow-up) ---

DISMISSED_FILE = "dismissedFile: '{outputFolderPath}/.ra-dismissed-{arch_project_name}.json'"


def test_a_finding_the_review_drops_stays_dropped():
    assert DISMISSED_FILE in _frontmatter(_read(INIT)) and DISMISSED_FILE in _frontmatter(_read(COMPILE))
    previous = _slice(_read(INIT), "**Findings an earlier review dropped.**", "\n\n")
    assert "When `{previous_pass}` is true and `{dismissedFile}` exists, read it as `{dismissed_findings}`" in previous
    fields = "`{kind, skills, anchor, title, capability}`"
    assert fields in previous and fields in _read(STORAGE)
    match = _slice(_read(STORAGE), "Compare each in-scope finding", "\n")
    assert "findingStorageData: 'references/finding-storage.md'" in _frontmatter(_read(COMPILE))
    assert "its kind (`gap`, `issue` or `improvement`) is the record's and it cites the same skills" in match
    assert "An issue must also contradict the claim the record's `anchor` holds" in match
    # Step 4 raises one improvement per unused capability, so a skill has
    # several: the capability keeps one drop from hiding the others.
    assert "an improvement must name the capability or API the record's `capability` holds" in match
    assert "so one dropped finding never hides another about the same skills" in match
    assert "with a one-line title of its own and the `title` of the record it matched" in match
    assert "inserts it only if the user takes it back" in match
    record = _slice(_read(STORAGE), "**How Step 05 records a drop.**", "\n")
    assert '`{"kind", "skills", "anchor", "title", "capability"}`' in record
    assert "`capability` the `{api}` an improvement's block names, `null` for a gap or an issue" in record
    assert "a finding the user takes back removes the record it matched" in record
    assert "{api}" in _compile_improvements(), "the record's capability is the one the improvement block names"
    assert "atomicWriteProbeOrder:" in _frontmatter(_read(COMPILE))
    review = _slice(_read(COMPILE), "### 7. Present the Draft for Review", "### 8.")
    assert "{IF the `[RA-DISMISSED]` block holds findings:}" in review
    assert "its own title and the title of the record it matched" in review
    assert "A finding you dropped at the review stays out of later [RA] runs on this document" in _report_next_steps()


DISMISSED_WRITE = 'uv run {atomicWriteHelper} write --target "{dismissedFile}" < "{run_dir}/dismissed.json"'
PROMOTE = "uv run {preservationScript} promote "


def test_only_an_approved_review_records_a_drop():
    # A feedback round keeps the list in the run folder: [X] or a failed
    # promotion must leave the record a later run reads as it was. The write
    # and the record's shape live in finding-storage.md; compile points there.
    text, storage = _read(COMPILE), _read(STORAGE)
    assert DISMISSED_WRITE not in text and storage.count(DISMISSED_WRITE) == 1, "the record is written once"
    approve = _slice(text, "- IF C (only while the last `apply` exited 0)", "- IF cancel")
    assert approve.index(PROMOTE) < approve.index("  - **0:**")
    written = _slice(approve, "  - **0:**", "  - **1**")
    assert "When a feedback round staged `{run_dir}/dismissed.json`, only now write it to `{dismissedFile}`" in written
    assert "as `{findingStorageData}` says" in written
    assert written.index("{findingStorageData}") < written.index("execute `{nextStepFile}`")
    record = _slice(storage, "**How Step 05 records a drop.**", "\n\n")
    assert "Keep that list in `{run_dir}/dismissed.json`" in record
    assert "It reaches `{dismissedFile}` only at [C], once `promote` exits 0, so [X] leaves the record as it was" in record
    assert record.index("so [X] leaves the record as it was") < record.index("{atomicWriteHelper}")
    failed = '"The dropped findings were not recorded ({reason}): a later run may raise them again." and go on'
    assert storage.index(DISMISSED_WRITE) < storage.index(failed)
    feedback = _bullet(_slice(text, "#### Menu Handling Logic:", "[Redisplay Menu Options]"), "IF Any other")
    assert "record each drop or take-back in `{run_dir}/dismissed.json` as `{findingStorageData}` says" in feedback
    cancel = _bullet(_slice(text, "#### Menu Handling Logic:", "[Redisplay Menu Options]"), "IF cancel")
    assert "{dismissedFile}" not in cancel


# --- The walkthrough sits at the review gate (#599) ---


def test_the_review_gate_offers_the_walkthrough():
    menu = _slice(_read(COMPILE), "### 8. Present MENU OPTIONS", "#### Menu Handling Logic:")
    [select] = [line for line in menu.splitlines() if "**Select:**" in line]
    options = OPTION_RE.findall(select)
    assert options == ["R", "C", "X"], options
    assert GATE_DEFAULT_RE.findall(menu) == ["C"]
    branches = [line for line in _read(COMPILE).splitlines() if line.startswith("- IF ")]
    assert [b.split(":")[0] for b in branches[:2]] == ["- IF R", "- IF C (only while the last `apply` exited 0)"]
    assert "It changes nothing; then redisplay this menu." in branches[0]
    report = _read(REPORT)
    assert "[R]" not in report and "Present Menu" not in report and "EXECUTION RULES" not in report
    assert "### 6. Finish the Run" in report
    skill = _read(SKILL)
    [gates] = [line for line in skill.splitlines() if line.startswith("| **Gates** |")]
    assert "step 5: Review Gate [R] review each refinement / [C] approve" in gates and "step 6" not in gates
    assert "| 6 | Report | references/report.md | Yes |" in skill
    assert "final menu" not in skill


# --- Step 04 reads the surfaces Step 02 collected (#599) ---


def test_step_4_reads_the_surfaces_step_2_collected():
    surfaces = _slice(_read(GAP), "### 4. Load Skill API Surfaces for Cross-Reference", "### 5.")
    assert '"capabilities": [' in surfaces and "- `capabilities`:" in surfaces
    assert "as a `<!-- [RA-SURFACES] ... -->` block" in surfaces
    improvements = _read(IMPROVEMENTS)
    assert "delegate to parallel subagents" not in improvements, "Step 04 launches no second round of subagents"
    assert "Never re-read a SKILL.md, in the parent or through new subagents." in improvements
    for path in (ISSUES, IMPROVEMENTS):
        text = _read(path)
        assert "`{exports, protocols, data_formats, capabilities}`" in text, path.name
        assert "the `<!-- [RA-SURFACES] ... -->` block" in text, path.name
        assert "Reload a" not in text, path.name


# --- Headless envelopes name what a run left out (#593 follow-up) ---


def test_the_split_records_the_skills_left_out():
    split = _gap_split()
    warning = _bullet(split, "Once these bindings are final")
    assert "record the warning `out_of_scope_skills: <n> skills left out of the scope of this run:" in warning
    assert split.index("`pair_count` equals") < split.index("Once these bindings are final")


RECORDED_WARNING_RE = re.compile(r"[Rr]ecord the warning `([^`]+)`")
RECORD_WARNING_CMD = "uv run {emitEnvelopeHelper} record --run-dir \"{run_dir}\" --warning '<the warning>'"


def test_no_recorded_warning_holds_a_single_quote():
    # The record command single-quotes the warning, so an apostrophe in one
    # ends the quote early and bash never runs the command.
    commands = [path.name for path in REFS.glob("*.md") if RECORD_WARNING_CMD in _read(path)]
    assert sorted(commands) == ["gap-analysis.md", "init.md"], commands
    warnings = [(path.name, w) for path in sorted(REFS.glob("*.md")) for w in RECORDED_WARNING_RE.findall(_read(path))]
    assert len(warnings) >= 6, warnings
    for name, warning in warnings:
        assert "'" not in warning, f"{name}: {warning}"
        command = RECORD_WARNING_CMD.replace("<the warning>", warning)
        assert shlex.split(command)[-1] == warning, f"{name}: {warning}"
