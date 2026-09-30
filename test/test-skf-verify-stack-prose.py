#!/usr/bin/env python3
"""Prose contract of skf-verify-stack's feasibility report (#590, #599).

No test runs a stage file, so these pin what the stages promise:

- the Plausible cap is stated once, in integration-verification-rules.md, and
  a pair with a literal Check 4 citation can reach Verified;
- no stage recomputes a helper's result by hand when the helper is missing;
- no stage halts a vacuous analysis (exit 8 `analysis-halted` is gone), and the
  report ends without a menu, so the Stages table's Auto-proceed column
  matches the GATE annotations of the stage files;
- the project slug comes from the shared helper that holds the slug rule;
- the report fills the template's one canonical verdict table, with the
  display table a separate table below it;
- the integrations stage takes each skill's language, exports and evidence
  tier from the inventory, never from metadata.json;
- the Plausible recommendation says what Check 4 reads;
- each fact has one home (the single-technology note, where each run
  variable is fixed);
- module-help.csv and skill-lifecycle.md name the file the skill writes.
"""

from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "skf-verify-stack"
REFERENCES = SKILL / "references"
RULES = REFERENCES / "integration-verification-rules.md"
VALIDATOR = REPO / "src" / "shared" / "scripts" / "skf-validate-feasibility-report.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _stage_files():
    return sorted(REFERENCES.glob("*.md"))


def _skill_markdown():
    return [SKILL / "SKILL.md", *_stage_files(), *sorted((SKILL / "assets").glob("*.md"))]


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _section(text: str, start: str, end: str) -> str:
    assert start in text, f"marker {start!r} missing"
    body = text[text.index(start):]
    assert end in body, f"marker {end!r} missing after {start!r}"
    return body[:body.index(end)]


# --- The Plausible cap, stated once ---------------------------------------------

# A sentence that caps a pair at Plausible: "cap the pair at `Plausible`",
# "caps at `Plausible`", "capped at Plausible".
CAP_RE = re.compile(r"\bcap(?:s|ped)?\b[^.\n]*?\bat `?Plausible", re.IGNORECASE)


def test_the_plausible_cap_lives_only_in_the_rules_file():
    for path in _skill_markdown():
        if path == RULES:
            continue
        match = CAP_RE.search(_read(path))
        assert match is None, f"{_rel(path)} restates the Plausible cap: {match.group(0)!r}"
    rules = _read(RULES)
    assert rules.count("**Plausible cap:**") == 1
    cap = rules[rules.index("**Plausible cap:**"):].split("\n\n", 1)[0]
    assert "This is the only cap." in cap


def test_a_literal_citation_can_reach_verified():
    rules = _read(RULES)
    cap = rules[rules.index("**Plausible cap:**"):].split("\n\n", 1)[0]
    # Inferred protocol tokens flag risks only; they never cap the pair.
    assert "never promotes a pair to `Verified` and never caps one at `Plausible`" in cap
    assert "A pair whose Checks 1 to 3 pass and whose Check 4 finds a literal citation is `Verified`." in cap
    check2 = _section(rules, "### 2. Protocol Compatibility Check", "### 3.")
    assert "or no token on either side, flags none" in check2
    integrations = _read(REFERENCES / "integrations.md")
    assert "no token on either side, or conflicting tokens with no adapter, flags a risk" not in integrations


# --- No hand-made fallback for a helper ------------------------------------------

FALLBACK_PHRASES = (
    "If `uv` is unavailable",
    "uv` unavailable",
    "Graceful degradation",
    "graceful degradation",
    "**Fallback path",
    "inline per the `--help`",
    "apply the ladder below inline",
    "equivalent structural check inline",
    "run the equivalent DFS",
    "claude.ai web",
)


@pytest.mark.parametrize("path", _skill_markdown(), ids=_rel)
def test_no_stage_recomputes_a_helper_by_hand(path):
    text = _read(path)
    for phrase in FALLBACK_PHRASES:
        assert phrase not in text, f"{_rel(path)} still holds a prose fallback: {phrase!r}"


def test_a_missing_helper_halts():
    skill = _read(SKILL / "SKILL.md")
    assert "Never recompute a helper's result by hand" in skill
    integrations = _read(REFERENCES / "integrations.md")
    cycles = _section(integrations, "**Resolve `{cycleFinderHelper}`**", "uv run {cycleFinderHelper}")
    assert '(exit code 3, `halt_reason: "resolution-failure"`)' in cycles
    report = _read(REFERENCES / "report.md")
    gate = _section(report, "**Validate the report (deterministic gate).**", "uv run {validateFeasibilityReportHelper}")
    assert '(exit code 3, `halt_reason: "resolution-failure"`)' in gate


# --- No vacuous-analysis halt, no closing menu ------------------------------------


@pytest.mark.parametrize("path", _skill_markdown(), ids=_rel)
def test_no_stage_halts_a_vacuous_analysis(path):
    text = _read(path)
    for phrase in ("analysis-halted", "exit code 8", "Continue anyway", "Halt workflow", "Review full report"):
        assert phrase not in text, f"{_rel(path)}: {phrase!r}"


def test_exit_codes_table_has_no_exit_8():
    rows = [line for line in _read(REFERENCES / "exit-codes.md").splitlines() if re.match(r"\|\s*\d+\s*\|", line)]
    codes = [int(line.split("|")[1]) for line in rows]
    assert codes == [0, 2, 3, 4, 5, 6, 7]
    assert "menu" not in rows[codes.index(6)]


def _stages_table():
    skill = _read(SKILL / "SKILL.md")
    table = _section(skill, "## Stages", "## Invocation Contract")
    rows = {}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].isdigit():
            rows[cells[2]] = cells[3]
    return rows


def test_stages_table_matches_the_gate_annotations():
    rows = _stages_table()
    assert len(rows) == 7
    for file, auto_proceed in rows.items():
        gated = "**GATE [default:" in _read(SKILL / file)
        assert auto_proceed == ("No (confirm)" if gated else "Yes"), f"{file}: {auto_proceed}"
    gates = next(line for line in _read(SKILL / "SKILL.md").splitlines() if line.startswith("| **Gates** |"))
    assert "step 1 Input Gate" in gates and "step 6" not in gates


# --- The slug comes from the shared helper ----------------------------------------


def test_the_slug_rule_lives_in_the_shared_helper():
    skill = _read(SKILL / "SKILL.md")
    assert "slugify `project_name` (lowercase" not in skill, "SKILL.md still slugifies in prose"
    assert "never slugify `project_name` by hand" in skill
    init = _read(REFERENCES / "init.md")
    assert "validateFeasibilityReportProbeOrder:" in init.split("\n---\n", 1)[0]
    bind = _section(init, "**Bind `{project_slug}`.**", "### 1. Accept Input Documents")
    call = next(line for line in bind.splitlines() if line.startswith("uv run {validateFeasibilityReportHelper}"))
    assert call == 'uv run {validateFeasibilityReportHelper} --locate "{outputFolderPath}" --project-name "{project_name}"'
    assert "Bind `{project_slug}` ← `projectSlug`" in bind
    assert '(exit code 3, `halt_reason: "resolution-failure"`)' in bind
    # The call fits the helper's own parser.
    spec = importlib.util.spec_from_file_location("skf_validate_feasibility_report_prose", VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    args = mod._build_parser().parse_args(["--locate", "forge", "--project-name", "My App"])
    assert args.locate == "forge" and args.project_name == "My App"


# --- One canonical verdict table ---------------------------------------------------

CANONICAL_HEADER = "| lib_a | lib_b | verdict | rationale |"


def test_the_report_fills_the_templates_one_verdict_table():
    template = _read(SKILL / "assets" / "feasibility-report-template.md")
    assert [line.strip() for line in template.splitlines()].count(CANONICAL_HEADER) == 1
    # The template's own comment no longer invites a second, appended table.
    verdicts = _section(template, "## Integration Verdicts", CANONICAL_HEADER)
    assert "Filled in place by integrations" in verdicts
    assert "Appended by" not in verdicts and "MUST be emitted" not in verdicts
    integrations = _read(REFERENCES / "integrations.md")
    write = _section(integrations, "### 6. Append to Report", "### 7.")
    assert "fill it in place instead of appending another one" in write
    assert "With zero integration pairs, leave the table with its header and delimiter rows only." in write
    assert "Emit the canonical" not in write
    # The canonical table ends at its first line that does not start with a
    # pipe, so the display table needs a blank line above it.
    assert "After one blank line, add the display table" in write


# --- One tier scale for the evidence strength -------------------------------------


def test_integrations_reads_the_inventory_not_metadata():
    integrations = _read(REFERENCES / "integrations.md")
    surfaces = _section(integrations, "### 3. Load Skill API Surfaces", "### 4.")
    assert "**From `skill_inventory` (step 1 §2), also take**" in surfaces
    assert "From metadata.json (read in parent" not in surfaces
    assert "`confidence_tier`" not in surfaces
    pairs = _section(integrations, "### 4. Cross-Reference Each Integration Pair", "**Cycle detection")
    assert "`(evidence from a {evidence_tier} skill)`" in pairs
    assert "Tier {n}" not in pairs and "confidence_tier" not in pairs
    # init.md names the inventory fields the stage takes.
    init = _read(REFERENCES / "init.md")
    for field in ("`language`", "`exports_documented`", "`evidence_tier`"):
        assert field in _section(init, "**Enumerate the skills with the shared helper:**", "**Failure-budget guard:**"), field
    assert "verdict-cap references" not in integrations


# --- The Plausible recommendation matches Check 4 ---------------------------------


def test_the_plausible_recommendation_names_what_check_4_reads():
    synthesize = _read(REFERENCES / "synthesize.md")
    plausible = _section(synthesize, "**Plausible integration (from Step 03", "**Blocked integration")
    # Check 4 searches only the two skills' SKILL.md, so a stack manifest
    # never promotes the pair.
    assert "SKILL.md names the other" in plausible
    assert "[SS]" not in plausible and "integration_patterns" not in plausible
    assert "promote" not in plausible
    check4 = _section(_read(RULES), "### 4. Documentation Cross-Reference", "---")
    assert "Skill A's SKILL.md" in check4 and "Skill B's SKILL.md" in check4


# --- One home for each fact -----------------------------------------------------------


def test_the_single_technology_fact_lives_in_synthesize_only():
    fact = "single live technology"
    assert fact in _section(_read(REFERENCES / "synthesize.md"), "### 1.", "### 2.")
    report = _read(REFERENCES / "report.md")
    assert fact not in report
    framing = next(line for line in report.splitlines() if line.startswith("- **`FEASIBLE`:**"))
    assert "`## Executive Summary`" in framing


def test_the_run_variables_name_where_each_is_fixed():
    init = _read(REFERENCES / "init.md")
    variables = next(line for line in init.splitlines() if line.startswith("**Filename variables:**"))
    assert "`project_slug` by the Bind block at the top of this step" in variables
    assert "`project_slug` and `timestamp` were fixed at activation" not in variables
    comment = _read(REFERENCES / "report.md").split("\n---\n", 1)[0]
    assert "{project_slug} (bound at the top of init.md)" in comment
    assert "§2 + §4" not in comment


# --- The file the skill writes, named where users look ---------------------------


def _latest_name():
    init = _read(REFERENCES / "init.md")
    template = re.search(r"^outputFileLatest: '\{outputFolderPath\}/([^']+)'$", init, re.MULTILINE)
    assert template, "init.md frontmatter names outputFileLatest"
    return template.group(1)


def test_module_help_names_the_written_report():
    with (REPO / "src" / "module-help.csv").open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["skill"] == "skf-verify-stack"]
    assert len(rows) == 1
    assert rows[0]["outputs"] == _latest_name() == "feasibility-report-{project_slug}-latest.md"


def test_skill_lifecycle_names_the_written_report():
    lifecycle = _read(REPO / "src" / "knowledge" / "skill-lifecycle.md")
    [line] = [line for line in lifecycle.splitlines() if line.startswith("VS → ")]
    assert "feasibility-report-{project_slug}-{timestamp}.md" in line
    assert _latest_name() in line
    assert "feasibility-report-{project_name}" not in lifecycle
