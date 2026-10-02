#!/usr/bin/env python3
"""Prose pins: the user docs describe what the skills they document do.

Each test reads a page under docs/ and the skill file or script the page
describes, so a change on one side that the other does not follow fails:

- docs/workflows.md's Quick Skill section describes the skills-module shape
  quick-extract records, says `--description` and `--exports` are
  single-target overrides that a `--batch` run refuses with the exit code and
  halt reason batch-mode.md raises, and its headless exit-code map is
  halt-contract.md's;
- its Refine Architecture section describes the gate gap analysis shows for
  a derived scope and the Refinement Summary rows and next step compile
  writes;
- docs/skill-model.md gives `confidence_tier` the scale the export gate
  accepts for each `skill_type`, says a stack's `confidence_distribution`
  sums to `library_count` as the stack validator checks, and says where an
  update records `last_update` now that update-skill writes none into
  metadata.json;
- docs/troubleshooting.md names Ferris's two install halts beside setup's
  and the installer command they all give;
- docs/agents.md lists the first-run starting points Ferris highlights, what
  WS ends with, and the offer Ferris makes before a second workflow;
- docs/verifying-a-skill.md rates each gap it names as Test Skill's Gap
  Severity table does, names every blocking category, and says what the hard
  gate reads and what a blocked run still writes; workflows.md, forge-auto.md,
  campaign.md and architecture.md say the same about a blocked run, a missing
  export and the gap ledger;
- the setup lines of workflows.md and getting-started.md hold a tier tool to
  the minimum tool-requirements.yaml sets and name the statuses the CLI tool
  report prints; workflows.md's setup flags name the halts setup raises;
- the Verify Stack, Refine Architecture, Update, Export, Drop, Audit, Quick
  Skill and Campaign lines of the docs follow the verdict rollup, the
  feasibility-report lookup, the unconsumed-report offer, the snippet timing,
  the drop version rule and envelope, the audit data folder, the quick-skill
  success envelope and batch rule, and the campaign kickoff's facts loader.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
DOCS = REPO_ROOT / "docs"
WORKFLOWS = DOCS / "workflows.md"
SKILL_MODEL = DOCS / "skill-model.md"
TROUBLESHOOTING = DOCS / "troubleshooting.md"
AGENTS = DOCS / "agents.md"
VERIFYING = DOCS / "verifying-a-skill.md"
CAMPAIGN_DOC = DOCS / "campaign.md"
FORGE_AUTO = DOCS / "forge-auto.md"
SYNERGY = DOCS / "bmad-synergy.md"
GETTING_STARTED = DOCS / "getting-started.md"
ARCHITECTURE = DOCS / "architecture.md"
TEST_SKILL = SRC / "skf-test-skill"
SCORING_RULES = TEST_SKILL / "references" / "scoring-rules.md"
HARD_GATE = TEST_SKILL / "references" / "step-hard-gate.md"
SCHEMAS = SRC / "shared" / "scripts" / "schemas"
QUICK = SRC / "skf-quick-skill"
QUICK_EXTRACT = QUICK / "references" / "quick-extract.md"
BATCH_MODE = QUICK / "references" / "batch-mode.md"
HALT_CONTRACT = QUICK / "references" / "halt-contract.md"
RA_REFS = SRC / "skf-refine-architecture" / "references"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
VALIDATE_OUTPUT = SRC / "shared" / "scripts" / "skf-validate-output.py"

INSTALLERS = ("npx bmad-module-skill-forge install", "npx bmad-method install")
EXIT_ROW_RE = re.compile(r"^\s*\| (\d+)\s+\| ([a-z-]+)\s+\|", re.M)
BOLD_PATH_RE = re.compile(r"\*\*([^*]+)\*\* \(")
NUMBER_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


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


def _tail(text: str, start: str) -> str:
    """`text` from `start`, which occurs once, to its end."""
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    return text[text.index(start):]


def _paragraph(text: str, start: str) -> str:
    """The one paragraph of `text` that starts with `start`."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.lstrip().startswith(start)]
    assert len(paragraphs) == 1, f"one paragraph starting with {start!r} expected, found {len(paragraphs)}"
    return paragraphs[0]


def _quick_section() -> str:
    return _slice(_read(WORKFLOWS), "### Quick Skill (QS)", "**Agent:**")


def _ra_section() -> str:
    return _slice(_read(WORKFLOWS), "### Refine Architecture (RA)", "**Agent:**")


def _exit_codes(table: str) -> dict[str, str]:
    """{code: meaning} from the rows of a markdown table led by Code and Meaning columns."""
    return dict(EXIT_ROW_RE.findall(table))


# --------------------------------------------------------------------------
# Quick Skill: skills modules, the batch refusal and the exit-code map
# --------------------------------------------------------------------------


def test_quick_skill_documents_the_skills_module_shape():
    """#527: the section names the shape quick-extract records and what such a skill documents."""
    sniff = _slice(_read(QUICK_EXTRACT), "### 1.5. Repo-Shape Sniff", "### 2.")
    assert "record `repo_shape: skills-module`" in sniff
    shape = _paragraph(_quick_section(), "**Skills modules:**")
    for token in ("`repo_shape: skills-module`", "`SKILL.md` frontmatter", "`module-help.csv`", "`module.yaml`",
                  "Key Exports", "`exports` of its `metadata.json`", "Usage Patterns", "scope hint",
                  "`scope=<path>` on a batch line", "stays a library"):
        assert token in shape, token
    for signal in ("`module.yaml`", "`module-help.csv`", "`scope_hint`"):
        assert signal in sniff, signal


def test_quick_skill_batch_refuses_the_single_target_overrides():
    """#609: `--description` and `--exports` never reach every target of a batch.

    The doc gives the exit code and halt reason batch-mode.md raises before the batch starts
    (SKILL.md On Activation step 5 loads it first under `--batch`).
    """
    before = _slice(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    halt = re.search(r"HARD HALT with \*\*exit code (\d+) \(([a-z-]+)\)\*\*", before)
    assert halt, "the --batch refusal halt not found in batch-mode.md"
    code, reason = halt.groups()
    section = _quick_section()
    assert "globally to every target" not in section
    overrides = _slice(section, "**Per-target overrides**", "**Safety:**")
    heading = overrides.splitlines()[0]
    assert "`--skip-snippet` and `--no-active-pointer` also apply to every target in `--batch`" in heading
    for flag in ("--description", "--exports"):
        [row] = [line for line in overrides.splitlines() if line.startswith(f"- `{flag} ")]
        assert row.endswith("Single-target runs only."), row
    refusal = _paragraph(overrides, "`--description` and `--exports` do not combine with `--batch`")
    assert f"exit `{code}` (`{reason}`)" in refusal
    for token in ("before its first target", "writes no batch summary", "run it on its own"):
        assert token in refusal, token
    assert "no batch summary is written" in before


def test_quick_skill_exit_code_map_matches_the_halt_contract():
    """The headless exit-code map in the docs is halt-contract.md's, code for code (exit 2 included)."""
    contract = _slice(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract on HARD HALT")
    doc = _slice(_read(WORKFLOWS), "**Exception: `/skf-quick-skill` headless", "3. **Error-variant result contract")
    expected = _exit_codes(contract)
    assert expected.get("2") == "input-invalid"
    assert _exit_codes(doc) == expected


# --------------------------------------------------------------------------
# Refine Architecture: the derived-scope gate and the Refinement Summary
# --------------------------------------------------------------------------


def test_refine_architecture_documents_the_scope_confirmation():
    """#610: the section describes the gate gap analysis shows for a derived scope, and its headless default."""
    gate = _slice(_read(RA_REFS / "gap-analysis.md"), "**Confirm a derived scope.**", "**Technologies with no skill.**")
    for token in ("Type **C** to keep this scope", "Type skill names to bring them **into** scope",
                  "Type **-skill_name** to take a skill **out** of scope",
                  "keep the derived sets and auto-proceed with [C]",
                  "Pairs, VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for "
                  "awareness only and stay out of the refined document."):
        assert token in gate, token
    section = _ra_section()
    assert "Gap analysis (confirms a derived scope)" in section
    scope = _paragraph(section, "**Scope:**")
    for token in ("`--scope-skills`", "type `C` to keep the scope", "a skill's name to bring it in",
                  "`-<name>` to take it out", "A headless run keeps the derived scope and logs that decision",
                  "VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for awareness "
                  "only and stay out of the refined document"):
        assert token in scope, token


def test_refine_architecture_documents_the_summary_rows_and_next_step():
    """#610: the rows the section names are rows compile writes, and so is the [CS] or [QS] next step."""
    summary = _slice(_read(RA_REFS / "compile.md"), "### 5. Add Refinement Summary Section", "### 6.")
    rows = re.findall(r"^\| ([^|]+?) \| \{", summary, re.M)
    output = _paragraph(_ra_section(), "**Output:**")
    for row in ("Not verified (no skill)", "VS Coverage"):
        assert row in rows, row
        assert f"`{row}`" in output, row
    assert "**[CS] Create Skill** or **[QS] Quick Skill** and re-run **[RA]** first" in summary
    for token in ("`@Ferris CS` or `@Ferris QS`", "run RA again before Stack Skill",
                  "when RA used one", "the document mentions but no skill covers"):
        assert token in output, token


# --------------------------------------------------------------------------
# Skill model: confidence_tier scales, a stack's distribution and where an update records itself
# --------------------------------------------------------------------------


def _validate_output():
    spec = importlib.util.spec_from_file_location("skf_validate_output_user_docs", VALIDATE_OUTPUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tier_verdict(gate, skill_type: str, tier: str) -> str:
    """How the export gate takes `tier` in a `skill_type` skill: accepted, warned or rejected."""
    required, enums, _ = gate({"name": "demo", "version": "1.0.0", "skill_type": skill_type,
                               "source_authority": "community", "exports": ["demo"],
                               "generation_date": "2026-09-30", "confidence_tier": tier})
    if any(issue["field"] == "confidence_tier" for issue in enums):
        return "rejected"
    if any(issue["field"] == "confidence_tier" for issue in required):
        return "warned"
    return "accepted"


def _tiers(words: str) -> list[str]:
    """The names in a list such as "Quick, Forge, Forge+ or Deep"."""
    return re.split(r", | or ", words)


def test_skill_model_gives_confidence_tier_the_export_gate_scales():
    """#552: a single skill holds its forge tier, a stack the dominant confidence tier of its libraries.

    The export gate accepts exactly those scales, and takes a stack's forge tier with a warning.
    """
    paragraph = _paragraph(_read(SKILL_MODEL), "Two fields are easy to mix up.")
    single = re.search(r"holds the forge tier a single skill like this one was compiled at \(([^)]+)\)", paragraph)
    stack = re.search(r"A stack skill records there the dominant confidence tier of its libraries \(([^)]+)\)",
                      paragraph)
    assert single and stack, paragraph
    forge_tiers, stack_tiers = _tiers(single.group(1)), _tiers(stack.group(1))
    gate = _validate_output().validate_metadata_export_gate
    for tier in forge_tiers:
        assert _tier_verdict(gate, "single", tier) == "accepted", tier
        assert _tier_verdict(gate, "stack", tier) == "warned", tier
    for tier in stack_tiers:
        assert _tier_verdict(gate, "stack", tier) == "accepted", tier
        assert _tier_verdict(gate, "single", tier) == "rejected", tier
    assert "keeps its forge tier in `forge_tier`" in paragraph
    assert ("Export Skill still accepts a forge tier from a stack made by an earlier SKF version, with a warning "
            "that running Stack Skill again records the dominant tier") in paragraph
    template = _read(SRC / "skf-create-stack-skill" / "assets" / "stack-skill-template.md")
    assert f'"forge_tier": "{{{"|".join(forge_tiers)}}}"' in template
    assert f'"confidence_tier": "{{{"|".join(stack_tiers)}}}"' in template


def test_skill_model_says_what_a_stack_distribution_counts(tmp_path):
    """#528: a stack's `confidence_distribution` counts each library once, so its bins sum to `library_count`.

    The stack validator checks that sum, so bins that count provenance entries instead are an issue.
    """
    paragraph = _paragraph(_read(SKILL_MODEL), "Two fields are easy to mix up.")
    assert ("In a stack it counts each library once, by the library's tier, so its bins sum to `library_count`."
            in paragraph)
    validate_stack_counts = _validate_output().validate_stack_counts
    meta = {"library_count": 3, "integration_count": 0}
    for bins, fits in (({"t1": 2, "t1_low": 1, "t2": 0, "t3": 0}, True),
                       ({"t1": 15, "t1_low": 7, "t2": 0, "t3": 0}, False)):  # 22 provenance entries, 3 libraries
        issues, _ = validate_stack_counts(tmp_path, {**meta, "confidence_distribution": bins})
        assert any(issue["field"] == "confidence_distribution" for issue in issues) != fits, bins


def test_skill_model_says_where_an_update_records_itself():
    """#548: an update writes `last_update` and `update_type` into provenance-map.json, never into metadata.json."""
    write = _read(UPDATE_WRITE)
    metadata = _slice(write, "### 2. Write Updated metadata.json", "### 3.")
    assert "Write neither key into metadata.json" in metadata
    provenance = _slice(write, "### 3. Write Updated provenance-map.json", "### 4.")
    for key in ('"last_update"', '"update_type"'):
        assert key in provenance, key
    doc = _read(SKILL_MODEL)
    excerpt = _slice(doc, "```json\n{\n  \"name\": \"oms-cognee\"", "\n```\n")
    assert "last_update" not in excerpt and "update_type" not in excerpt
    omitted = _paragraph(doc, "Fields omitted from this excerpt for brevity:")
    for token in ("a `last_update` that an earlier SKF version wrote",
                  "records `last_update` and `update_type` at the top level of `provenance-map.json`",
                  "an update removes both from `metadata.json`", "`generation_date`"):
        assert token in omitted, token


# --------------------------------------------------------------------------
# Troubleshooting and the Ferris page
# --------------------------------------------------------------------------


def test_troubleshooting_names_ferris_install_halts_and_the_installer():
    """#608: Ferris stops on a missing config, or on missing scripts, as setup does, and all name the installer."""
    forger = _read(FORGER_SKILL)
    guard = _slice(forger, "1. **Config guard.**", "\n").replace("**", "")
    scripts = _slice(forger, "2. **Preflight.**", "Otherwise run it once").replace("**", "")
    ki = _slice(forger, "- **KI**:", "\n")
    entry = _slice(_read(TROUBLESHOOTING), '### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"',
                   "\n### ")
    for halt, source in (("Cannot initialize. SKF is not installed in this project", guard),
                         ("Cannot initialize. SKF's scripts are missing from this project", scripts)):
        assert halt in source, halt
        assert f'"{halt}"' in entry, halt
    for command in INSTALLERS:
        for name, text in (("config guard", guard), ("missing scripts", scripts), ("KI", ki),
                           ("troubleshooting", entry)):
            assert command in text, (name, command)
    for token in ("setup reads the file and never writes it, and only the installer does",
                  "start Ferris again and give him SF", "KI says so when the knowledge index is missing",
                  "Ferris names the file and the parser error"):
        assert token in entry, token


def test_agents_doc_lists_the_first_run_paths_ferris_highlights():
    """Ferris's first-run greeting and the Ferris page name the same starting points, in the same order."""
    greeting = _slice(_read(FORGER_SKILL), "5. **Greet, then dispatch or wait.**", "\n")
    paths = BOLD_PATH_RE.findall(_slice(greeting, "On a first run", "Otherwise"))
    assert "forge-auto `<repo-or-doc-url>`" in paths
    doc = _paragraph(_read(AGENTS), "On your first run")
    assert BOLD_PATH_RE.findall(doc) == paths
    assert f"points you to {NUMBER_WORDS[len(paths)]} places to start" in doc


def test_agents_doc_says_what_ws_ends_with():
    """WS lists each skill's stage, then the next code for each skill in flight; the menu row says the same."""
    ws = _slice(_read(FORGER_SKILL), "- **WS**:", "## Pipeline Mode")
    stages = re.search(r"List each skill with its stage (\([^)]+\))", ws)
    assert stages, "WS stage list not found"
    assert "then end with the recommended codes" in ws
    [row] = [line for line in _read(AGENTS).splitlines() if line.startswith("| 17 | WS |")]
    assert f"Show where each skill stands {stages.group(1)}" in row
    assert "the next code to run for each skill in flight" in row


def test_agents_doc_describes_the_second_workflow_offer():
    """A single code picked after another workflow ran first offers a fresh session or a pipeline."""
    dispatch = _slice(_read(FORGER_SKILL), "- **Any other single code**", "\n")
    for token in ("When another workflow already ran in this session", "the command to paste into a fresh session",
                  "the remaining steps chained now as a pipeline", "in place only when the user asks for that"):
        assert token in dispatch, token
    menu = _paragraph(_read(AGENTS), "Ferris shows his menu as a numbered table")
    for token in ("after another workflow already ran in the same session", "the command to paste into a new session",
                  "the remaining steps chained as a pipeline", "runs it in place only if you ask"):
        assert token in menu, token


# --------------------------------------------------------------------------
# Test Skill: gap severities, the hard gate and what a blocked run writes
# --------------------------------------------------------------------------

SEVERITY_ROW_RE = re.compile(r"^\| (Critical|High|Medium|Low|Info)\s+\| `([a-z-]+)`\s+\| (.+?) \|$", re.M)
DOC_SEVERITY_ROW_RE = re.compile(r"^\| \*\*(Critical|High|Medium|Low|Info)\*\* \| (.+) \|$", re.M)
# (phrase in the docs table, category in scoring-rules.md, a word of that category's criteria)
DOC_GAP_EXAMPLES = (
    ("A wrong signature", "signature-mismatch", "Wrong signature"),
    ("or a fabricated one", "fabricated-signature", "Fabricated signature"),
    ("a broken reference in a stack skill", "broken-reference", "Broken reference"),
    ("An inaccurate reference in a stack skill", "inaccurate-reference", "Inaccurate reference"),
    ("a reference whose real path leads outside the skill", "reference-escape", "real path leaves the skill"),
    ("a split-body mismatch", "split-body-mismatch", "document one export differently"),
    ("stats that count every export as documented", "numerator-inflation", "`stats.exports_documented`"),
    ("a missing required section, an unbalanced code fence", "structural", "a missing required section"),
    ("A missing export", "missing-export", "Missing export"),
    ("stale documentation", "stale-documentation", "not a fabricated signature"),
    ("an incomplete integration pattern in a stack skill", "integration-pattern", "Incomplete integration pattern"),
    ("a code fence with no language tag", "structural", "without a language tag"),
    ("a provenance line that is not the definition line", "provenance-line", "not the definition of an export"),
    ("discovery testing not performed", "discovery", "Discovery testing not performed"),
)


def _severity_rows() -> list[tuple[str, str, str]]:
    """(severity, category, criteria) for each row of scoring-rules.md's Gap Severity table."""
    table = _tail(_read(SCORING_RULES), "## Gap Severity")
    rows = SEVERITY_ROW_RE.findall(table)
    assert len(rows) > 20, "Gap Severity rows not found"
    return rows


def _doc_severities() -> dict[str, str]:
    table = _slice(_read(VERIFYING), "### Gap severities", "### Score report output")
    rows = dict(DOC_SEVERITY_ROW_RE.findall(table))
    assert list(rows) == ["Critical", "High", "Medium", "Low", "Info"], list(rows)
    return rows


def _severity_of(category: str, criteria: str) -> str:
    [severity] = [s for s, c, text in _severity_rows() if c == category and criteria in text]
    return severity


def test_docs_gap_table_rates_each_example_as_scoring_rules_does():
    """#583, #545: each gap the docs table names sits in the row of the severity the Gap Severity table gives it."""
    doc = _doc_severities()
    for phrase, category, criteria in DOC_GAP_EXAMPLES:
        severity = _severity_of(category, criteria)
        assert phrase in doc[severity], (phrase, severity)
        others = [name for name, row in doc.items() if name != severity and phrase in row]
        assert not others, (phrase, others)


def test_docs_gap_table_names_every_blocking_category():
    """Every Critical and High category the hard gate blocks on has an example in the docs table.

    Discovery runs after the gate, so its High row blocks nothing, and the note under the table says so.
    """
    documented = {(category, _severity_of(category, criteria)) for _, category, criteria in DOC_GAP_EXAMPLES}
    blocking = {(category, severity) for severity, category, _ in _severity_rows()
                if severity in ("Critical", "High") and category != "discovery"}
    assert blocking <= documented, sorted(blocking - documented)
    discovery = {severity for severity, category, _ in _severity_rows() if category == "discovery"}
    assert discovery == {"High", "Medium", "Info"}
    assert "Discovery testing runs after the gate" in _read(SCORING_RULES)
    severities = _slice(_read(VERIFYING), "### Gap severities", "### Score report output")
    assert "blocks a run on any Critical or High gap, before scoring" in _read(SCORING_RULES)
    assert "Critical and High gaps found before scoring block the run at the [hard gate](#hard-gate)" in severities
    note = _paragraph(severities, "Discovery testing")
    assert "a discovery gap (Info, Medium or High) is counted in the Gap Report and blocks nothing" in note


def test_docs_say_a_signature_mismatch_and_a_missing_export_as_test_skill_rates_them():
    """A signature mismatch is Critical and blocks; a missing export is Medium and only lowers the score."""
    assert _severity_of("signature-mismatch", "Wrong signature") == "Critical"
    assert _severity_of("missing-export", "Missing export") == "Medium"
    verifying = _read(VERIFYING)
    assert "rates a signature mismatch as a Critical gap, which stops the test at its [hard gate](#hard-gate)" \
        in verifying
    assert "High-severity gap" not in verifying
    gate = _paragraph(_slice(verifying, "### Hard gate", "### Pass/fail"), "Before scoring")
    assert "a missing export, for example, is Medium, so it lowers Export Coverage" in gate
    forge_auto = _read(FORGE_AUTO)
    assert "A missing export is a Medium gap, so it lowers the score and blocks nothing on its own." in forge_auto
    assert "Any Critical or High gap, such as a wrong or fabricated signature, also stops the pipeline at TS" \
        in forge_auto
    hard = [line for line in _read(CAMPAIGN_DOC).splitlines()
            if line.startswith("- **Hard gate** (`zero-critical-high`)")]
    assert len(hard) == 1
    for token in ("such as a wrong or fabricated signature or a broken reference",
                  "A missing export does not trip this gate: Test Skill rates it Medium",
                  "(/docs/verifying-a-skill.md#gap-severities)"):
        assert token in hard[0], token


def test_docs_say_what_the_hard_gate_reads_and_a_blocked_run_writes():
    """The gate reads the gap ledger; a blocked run writes its Gap Report and FAIL record, then exits 2."""
    front = yaml.safe_load(_read(HARD_GATE).split("---")[1])
    ledger = front["ledgerFile"].rsplit("/", 1)[1]
    assert ledger == "test-findings-{run_id}.json"
    gate = _paragraph(_slice(_read(VERIFYING), "### Hard gate", "### Pass/fail"), "Before scoring")
    for token in (f"`{ledger}`", "reads the run's gap ledger", "It writes the Gap Report, with the blocking gaps first",
                  "a FAIL result record whose `halt_reason` is `hard-gate-blocked`",
                  "runs the `on_complete` hook and the health check, then exits with code 2",
                  "`@Ferris US <name> --from-test-report`"):
        assert token in gate, token
    # The headless contract lives in references/invocation-contract.md (#600).
    skill = _read(TEST_SKILL / "references" / "invocation-contract.md")
    [row] = [line for line in skill.splitlines() if re.match(r"\| 2 +\| fail / FAIL ", line)]
    assert '`halt_reason: "hard-gate-blocked"`' in row
    assert "which still writes the Gap Report and its FAIL result contract" in skill
    exits = _paragraph(_slice(_read(WORKFLOWS), "### Test Skill (TS)", "**Agent:**"), "**Verdicts and exit codes")
    for token in ("`2` FAIL", "A run the hard gate blocks on a Critical or High gap is a FAIL as well",
                  "writes the Gap Report and a FAIL result record", "runs `on_complete` and the health check",
                  "then exits `2`", "its result line, printed on stderr instead of stdout",
                  '`status: "error"`', '`halt_reason: "hard-gate-blocked"`'):
        assert token in exits, token
    contract = _slice(skill, "## Result Envelope (Headless)", "| `halt_reason` | Raised by |")
    assert "on stdout and a halt's or a blocked run's on stderr" in contract and "hard gate blocked" in contract
    tree = _slice(_read(ARCHITECTURE), "## Workspace Artifacts", "### Pipeline Result Contracts")
    assert f"├── {ledger}" in tree


# --------------------------------------------------------------------------
# Tool minimums: setup's tier, the CLI tool report and the setup flags
# --------------------------------------------------------------------------


def _ast_grep_minimum() -> str:
    tools = yaml.safe_load(_read(SRC / "shared" / "tool-requirements.yaml"))["tools"]
    assert tools["ast_grep"]["kind"] == "tier"
    return tools["ast_grep"]["minimum"]


def test_docs_hold_a_tier_tool_to_its_minimum():
    """#577: a tier tool below its minimum counts toward no tier, so an old ast-grep leaves you at Quick."""
    older = f"an ast-grep older than {_ast_grep_minimum()} leaves you at Quick"
    detect = _read(SRC / "skf-setup" / "references" / "detect-and-tier.md")
    assert "A tier tool below its minimum version binds `false` here, like a missing one" in detect
    assert "tool_below_minimum: " in _read(SRC / "shared" / "scripts" / "skf-emit-result-envelope.py")
    purpose = _paragraph(_slice(_read(WORKFLOWS), "### Setup Forge (SF)", "**Agent:**"), "**Purpose:**")
    for token in ("counts only at its minimum version or newer", older, "an upgrade line in FORGE STATUS",
                  "a `tool_below_minimum` warning in `SKF_SETUP_RESULT_JSON`", "src/shared/tool-requirements.yaml"):
        assert token in purpose, token
    started = _read(GETTING_STARTED)
    assert started.count(older) == 2  # step 1 of "Your first skill" and the prerequisites
    report = _slice(started, "### The tool report", "\n---\n")
    for token in (f"With an ast-grep older than {_ast_grep_minimum()}, `@Ferris SF` leaves you at Quick",
                  "a `tool_below_minimum` warning", "never lowers your tier"):
        assert token in report, token
    assert "detects which ones you have and their versions" in started


def test_getting_started_names_the_statuses_the_tool_report_prints():
    """Every status the docs list is a label tool-check.js prints, and the report follows install, update and status."""
    check = _read(REPO_ROOT / "tools" / "cli" / "lib" / "tool-check.js")
    for label in ("'ok'", "`upgrade to >= ${row.minimum}`", "'missing'", "'installed, version unknown'",
                  "`optional, ${tiers[0]} tier`"):
        assert label in check, label
    report = _slice(_read(GETTING_STARTED), "### The tool report", "\n---\n")
    for token in ("`ok`", "`upgrade to >= <minimum>`", "`missing`", "`optional`", "`installed, version unknown`",
                  "never changes the command's exit code", "never runs `npx`",
                  "upgrade to >= " + _ast_grep_minimum()):
        assert token in report, token
    commands = _slice(_read(GETTING_STARTED), "### Other installer commands", "### The tool report")
    update = next(line for line in commands.splitlines() if "skill-forge@latest update" in line)
    assert "It then prints the [tool report](#the-tool-report), followed by the update notice" in update
    status = next(line for line in commands.splitlines() if "skill-forge status" in line)
    for token in ("the tools the last setup detected. Below them it prints the [tool report](#the-tool-report)",
                  "each tool installed now against its minimum version, with the command that upgrades it",
                  "and then the output folders"):
        assert token in status, token
    status_js = _read(REPO_ROOT / "tools" / "cli" / "commands" / "status.js")
    assert status_js.index("await printToolReport();") < status_js.index("'  Output Folders'")
    for command in ("install", "update", "status"):
        assert "startToolCheck" in _read(REPO_ROOT / "tools" / "cli" / "commands" / f"{command}.js"), command


def test_setup_flag_lines_name_the_halts_setup_raises():
    """#594: a mistyped tier or orphan action halts, and `--quiet` is an alias of `--headless`."""
    skill = _read(SRC / "skf-setup" / "SKILL.md")
    for token in ("`--quiet` (an alias of `--headless`", "`--require-tier <tier>`", "`step 1:detect-tools`",
                  "on-activation:orphan-action-invalid"):
        assert token in skill, token
    lines = _slice(_read(WORKFLOWS), "### Setup Forge (SF)", "**Agent:**").splitlines()
    require = next(line for line in lines if line.startswith("- `--require-tier="))
    for token in ("(or `--require-tier <tier>`)", "one of the four tier names exactly", "is no miss",
                  "`blocked` with `error.phase` `step 1:detect-tools`"):
        assert token in require, token
    orphan = next(line for line in lines if line.startswith("- `--orphan-action="))
    assert "Any other value halts the run before setup does anything (`error.phase` " \
           "`on-activation:orphan-action-invalid`)" in orphan
    quiet = next(line for line in lines if line.startswith("- `--quiet`"))
    assert "an alias of `--headless`" in quiet and "`quiet-default`" in quiet


# --------------------------------------------------------------------------
# Verify Stack and Refine Architecture: the verdicts and the report lookup
# --------------------------------------------------------------------------


def _rollup():
    path = SRC / "skf-verify-stack" / "scripts" / "skf-verdict-rollup.py"
    spec = importlib.util.spec_from_file_location("skf_verdict_rollup_user_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.rollup


def _counts(**overrides) -> dict:
    counts = {"coveragePercentage": 100, "missingCount": 0, "coveredCount": 2, "replacedCount": 0,
              "pairsBlocked": 0, "pairsRisky": 0, "pairsPlausible": 0, "pairsVerified": 0}
    return {**counts, **overrides}


def test_docs_give_the_verdicts_the_rollup_returns():
    """#590, #599: no pair between covered technologies is CONDITIONALLY_FEASIBLE, and a vacuous run finishes."""
    rollup = _rollup()
    zero_pairs = rollup(_counts())
    assert zero_pairs["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert "zero-integration-pairs" in zero_pairs["matchedConditions"]
    assert rollup(_counts(pairsVerified=1))["overallVerdict"] == "FEASIBLE"
    for counts in (_counts(coveragePercentage=0, coveredCount=0, missingCount=2), _counts(pairsBlocked=1)):
        assert rollup(counts)["overallVerdict"] == "NOT_FEASIBLE", counts
    exits = _read(SRC / "skf-verify-stack" / "references" / "exit-codes.md")
    assert "analysis-halted" not in exits and not re.search(r"^\| 8 ", exits, re.M)
    integrations = _read(SRC / "skf-verify-stack" / "references" / "integrations.md")
    for token in ("**Source preference:** If a stack skill assembled by `skf-create-stack-skill` is present in the "
                  "inventory and its manifest", "declares `integration_patterns`, use THAT as the primary source",
                  "Fall back to prose co-mention (below) only when no such manifest is available",
                  "do not parse Mermaid diagram syntax for co-mention detection"):
        assert token in integrations, token
    verdicts = _paragraph(_slice(_read(WORKFLOWS), "### Verify Stack (VS)", "**Agent:**"), "**Verdicts:**")
    for token in ("every integration pair is `Verified`",
                  "VS takes integration pairs from a stack skill's `integration_patterns` when one built by Stack "
                  "Skill (SS) is in the inventory", "and otherwise from the architecture document's prose, never "
                  "from a Mermaid diagram", "finds no pair between two or more covered technologies",
                  "ends `CONDITIONALLY_FEASIBLE`", "A weak result never stops VS early", "finishes `NOT_FEASIBLE`"):
        assert token in verdicts, token
    assert "only from the architecture document's prose" not in verdicts
    synergy = _paragraph(_read(SYNERGY), "**What flows back:** A feasibility report")
    for token in ("A pair is Verified only when one of its two skills cites the other",
                  "VS takes the pairs from a stack skill's `integration_patterns` when one is in the inventory, and "
                  "otherwise from your document's prose, never from a Mermaid diagram",
                  "the verdict is CONDITIONALLY_FEASIBLE", "VS finishes its report, with NOT_FEASIBLE"):
        assert token in synergy, token


def test_refine_architecture_documents_the_report_lookup_and_its_halt():
    """RA offers the newest [VS] report it finds, and stops with exit 2 on a report that breaks the contract."""
    init = _read(RA_REFS / "init.md")
    for token in ("--locate", "the `-latest` report", "press Enter to use it",
                  "`--vs-report-path none` answers the report question", 'halt_reason: "input-invalid"',
                  "a `schemaVersion` other than `1.0`", "a second verdict table", "`unknownTokens`"):
        assert token in init, token
    lookup = _paragraph(_ra_section(), "**Feasibility report:**")
    for token in ("`feasibility-report-<slug>-latest.md`", "press Enter to use it",
                  "A headless run uses it and logs that it did", "`--vs-report-path none` to refine without one",
                  "exit `2` (`input-invalid`)"):
        assert token in lookup, token
    [line] = [line for line in _read(WORKFLOWS).splitlines()
              if line.startswith("- **`/skf-refine-architecture` (RA)**")]
    assert ("(`input-invalid` also covers a Verify Stack report with a `schemaVersion` other than `1.0`, a missing or "
            "doubled verdict table, or an unknown verdict token)") in line


# --------------------------------------------------------------------------
# Update, Export, Drop and Audit lines
# --------------------------------------------------------------------------


def test_docs_describe_the_unconsumed_test_report_offer():
    """A plain update offers an unconsumed failing report; a headless one warns `unconsumed-test-report`."""
    init = _read(SRC / "skf-update-skill" / "references" / "init.md")
    for token in ("### 4b. Offer an Unconsumed Test Report", "`testResult` is `fail` or `pass-with-drift`",
                  "- **[G]:**", "- **[S]:**", "add `unconsumed-test-report: {unconsumed_test_report}`"):
        assert token in init, token
    modes = _paragraph(_slice(_read(WORKFLOWS), "### Update Skill (US)", "**Agent:**"), "**Modes:**")
    for text in (modes, _read(FORGE_AUTO)):
        for token in ("a failed or pass-with-drift", "newer than the skill", "no repair has applied", "(`[G]`)",
                      "(`[S]`)", "a headless run checks the source and adds an `unconsumed-test-report` warning"):
            assert token in text, token
    assert "routes each gap by its category, so a missing export" in modes
    assert "does not read the test report" not in _read(FORGE_AUTO)


def test_export_line_names_the_test_warnings_and_the_snippet_timing():
    """Export warns on an inconclusive or drift-only pass and writes each snippet last."""
    load = _read(SRC / "skf-export-skill" / "references" / "load-skill.md")
    assert "- `pass-with-drift`: warn" in load and "- `inconclusive`: warn" in load
    timing = _slice(_read(SRC / "skf-export-skill" / "SKILL.md"), "- **Snippet timing:**", "\n")
    assert "as step 4's last write" in timing and "as it was" in timing
    update_context = _read(SRC / "skf-export-skill" / "references" / "update-context.md")
    assert "a run with passive context off has none" in update_context
    good = _paragraph(_slice(_read(WORKFLOWS), "### Export Skill (EX)", "**Agent:**"), "**Good to know:**")
    for token in ("its last test was inconclusive or passed only under `--allow-workspace-drift`",
                  "With passive context on (the default), it writes each skill's `context-snippet.md` last",
                  "a cancelled or halted export leaves the snippet as it was",
                  "`passive_context: false`", "such a run writes no snippet"):
        assert token in good, token


def test_drop_lines_give_the_version_rule_and_the_envelope_fields():
    """A headless manifest drop needs `version`; a draft takes no single version; the envelope fields exist."""
    select = _read(SRC / "skf-drop-skill" / "references" / "select.md")
    assert "With no `version` argument, headless mode HALTs (exit code 2, `halt_reason: \"input-missing\"`" in select
    assert "HALT (exit code 2, `halt_reason: \"input-invalid\"`, phase `select:scope`) in either mode" in select
    safety = _paragraph(_slice(_read(WORKFLOWS), "### Drop Skill (DS)", "**Agent:**"), "**Safety:**")
    for token in ("needs `version=all` or the one version to drop",
                  "exit `2` (`input-missing`) before it changes anything",
                  "A specific version for a draft skill", "exit `2` (`input-invalid`) in every mode"):
        assert token in safety, token
    schema = json.loads(_read(SCHEMAS / "skf-drop-skill-result-envelope.v1.json"))
    [line] = [line for line in _read(WORKFLOWS).splitlines() if line.startswith("- **`/skf-drop-skill` (DS)**")]
    for field in ("would_delete", "result_path", "error"):
        assert field in schema["properties"], field
        assert f"`{field}` (" in line, field


def test_audit_section_names_the_version_it_reads_and_its_data_folder():
    """The audit reads the `active` link's version unless [M] is picked, and keeps its JSON per run."""
    init = _read(SRC / "skf-audit-skill" / "references" / "init.md")
    assert "**[M] Audit the manifest's version ({active_version})**" in init
    front = yaml.safe_load(_read(SRC / "skf-audit-skill" / "references" / "report.md").split("---")[1])
    assert front["auditDataFolder"] == "{forge_version}/.skf-audit/{timestamp}"
    section = _slice(_read(WORKFLOWS), "### Audit Skill (AS)", "**Agent:**")
    version = _paragraph(section, "**Version read:**")
    assert "the version the skill's `active` link names" in version and "offers `[M]`" in version
    output = _paragraph(section, "**Output:**")
    assert "`forge-data/<name>/<version>/.skf-audit/<timestamp>/`" in output
    drift = _paragraph(section, "**Doc drift:**")
    assert "`blob/main` page" in drift and "records the raw README at the ref the skill was built from" in drift
    assert "├── .skf-audit/{timestamp}/" in _slice(_read(ARCHITECTURE), "## Workspace Artifacts",
                                                   "### Pipeline Result Contracts")


def test_verifying_lists_create_skill_private_source_tree():
    """Create Skill reads a remote source at the resolved commit and moves SKF's clone there, or says why not."""
    extract = _read(SRC / "skf-create-skill" / "references" / "extract.md")
    assert "--update-clone" in extract and "this run skips ccc discovery and the ccc index registration" in extract
    enforcement = _slice(_read(VERIFYING), "### Workflow-time enforcement", "\n---\n")
    [bullet] = [line for line in enforcement.splitlines() if line.startswith("- **Create Skill (`@Ferris CS`)**")]
    for token in ("at Forge tier and above", "private checkout", "`source_commit`",
                  "moves SKF's shared clone of the repository to the same commit",
                  "skips ccc discovery and the ccc index registration"):
        assert token in bullet, token
    assert enforcement.index("- **Create Skill") < enforcement.index("- **Update Skill (`@Ferris US`)**")


# --------------------------------------------------------------------------
# Quick Skill: the success envelope and the batch exit rule
# --------------------------------------------------------------------------


def test_quick_skill_headless_block_names_the_success_envelope():
    """Four contracts; the success line's summary fields are the schema's, and the batch rule is batch-mode.md's."""
    block = _slice(_read(WORKFLOWS), "**Exception: `/skf-quick-skill` headless", "**Exception: `/skf-brief-skill`")
    items = re.findall(r"^(\d)\. \*\*", block, re.M)
    assert items == ["1", "2", "3", "4"]
    assert f"{NUMBER_WORDS[len(items)].capitalize()} operational contracts" in block
    schema_path = "src/shared/scripts/schemas/skf-quick-skill-result-envelope.v1.json"
    schema = json.loads(_read(REPO_ROOT / schema_path))
    third = _slice(block, "3. **Error-variant result contract", "4. **Success result contract.**")
    assert f"[`{schema_path}`]" in third and "§ \"Result Contract on HARD HALT\"" in third
    fourth = _slice(block, "4. **Success result contract.**", "**Batch mode")
    for field in ("quality_score", "validation_issues", "repo_shape", "language_resolution", "active_pointer"):
        assert field in schema["properties"]["summary"]["properties"], field
        assert f"`{field}`" in fourth, field
    for field in ("headless_decisions", "warnings"):
        assert field in schema["properties"], field
        assert f"`{field}`" in fourth, field
    assert "`also_found_in`" in fourth and "not a Test Skill score" in fourth
    assert "`quick-skill-result-latest.json`" in fourth
    rule = _tail(_read(BATCH_MODE), "## Exit code")
    assert "otherwise the highest exit code among the failed targets" in rule
    batch = _paragraph(block, "**Batch mode (`--batch <file>`).**")
    for token in ("each target runs steps 1 to 6", "the health check runs once, after the batch summary",
                  "the highest exit code among its failed targets (`0` when none failed)",
                  "`--fail-fast` stops it at the first failed target", "writes no summary and exits `2`, or `4`"):
        assert token in batch, token


# --------------------------------------------------------------------------
# Campaign: Setup's one question, the brief and the persistent facts
# --------------------------------------------------------------------------


def _kickoff():
    path = SRC / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
    spec = importlib.util.spec_from_file_location("campaign_render_kickoff_user_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_setup_asks_one_question_and_drafts_the_table():
    """Setup opens with one question for the targets, shows one draft table and asks only what is missing."""
    setup = _read(SRC / "skf-campaign" / "references" / "step-01-setup.md")
    doc = _read(CAMPAIGN_DOC)
    asks = _slice(doc, "### What Setup Asks For", "To skip these questions")
    for token in ("in whatever form you have them", "a manifest or `campaign-brief.yaml` path", "a pasted list",
                  "repository URLs"):
        assert token in setup and token in asks, token
    for token in ("open with this one question", "Show the drafted campaign once for correction",
                  "ask only about what is still missing or ambiguous"):
        assert token in setup, token
    for token in ("opens with one question", "shows it once for you to correct",
                  "asks only about what is still missing or ambiguous"):
        assert token in asks, token
    for gone in ("improvement queue", "health findings"):
        assert gone not in doc, gone
    brief = _paragraph(doc, "A machine-readable summary of the campaign")
    assert "any language or scope hint its source gave" in brief
    assert "plus every other field its source gave it (a language or scope hint, for example)" in setup


def test_campaign_persistent_facts_line_follows_the_kickoff_loader(tmp_path):
    """A `file:` path that names no file stops the kickoff; a glob that matches nothing adds nothing."""
    kickoff = _kickoff()
    with pytest.raises(FileNotFoundError):
        kickoff.load_facts(["file:{project-root}/no-such-facts.md"], str(tmp_path))
    assert kickoff.load_facts(["file:{project-root}/**/no-such-*.md"], str(tmp_path)) == []
    loop = _read(SRC / "skf-campaign" / "references" / "step-05-skill-loop.md")
    assert "on any other code, HALT (exit code 2, `invalid-input`)" in loop
    [line] = [line for line in _read(CAMPAIGN_DOC).splitlines() if line.startswith("- **`persistent_facts`**")]
    for token in ("A `file:` path with no glob character that names no file stops the campaign at its first Tier A "
                  "kickoff with exit code 2", "a glob that matches nothing adds nothing"):
        assert token in line, token
