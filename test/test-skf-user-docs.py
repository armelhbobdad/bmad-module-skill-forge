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
  success envelope and batch rule, and the campaign kickoff's facts loader;
- workflows.md, forge-auto.md, agents.md and architecture.md link only to
  source files and sections that exist, and say what each workflow's
  contract does: the pipeline gate, journal and resume, the registry lookup
  and hints, the brief lookup and batch, the stack inputs, the audit's
  upstream and baseline rules, the test exit code, the rename lock, the
  export snippet root, and only settings a customize.toml holds.
- the same pages say that every workflow and Ferris run the customization
  resolver through uv and warn when it cannot run, that a `!` entry drops
  the persistent_facts default, which arrays Ferris's own override file
  adds, how each workflow calls on_complete, and that a chain asks for its
  first workflow's input or halts headless as parse-pipeline.py's
  first_input reports it, and that every pipeline example parses as
  runnable; and workflows.md says what a required-tier miss skips, when an
  audit stops at its baseline, and which warnings a drop can carry.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tomllib
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
    template = _read(SRC / "skf-create-stack-skill" / "assets" / "metadata-contract.md")
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
    entry = _slice(_read(TROUBLESHOOTING), '### "Setup cannot proceed: the SKF config file was not found"',
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
    greeting = _slice(_read(FORGER_SKILL), "6. **Greet, then dispatch or wait.**", "\n")
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
                  "has `exit_code` `2`", "its result line, printed on stderr instead of stdout",
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
    # The flag rows moved to the lifted Invocation Contract (#600); the halt stays in SKILL.md.
    contract = _read(SRC / "skf-setup" / "references" / "invocation-contract.md")
    for token in ("`--quiet` (an alias of `--headless`", "`--require-tier <tier>`", "`step 1:detect-tools`"):
        assert token in contract, token
    assert "on-activation:orphan-action-invalid" in _read(SRC / "skf-setup" / "SKILL.md")
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
    # No SKF producer writes a stack manifest's `integration_patterns` (a stack's metadata.json carries
    # `integration_pairs`, and the inventory no integration field), so the pairs come from prose alone.
    integrations = _read(SRC / "skf-verify-stack" / "references" / "integrations.md")
    for token in ("**Prose co-mention:** step 2's mentions run already found the candidate pairs.",
                  "draws them only in fenced code, such as a Mermaid diagram, which the mentions helper never reads"):
        assert token in integrations, token
    for gone in ("**Source preference:**", "(fallback only)", "stack manifest", "`source: prose co-mention`"):
        assert gone not in integrations, gone
    verdicts = _paragraph(_slice(_read(WORKFLOWS), "### Verify Stack (VS)", "**Agent:**"), "**Verdicts:**")
    for token in ("every integration pair is `Verified`",
                  "VS takes integration pairs from the architecture document's prose, never from a Mermaid diagram.",
                  "finds no pair between two or more covered technologies",
                  "ends `CONDITIONALLY_FEASIBLE`", "A weak result never stops VS early", "finishes `NOT_FEASIBLE`"):
        assert token in verdicts, token
    synergy = _paragraph(_read(SYNERGY), "**What flows back:** A feasibility report")
    for token in ("A pair is Verified only when one of its two skills cites the other",
                  "VS takes the pairs from your document's prose, never from a Mermaid diagram",
                  "the verdict is CONDITIONALLY_FEASIBLE", "VS finishes its report, with NOT_FEASIBLE"):
        assert token in synergy, token
    for text in (integrations, verdicts, synergy):
        assert "integration_patterns" not in text


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
    """A `file:` path that names no file stops the kickoff; a glob that matches nothing adds nothing.

    The line also says how an override drops the bundled default (#596, the maintainer's 2026-10-02 decision): a
    `!` entry naming the default exactly as customize.toml's persistent_facts array holds it.
    """
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
    default = "file:{project-root}/**/project-context.md"
    assert tomllib.loads(_read(SRC / "skf-campaign" / "customize.toml"))["workflow"]["persistent_facts"] == [default]
    for token in (f'`persistent_facts = ["!{default}"]`', "a team or personal override",
                  "an entry that starts with `!` adds nothing and removes every earlier entry it names",
                  "those files stay out of every Tier A kickoff"):
        assert token in line, token


# --------------------------------------------------------------------------
# Provenance labels follow the tool (the #556 pre-release docs drift fix):
# the label rule, the tier text, the receipts and the oms-cognee example
# --------------------------------------------------------------------------

CONCEPTS = DOCS / "concepts.md"
EXAMPLES = DOCS / "examples.md"
HOW_IT_WORKS = DOCS / "how-it-works.md"
INDEX = DOCS / "index.md"
README = REPO_ROOT / "README.md"
METADATA_STATS = SRC / "shared" / "scripts" / "skf-render-metadata-stats.py"
COMPUTE_SCORE = TEST_SKILL / "scripts" / "compute-score.py"
CAMPAIGN = SRC / "skf-campaign"
LABEL_TABLE = "Provenance label differences (not drift)"
AST_RECEIPT = "[AST:cognee/api/v1/search/search.py:L27]"
SCORE_CATEGORIES = ("exportCoverage", "signatureAccuracy", "typeCoverage", "coherence", "externalValidation")


def _script(path: Path):
    """The module of a script whose file name has hyphens."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_") + "_user_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score(threshold: int, score: int, tooling: str = "ok") -> dict:
    """compute-score.py's verdict for a Deep contextual run scoring `score` in every category."""
    return _script(COMPUTE_SCORE).compute_score({
        "mode": "contextual", "tier": "Deep", "threshold": threshold, "toolingStatus": tooling,
        "scores": dict.fromkeys(SCORE_CATEGORIES, score)})


def test_verifying_example_entry_carries_the_labels_its_tool_implies():
    """The step 2 entry passes the label check; the published entry the page describes is flagged by it.

    The checks bullet the step links to describes that label check and the relabel Create Skill applies.
    """
    step = _slice(_read(VERIFYING), "### 2. Open the skill's `provenance-map.json`", "### 3. ")
    entry = json.loads(_slice(step, "```json\n", "```\n")[len("```json\n"):])
    check = _script(METADATA_STATS).check_label_agreement
    assert (entry["extraction_method"], entry["confidence"], entry["source_line"]) == ("ast-grep", "T1", 27)
    assert check({"entries": [entry]}) == []
    assert [v["expected"] for v in check({"entries": [{**entry, "ast_node_type": None}]})] == ["non-null"]
    published = {**entry, "extraction_method": "source-read", "source_line": 26}
    expected = {v["field"].rsplit(".", 1)[1]: v["expected"] for v in check({"entries": [published]})}
    assert expected == {"confidence": "T1-low", "signature_source": "T1-low", "ast_node_type": None}, expected
    for token in ("`[AST:file:Lnn]` for an export ast-grep matched or `[SRC:file:Lnn]` for one read by eye",
                  "gets `T1-low`, `source-read`, no node kind and an `[SRC:]` citation, at every forge tier",
                  "It records `search` as `source-read` but labels it `T1`",
                  "points at line 26, the blank line above the definition", f"cites `{AST_RECEIPT}`",
                  "a source read is `T1-low` with an `[SRC:]` citation, and its line is 27, the `def` line",
                  "[line, label and citation checks](#workflow-time-enforcement)"):
        assert token in step, token
    relabel = _read(SRC / "skf-create-skill" / "references" / "relabel-rule.md")
    assert ("Set the entry's `confidence`, `signature_source` and `ast_node_type` to the violation's `expected`"
            in relabel)
    bullet = "- **Line, label and citation checks.**"
    [checks] = [line for line in _read(VERIFYING).splitlines() if line.startswith(bullet)]
    for token in ("an ast-grep entry is `T1` with a node kind",
                  "an entry read by eye is `T1-low` with no node kind and a `signature_source` other than `T1`",
                  "They relabel an entry that disagrees, so a source read labeled `T1` becomes `T1-low`"):
        assert token in checks, token


def test_docs_say_labels_follow_the_tool_and_t1_counts_drop():
    """A label names the tool that read the export, at every tier, and Audit Skill lists label changes apart."""
    assert "The label follows the tool that produced the claim, not the forge tier" in _read(
        SRC / "knowledge" / "confidence-tiers.md")
    audit = SRC / "skf-audit-skill" / "references"
    # Step 3 writes the table, by hand or through its renderer script once one ships.
    renderer = SRC / "skf-audit-skill" / "scripts" / "render-drift-tables.py"
    assert LABEL_TABLE in _read(audit / "structural-diff.md") + (_read(renderer) if renderer.exists() else "")
    assert f"**{LABEL_TABLE}** table) is never a finding" in _read(audit / "severity-classify.md")
    concepts = _paragraph(_read(CONCEPTS), "**The label follows the tool, not the tier.**")
    model = _paragraph(_read(SKILL_MODEL), "**Labels follow the tool that read each export, not the forge tier.**")
    for text in (concepts, model):
        for token in (f'"{LABEL_TABLE}"', "with nothing less extracted",
                      "Before SKF 3.0.0 the label followed the forge tier"):
            assert token in text, token
    for token in ("an ast-grep match is T1 at any tier", "an export read by eye is T1-low, even in a Deep-tier skill",
                  "fewer T1 claims", "does not count them as drift"):
        assert token in concepts, token
    methods = re.findall(r"`([a-z-]+)`", model.split("`extraction_method` (", 1)[1].split(")", 1)[0])
    assert methods == ["ast-grep", "source-read"]
    assert set(methods) <= set(_script(METADATA_STATS)._KNOWN_METHODS)
    for token in ("Expect lower T1 counts", "`confidence_distribution`", "never counts it as drift"):
        assert token in model, token
    drift = _paragraph(_read(CONCEPTS), "Audit Skill also checks the documentation pages")
    assert f'(T1 to T1-low, or back): Audit Skill lists it under "{LABEL_TABLE}"' in drift
    excerpt = _paragraph(_read(SKILL_MODEL), "The excerpt's `t1` count of 34")
    assert '"t1": 34' in _read(SKILL_MODEL) and "which SKF 3.0.0 counts as `t1_low`" in excerpt
    assert "Set `ast_node_count` to the number of exports ast-grep matched" in _read(
        SRC / "skf-create-skill" / "references" / "compile.md")
    assert '"ast_node_count": 34' in _read(SKILL_MODEL) and "`ast_node_count` counts only those exports" in excerpt


def test_tier_text_promises_t1_only_for_an_ast_grep_match():
    """No tier makes every signature T1 and `[AST:]`: an export ast-grep cannot match stays T1-low at any tier."""
    rule = _read(SRC / "skf-create-skill" / "references" / "tier-degradation-rules.md")
    assert "Label the export by the tool that produced it, not by the tier" in rule
    model, examples, trouble, concepts = (_read(p) for p in (SKILL_MODEL, EXAMPLES, TROUBLESHOOTING, CONCEPTS))
    [forge] = [line for line in model.splitlines() if line.startswith("| **Forge** |")]
    assert "T1 confidence" not in forge
    assert ("Each export an ast-grep rule matches is AST-verified and labeled T1; one it cannot match is read by eye "
            "and labeled T1-low") in forge
    assert "an export it could not match is labeled T1-low and cited `[SRC:...]`, even in a Deep-tier skill" in model
    for stale, text in (("Every signature must be AST-verified", examples),
                        ("Every signature carries `[AST:file:Lnn]` at T1", examples),
                        ("for AST-verified signatures (T1 confidence)", trouble),
                        ("Every parameter and location is AST-verified", concepts),
                        ("| Structural (AST-verified) |", model)):
        assert stale not in text, stale
    scenario = _slice(examples, "### Scenario G:", "### Scenario H:")
    assert "An export it could not match is read by eye and carries `[SRC:file:Lnn]` at T1-low" in scenario
    quick = _slice(trouble, "### Quick-tier skills have lower confidence scores", "\n### ")
    assert "The label follows the tool that read the export, not the tier" in quick
    assert "one it cannot match is read by eye and stays T1-low" in _slice(concepts, "- **Forge:**", "\n")


def test_receipt_pages_say_ast_means_an_ast_grep_match():
    """Each page that shows the `search` receipt says `[AST:]` is an ast-grep match and `[SRC:]` a read by eye."""
    pages = {
        README: "its provenance map records `search` as read by eye, which SKF 3.0.0 cites as `[SRC:...]`",
        GETTING_STARTED: "an export SKF read by eye instead carries an `[SRC:...]` receipt",
        HOW_IT_WORKS: "An export ast-grep cannot match is read by eye and carries an `[SRC:...]` receipt instead",
        INDEX: "the receipt says so: `[SRC:...]`",
        EXAMPLES: "that record lists these functions as read by eye (`source-read`)",
    }
    for page, token in pages.items():
        text = _read(page)
        assert AST_RECEIPT in text and token in text, page.name
    for stale, page in (("Here's a real snippet from a cognee skill SKF compiled", GETTING_STARTED),
                        ("The tag means *this came from AST extraction", HOW_IT_WORKS),
                        ("extracted from code via AST parsing", EXAMPLES),
                        ("extracted from source code by AST parsing", CONCEPTS)):
        assert stale not in _read(page), (page.name, stale)


def test_ccc_ranks_the_files_a_step_reads_one_at_a_time():
    """CCC orders the files a step reads by hand; the recipe runner reads every file in scope."""
    bridge = _read(SRC / "knowledge" / "ccc-bridge.md")
    assert "The ranking orders the files a step reads by hand; the recipe runner reads every file in scope" in bridge
    [forge_plus] = [line for line in _read(SKILL_MODEL).splitlines() if line.startswith("| **Forge+** |")]
    entry = _slice(_read(TROUBLESHOOTING), "### Want semantic discovery for large codebases?", "\n### ")
    bullet = _slice(_read(CONCEPTS), "- **Forge+:**", "\n")
    for text in (forge_plus, entry, bullet):
        assert "a step that reads files one at a time reads the most relevant" in text, text
        assert "recipe runner reads every file in scope" in text and "before AST extraction" not in text, text


# --------------------------------------------------------------------------
# Troubleshooting: the brief lookup, the ecosystem check, forge-auto's Test
# stage and the run locks
# --------------------------------------------------------------------------


def test_troubleshooting_brief_entry_follows_the_brief_lookup():
    """#594: with nothing named, Create Skill loads the only brief, asks among several, or halts headless."""
    load = _slice(_read(SRC / "skf-create-skill" / "references" / "load-brief.md"),
                  "### 2. Discover Skill Brief", "### 3.")
    for token in ("**One brief:** load it", "§5's banner names it", '"Which brief should I compile?"',
                  "exit code 2, `brief-missing`", "or `--batch` to compile them all",
                  "No skill brief found. Run [BS] Brief Skill to create one, or use [QS] Quick Skill"):
        assert token in load, token
    entry = _slice(_read(TROUBLESHOOTING), '### "No skill brief found"', "\n### ")
    for token in ("loads the only brief in `forge_data_folder` and names it in its banner", "asks which one to compile",
                  "stops with exit code 2 (`brief-missing`) and names them", "or `--batch` to compile them all",
                  "with nothing named, that `forge_data_folder` holds no brief", "`@Ferris BS`", "`@Ferris QS`"):
        assert token in entry, token


def test_docs_describe_the_skipped_ecosystem_check():
    """#599: Quick Skill skips its official-skill check until a registry API exists, and Create Skill has none."""
    check = _read(QUICK / "references" / "ecosystem-check.md")
    assert "agentskills.io has no registry API" in check and "Once a registry API lists an official skill" in check
    create = SRC / "skf-create-skill"
    assert not (create / "references" / "ecosystem-check.md").exists()
    check_words = ("ecosystem check", "ecosystem-check", "ecosystem match", "ecosystem-match")
    assert not [p.name for p in create.rglob("*.md") if any(w in _read(p).lower() for w in check_words)]
    entry = _slice(_read(TROUBLESHOOTING), '### "Ecosystem match found"', "\n### ")
    for token in ("No run stops here today", "agentskills.io offers no registry API",
                  "Create Skill has no such check since 3.0.0"):
        assert token in entry, token
    assert "it skips that check until agentskills.io offers a registry API" in _read(HOW_IT_WORKS)
    for stale, page in (("Checks ecosystem first", EXAMPLES), ("the ecosystem check in `@Ferris QS`", EXAMPLES),
                        ("ecosystem check messages", EXAMPLES), ("ecosystem checks", README),
                        ("he checks agentskills.io for an official cognee skill", HOW_IT_WORKS)):
        assert stale not in _read(page), (page.name, stale)


def test_quick_skill_walkthrough_names_the_registry_lookup():
    """#582: every registry is asked, a language hint asks one, and a headless run records `also_found_in`."""
    resolve = _read(QUICK / "references" / "resolve-target.md")
    for token in ("which asks every deterministic registry (npm, PyPI, crates.io)",
                  "a JavaScript, TypeScript, Python or Rust hint makes the resolver ask that language's registry alone",
                  "(the first registry, in the order npm, PyPI, crates.io, that gives a GitHub repository)",
                  "Record the resolver's `warning` (`also_found_in: ...`)"):
        assert token in resolve, token
    step = _paragraph(_read(HOW_IT_WORKS), "Ferris turns your input into a GitHub repository.")
    for token in ("looked up on every registry of npm, PyPI and crates.io",
                  "(a language hint asks only that language's registry)", "an interactive run lists every candidate",
                  "keeps the first registry's pick (npm, then PyPI, then crates.io)", "an `also_found_in` warning"):
        assert token in step, token


def test_forge_auto_entry_names_every_verdict_that_stops_ts():
    """#586: TS stops a pipeline on any verdict but PASS, a capped FAIL included; a plain update offers the report."""
    pipeline = _read(FORGER_SKILL.parent / "references" / "pipeline-mode.md")
    assert "(for TS, the verdict: `FAIL`, `INCONCLUSIVE` or `pass-with-drift`)" in pipeline
    capped = _score(90, 95, "frontmatter-validator-timeout")
    assert (capped["result"], capped["effectiveResult"]) == ("PASS", "FAIL")
    entry = _slice(_read(TROUBLESHOOTING), "### forge-auto halted at the Test stage", "\n### ")
    for token in ("TS stops the pipeline on any verdict but PASS", "unless a cap fired",
                  "a cap that turned a pass into a fail whatever the score", "INCONCLUSIVE, and pass-with-drift",
                  "`@Ferris US <name> --from-test-report`", "no repair has applied",
                  "finds a failed or pass-with-drift test report", "adds an `unconsumed-test-report` warning"):
        assert token in entry, token
    assert "does not read the test report" not in entry


def test_troubleshooting_names_the_run_lock_halts():
    """#588: update and rename each stop on a run lock another run holds, and say how to clear a stale one."""
    refs = SRC / "skf-update-skill" / "references"
    guard = _slice(_read(refs / "init.md"), "### 1b. Concurrency Guard", "### 2.")
    for token in ('--lock "{forge_data_folder}/{skill_name}/.skf-update.lock"', "--stale-after 60",
                  '`status: "halted-for-concurrent-run"`, `phase: "init:concurrency-guard"`',
                  "Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true"):
        assert token in guard, token
    for name, phase in (("merge.md", "merge:run-lock"), ("write.md", "write:run-lock")):
        text = _read(refs / name)
        assert f'`phase: "{phase}"`' in text and '"run-lock-lost: ' in text, name
    doc = _read(TROUBLESHOOTING)
    update = _slice(doc, "### Update Skill stops with `halted-for-concurrent-run`", "\n### ")
    for token in ("`.skf-update.lock` in `<forge_data_folder>/<name>/`", "`init:concurrency-guard`",
                  "60 minutes after it was taken or renewed", "`--detect-only` and `--dry-run` take no lock",
                  "delete the lock file the message names", "**`run-lock-lost`:**",
                  "`merge:run-lock` or `write:run-lock`"):
        assert token in update, token
    contract = _read(SRC / "skf-rename-skill" / "references" / "invocation-contract.md")
    assert "`{forge_data_folder}/.skf-rename-{old_name}.lock`" in contract
    assert "(60 minutes after it was taken or renewed)" in contract and "`--dry-run` takes none" in contract
    assert "guarded-delete" in _read(SRC / "skf-rename-skill" / "references" / "select.md")
    verify = doc.index("### Rename Skill stops with `verify-failed`")
    lock = doc.index("### Rename Skill stops with `halted-for-concurrent-run`")
    assert doc.index("\n### ", verify) == lock - 1
    rename = _slice(doc, "### Rename Skill stops with `halted-for-concurrent-run`", "\n### ")
    for token in ("(exit `5`)", "`.skf-rename-<name>.lock` in `forge_data_folder`",
                  "60 minutes after it was taken or renewed", "delete the lock file the message names",
                  "`--dry-run` takes no lock"):
        assert token in rename, token
    leftover = _slice(doc, "### Rename Skill stops with `name-collision` and lists old folders", "\n### ")
    assert doc.index("\n### ", lock) == doc.index("### Rename Skill stops with `name-collision`") - 1
    for token in ("(exit `5`)", "`skf-skill-inventory.py guarded-delete`", "`@Ferris EX`"):
        assert token in leftover, token


# --------------------------------------------------------------------------
# Verifying a Skill: where the scores come from, the caps and the report
# --------------------------------------------------------------------------


def test_verifying_scoring_lines_follow_test_skill():
    """#613: the source access and tooling health the report records, and the caps no fallback re-flips."""
    score = _script(COMPUTE_SCORE)
    doc = _read(VERIFYING)
    confidence = _paragraph(doc, "The report also records `analysisConfidence`")
    listed = re.findall(r"`([a-z-]+)`", confidence.split("how Test Skill read the source (", 1)[1].split(")", 1)[0])
    assert tuple(listed) == score.ANALYSIS_CONFIDENCE and "degraded" not in confidence
    assert "toolingStatus: '{ok|frontmatter-validator-timeout}'" in _read(TEST_SKILL / "references" / "init.md")
    assert "`toolingStatus`: `ok`, or `frontmatter-validator-timeout`" in confidence
    [row] = [line for line in doc.splitlines() if line.startswith("| **Source not on disk**")]
    for state in ("provenance-map", *score.NO_LOCAL_SOURCE):
        assert f"`{state}`" in row, state
    for state in score.NO_LOCAL_SOURCE:
        out = score.compute_score({"mode": "naive", "tier": "Deep", "analysisConfidence": state,
                                   "scores": {**dict.fromkeys(SCORE_CATEGORIES, 90), "coherence": None}})
        assert {"signatureAccuracy", "typeCoverage"} <= set(out["skippedCategories"]), state
    caps = _paragraph(doc, "Test Skill does not run without its tools")
    for token in ("a missing `uv` or `python3` halts the run", "(`runtime-missing`)",
                  "whenever the report's `toolingStatus` is not `ok`", "A capped run stays FAIL at any threshold"):
        assert token in caps, token
    assert "| `runtime-missing` |" in _read(TEST_SKILL / "references" / "invocation-contract.md")
    for stale in ("the run is marked `degraded`", "still accepts a capped run"):
        assert stale not in doc, stale
    assert _paragraph(doc, "When no cap fired and a skill scores between 80% and its target threshold")
    floor, capped = _score(90, 85), _score(90, 85, "frontmatter-validator-timeout")
    assert (floor["effectiveResult"], floor["thresholdFallback"]) == ("PASS", True)
    assert (capped["effectiveResult"], capped["thresholdFallback"]) == ("FAIL", False)


def test_verifying_names_where_scores_and_reports_come_from():
    """#613, #593: the score is read from the scripts' files by path, and a report is published only once whole."""
    score = _script(COMPUTE_SCORE)
    doc = _read(VERIFYING)
    deterministic = _paragraph(doc, "The weight redistribution and score aggregation")
    for script in ("score-signatures.py", "load-coverage-inputs.py"):
        assert script in score.__doc__ and f"`{script}`" in deterministic, script
    assert "halts without a score rather than scoring by hand" in deterministic
    assert "falls back to manual calculation" not in deterministic
    assert "A quality gate does not score by hand" in _read(TEST_SKILL / "references" / "score.md")
    init = _read(TEST_SKILL / "references" / "init.md")
    assert "under the in-progress name `{forge_version}/.skf-test-report-{skill_name}-{run_id}.md`" in init
    assert 'mv "{report_file}" "{publishedReportFile}"' in _read(TEST_SKILL / "references" / "report.md")
    [row] = [line for line in doc.splitlines() if line.startswith("| How was the skill scored?")]
    for token in ("gives a report this name only once its checks pass", "`.skf-test-report-{name}-{run_id}.md`",
                  "the last finished report still counts"):
        assert token in row, token


# --------------------------------------------------------------------------
# Campaign: the export gate, Setup's checks, the exit codes, the state helper
# and the result line
# --------------------------------------------------------------------------


def _campaign_state(scores: dict) -> dict:
    """A campaign state whose skills completed with the given {name: (tier, score)}."""
    return {"campaign": {"name": "demo", "started_at": "2026-01-01T00:00:00Z",
                         "last_updated": "2026-01-01T00:00:00Z", "current_stage": 8,
                         "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80}},
            "skills": [{"name": name, "status": "completed", "tier": tier, "quality_score": value, "skill_path": None}
                       for name, (tier, value) in scores.items()],
            "dependency_graph": {"execution_order": [], "circular_deps_detected": False}}


def test_campaign_doc_follows_the_export_gate():
    """#586: a Tier A skill runs BS, CS and TS; Export exports pass and fallback skills and names the rest."""
    loop = _read(CAMPAIGN / "references" / "step-05-skill-loop.md")
    assert "- **BS → CS → TS**" in loop and "Campaign runs no analyze-source pass" in loop
    gate = _script(CAMPAIGN / "scripts" / "campaign-quality-gate.py")
    out = gate.classify(_campaign_state({"top": ("A", 95), "near": ("A", 85), "low": ("A", 70),
                                         "batch": ("B", None)}), gate.parse_directive(""))
    assert {s["name"]: s["verdict"] for s in out["skills"]} == {"top": "pass", "near": "fallback", "low": "fail",
                                                                 "batch": "fail"}
    assert out["export"] == ["top", "near"]
    capstone = _read(CAMPAIGN / "references" / "step-07-capstone.md")
    assert "The capstone composes the skills in its `export[]`" in capstone
    doc = _read(CAMPAIGN_DOC)
    for stale in ("analyze (AN)", "analyze, brief, compile and test", "fallback floor is fixed at 80%",
                  "composed from all completed skills"):
        assert stale not in doc, stale
    assert doc.count("brief (BS), compile (CS) and test (TS)") == 2
    assert "analyze, brief, compile and test" not in _read(EXAMPLES)
    gates = _paragraph(doc, "You can change all three through")
    for token in ("completes only on a Test Skill PASS, with `--threshold` set to its effective soft target",
                  "at or above the soft target is `pass`", "at or above the soft fallback is `fallback`",
                  "anything else is not exported",
                  "classified by its skill-check score, and one without a score is not exported"):
        assert token in gates, token
    rows = {line.split("|")[2].strip(): line for line in doc.splitlines() if re.match(r"\| \d+ \| ", line)}
    for token in ("names the ones the gate leaves out", "each `pass` and `fallback` skill"):
        assert token in rows["Export"], token
    assert "the completed skills that clear the quality gate" in rows["Capstone"]
    assert "`[E]xport all` exports only the `pass` and `fallback` skills" in doc
    assert "## Export Gate" in _read(CAMPAIGN / "templates" / "campaign-report-template.md")
    assert "an Export Gate section" in doc


def test_campaign_doc_follows_setup_strategy_and_the_exit_codes():
    """#594, #586: Setup rejects what the manifest parser rejects, Strategy a tier inversion, and 13 is listed."""
    manifest = _script(CAMPAIGN / "scripts" / "campaign-parse-manifest.py")
    parsed = manifest.parse_manifest_text(
        "core,git@github.com:acme/core.git,A,v1.2.0\ncli,acme/cli,B,main\nlab,https://gitlab.com/acme/lab,A,\n"
        "Bad_Name,https://github.com/acme/bad,A,\nweb,https://github.com/acme/web,A,main\n"
        "core,https://github.com/acme/core2,B,\nsub,https://github.com/acme/sub/tree/main,A,\n")
    assert [(t["name"], t["repo_url"]) for t in parsed["targets"]] == [
        ("core", "https://github.com/acme/core"), ("cli", "https://github.com/acme/cli")]
    assert [e["line"] for e in parsed["errors"]] == [3, 4, 5, 6, 7]
    doc = _read(CAMPAIGN_DOC)
    columns = _slice(doc, "- `repo_url`:", "- `depends_on`:")
    for token in ("as a URL, an SSH URL or `owner/repo`", "`https://github.com/<owner>/<repo>`",
                  "rejects another host or a path inside a repository",
                  "A Tier A pin must be a full `X.Y.Z` version (a `v` prefix is allowed)",
                  "a Tier B pin may also be a branch"):
        assert token in columns, token
    checks = _paragraph(doc, "Setup checks every target the same way")
    for token in ("a `repo_url` that is not a GitHub repository", f"at most {manifest.MAX_NAME} characters",
                  "a Tier A pin that is not an `X.Y.Z` version", "a duplicate name", "stops with exit code 2"):
        assert token in checks, token
    contracts = _read(CAMPAIGN / "references" / "campaign-contracts.md")
    assert re.search(r"^\| 13 +\| dependency-blocked", contracts, re.M)
    schema = json.loads(_read(SCHEMAS / "skf-campaign-result-envelope.v1.json"))
    [exits] = [line for line in doc.splitlines() if line.startswith("- **Exit codes**:")]
    for reason, code in schema["$defs"]["skf-envelope"]["const"]["exit_codes"].items():
        assert f"`{code}` {reason}" in exits, reason
    loop = _read(CAMPAIGN / "references" / "step-05-skill-loop.md")
    assert "`skip` (every unmet dependency failed or was skipped" in loop
    assert "`halt` (a dependency is still pending or active" in loop
    dependency = _paragraph(doc, "Campaign orders skills by their `depends_on` lists")
    for token in ("exit code 13 (`dependency-blocked`)",
                  "skips the waiting skill when every unmet dependency failed or was skipped",
                  "halts with exit code 13 only while a dependency is still pending or active"):
        assert token in dependency, token
    strategy = _read(CAMPAIGN / "references" / "step-02-strategy.md")
    assert "**Tier A on Tier B**" in strategy and "HALT (exit code 4, `circular-deps`)" in strategy
    tiers = _paragraph(doc, "Do not make a Tier A library depend on a Tier B library")
    assert "Strategy rejects such a plan with exit code 4" in tiers and "(`tier_inversions`)" in tiers


def test_campaign_doc_follows_the_state_helper_and_the_result_line():
    """#587, #593: one helper writes, archives and recovers the state; the log is typed; the line has a schema."""
    contracts = _read(CAMPAIGN / "references" / "campaign-contracts.md")
    for token in ("copies the valid primary it read to `_campaign-state.yaml.bak`", "renamed over the old one",
                  "from the clock in UTC", "one typed and timestamped line per entry"):
        assert token in contracts, token
    assert "archive/<campaign name>-<UTC stamp>/" in _read(CAMPAIGN / "scripts" / "campaign-state.py")
    resume = _read(CAMPAIGN / "references" / "step-resume.md")
    assert "**`stage` 1 with no `{briefFile}`:**" in resume and "HALT (exit code 8, `missing-brief`)" in resume
    doc = _read(CAMPAIGN_DOC)
    for stale in ("[R]ecover", "[K]eep"):
        assert stale not in doc and stale not in resume, stale
    state = _paragraph(doc, "The single source of truth for campaign progress.")
    for token in ("`campaign-state.py`", "validates the state before and after the change", "(never an invalid one)",
                  "writes the new state atomically", "in UTC"):
        assert token in state, token
    recovery = _slice(doc, "### Re-invocation and recovery", "\n---\n")
    for token in ("`campaign-state.py archive`", "`archive/<name>-<UTC timestamp>/`",
                  "Setup itself refuses to overwrite a state file or a backup", "`campaign-state.py recover`"):
        assert token in recovery, token
    log = _paragraph(doc, "This log only grows.")
    assert "timestamped" in log and all(f"`{kind}`" in log for kind in ("decision", "auto", "event"))
    assert "halts the resume with exit code 8 (`missing-brief`)" in doc
    assert "a headless resume prints the campaign's success line again" in doc
    maintenance = _read(CAMPAIGN / "references" / "step-11-maintenance.md")
    assert "run it now, after the final state write" in maintenance
    assert "run `{onComplete}` without `--report-path`" in maintenance
    [hook] = [line for line in doc.splitlines() if line.startswith("- **`on_complete`**")]
    assert "after its final state write" in hook and "only when the report was written" in hook
    schema = json.loads(_read(SCHEMAS / "skf-campaign-result-envelope.v1.json"))
    assert {"exit_code", "halt_reason", "export_verdicts", "skills_excluded"} <= set(schema["required"])
    for token in ("`skf-campaign-result-envelope.v1.json`", "`export_verdicts`", "`skills_excluded`",
                  "the health check displays the `SKF_CAMPAIGN_RESULT_JSON` line as the run's last line",
                  "every field the schema requires"):
        assert token in doc, token
    seeded = "a seeded run is an unattended run (CI)"
    assert seeded in _read(CAMPAIGN / "SKILL.md")
    [brief] = [line for line in doc.splitlines() if line.startswith("| `--brief <file>` |")]
    for token in ("a seeded run is an unattended (CI) run that takes every default",
                  "give the same file at the Setup question instead, which stays interactive"):
        assert token in brief, token


# --------------------------------------------------------------------------
# The workflows reference, forge-auto, the Ferris page and the architecture
# page: the v3.0.0 behaviour of each workflow
# --------------------------------------------------------------------------

GITHUB_BLOB = "https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/"
REFERENCE_PAGES = (WORKFLOWS, FORGE_AUTO, AGENTS, ARCHITECTURE)
LINK_OR_SECTION_RE = re.compile(r"\]\(" + re.escape(GITHUB_BLOB) + r"([^)#\s]+)\)|§ \"([^\"]+)\"(?: / \"([^\"]+)\")?")
# Each setting the docs name, by the workflow whose customize.toml holds it, and the ones the docs call gone.
SETTINGS_TAKING_EFFECT = {
    "skf-test-skill": ("default_threshold", "test_report_template_path"),
    "skf-drop-skill": ("forbid_purge_in_headless",),
    "skf-rename-skill": ("force_source_authority_in_headless",),
    "skf-refine-architecture": ("output_folder_path", "refinement_rules_path"),
    "skf-verify-stack": ("persistent_facts", "report_template_path"),
    "skf-campaign": ("report_template_path",),
    "skf-audit-skill": ("drift_report_template_path",),
    "skf-analyze-source": ("analysis_report_template_path",),
}
SETTINGS_REMOVED = {
    "skf-test-skill": ("scoring_rules_path", "output_formats_path"),
    "skf-drop-skill": ("default_mode",),
    "skf-audit-skill": ("severity_rules_path",),
    "skf-verify-stack": ("output_folder_path",),
}
RA_RULES_TABLES = ("Gap Classification", "Issue Classification", "Issue Severity", "VS Report Integration",
                   "Improvement Classification", "Improvement Value")


def _section(name: str) -> str:
    """docs/workflows.md's `### <name>` section, up to its **Agent:** line."""
    return _slice(_read(WORKFLOWS), f"### {name}", "**Agent:**")


def _schema(name: str) -> dict:
    return json.loads(_read(SCHEMAS / name))


def _settings(skill: str) -> dict:
    """The [workflow] table of a skill's bundled customize.toml."""
    return tomllib.loads(_read(SRC / skill / "customize.toml"))["workflow"]


def _headings(path: Path) -> set[str]:
    return {heading.strip() for heading in re.findall(r"^#{1,6} (.+)$", _read(path), re.M)}


def test_reference_pages_link_to_files_and_sections_that_exist():
    """#600: each source link on the four pages names a file on main, and each § after it a heading of that file.

    The lifted headless contracts moved sections out of SKILL.md (drop, rename, refine-architecture), so a link
    that still names a SKILL.md section points at nothing. A § without a link before it on its line is refused.
    """
    links = 0
    for page in REFERENCE_PAGES:
        for line in _read(page).splitlines():
            target = None
            for match in LINK_OR_SECTION_RE.finditer(line):
                if match.group(1):
                    target = REPO_ROOT / match.group(1)
                    assert target.is_file(), (page.name, match.group(1))
                    links += 1
                    continue
                assert target is not None, (page.name, line[:80])
                for heading in filter(None, match.groups()[1:]):
                    assert heading in _headings(target), (page.name, match.group(0), heading)
    assert links > 10


def test_pipeline_docs_name_the_circuit_breakers_the_gate_applies():
    """#586: TS stops a pipeline on any verdict but PASS, and VS only on zero coverage.

    pipeline-contracts.md's Circuit Breakers rows are what pipeline-gate.py applies, and an alias given without its
    argument asks for it, or halts a headless run; workflows.md and forge-auto.md say the same.
    """
    breakers = _slice(_read(SRC / "shared" / "references" / "pipeline-contracts.md"), "## Circuit Breakers",
                      "### Bracket Syntax")
    [ts] = [row for row in breakers.splitlines() if row.startswith("| TS |")]
    [vs] = [row for row in breakers.splitlines() if row.startswith("| VS |")]
    for token in ("Any verdict but PASS", "a post-score cap forced", "INCONCLUSIVE or pass-with-drift"):
        assert token in ts, token
    assert "Zero coverage" in vs and "NOT_FEASIBLE included" in vs
    [audit] = [row for row in breakers.splitlines() if row.startswith("| AS |")]
    assert "unless `next_workflow` is `update-skill`" in audit
    mode = _read(SRC / "skf-forger" / "references" / "pipeline-mode.md")
    assert "each input in `missing_args`" in mode and "In `{headless_mode}`, ask nothing: HALT" in mode
    doc = _read(WORKFLOWS)
    [bullet] = [line for line in doc.splitlines() if line.startswith("- **Circuit breakers**")]
    for token in ("TS settles any verdict but PASS", "VS covers none of the technologies the architecture keeps",
                  "a FAIL that a cap forced although the score clears the threshold",
                  "on INCONCLUSIVE and on pass-with-drift", "VS stops the pipeline only on zero coverage",
                  "a `NOT_FEASIBLE` verdict with coverage goes on to RA", "each `Blocked` pair"):
        assert token in bullet, token
    assert "VS finds every integration blocked" not in doc
    [maintain] = [line for line in doc.splitlines() if line.startswith("- **`maintain` skips")]
    assert "unless the source moved past the ref the skill was built from" in maintain
    assert "`--target-ref <upstream_ref>`" in maintain
    alias = _paragraph(_slice(doc, "### Pipeline Aliases", "### How It Works"), "An alias given without its argument")
    assert "asks for it" in alias and "halts instead, before any workflow runs" in alias
    forge_auto = _read(FORGE_AUTO)
    for token in ("The pipeline goes on to export only when Test Skill settles a PASS",
                  "Every other verdict but PASS stops it there too",
                  "a FAIL that a cap forced although the score clears 90%", "INCONCLUSIVE (", "and pass-with-drift"):
        assert token in forge_auto, token


def test_forge_auto_says_the_manual_repair_chain_tests_at_the_default_bar():
    """#586: a chain with no alias re-tests at Test Skill's default bar, so keeping 90% takes the offer or a flag."""
    thresholds = _slice(_read(TEST_SKILL / "references" / "init.md"), "### 1b.", "### 2.")
    assert re.search(r"\|\s*`forge-auto`\s*\|\s*90\s*\|", thresholds)
    assert "If `{pipeline_alias}` is absent" in thresholds and "falls through to `{defaultThreshold}`" in thresholds
    assert re.search(r"^default_threshold = 80$", _read(TEST_SKILL / "customize.toml"), re.M)
    routes = _slice(_read(SRC / "shared" / "references" / "pipeline-contracts.md"), "### Repair Routes",
                    "## Anti-Patterns")
    assert "TS, at the recorded threshold" in routes
    [repair] = [line for line in _read(FORGE_AUTO).splitlines() if "To fix the gaps, run" in line]
    for token in ("That chain has no alias, so Test Skill re-tests it at the default 80% bar",
                  "he offers that repair route himself, at the recorded 90% threshold",
                  "accept his offer to keep forge-auto's 90%",
                  "`@Ferris TS <name> --threshold=90`, then `@Ferris EX <name>`"):
        assert token in repair, token


def test_pipeline_docs_say_a_resume_comes_from_the_journal():
    """#587: a pipeline keeps its state in a journal in its run folder, which the next activation offers to resume.

    The pipeline result in the sidecar stays the chain's outcome, a quality halt offers its repair route, the offer
    can be dropped, and a headless start that names nothing to run stops.
    """
    contracts = _read(SRC / "shared" / "references" / "pipeline-contracts.md")
    state = _slice(contracts, "## Pipeline State", "## Pipeline Result")
    assert "`pipeline-journal.json`" in state and "`{project-root}/_bmad-output/.skf-run/skf-forger-<run_id>/`" in state
    assert "`{sidecar_path}/pipeline-result-latest.json`" in _slice(contracts, "## Pipeline Result",
                                                                  "## Resume and Repair")
    routes = _slice(contracts, "### Repair Routes", "## Anti-Patterns")
    assert "`US <skill> --from-test-report` joins the plan" in routes
    forger = _read(FORGER_SKILL)
    for token in ("runs at once", "**Nothing to run.**", "pipeline-journal.py discard"):
        assert token in forger, token
    [resume] = [line for line in _read(WORKFLOWS).splitlines() if line.startswith("- **Resume:**")]
    for token in ("`pipeline-journal.json`", "`_bmad-output/.skf-run/`", "rerun the step it stopped on with the "
                  "recorded plan", "A quality halt gets its repair route instead",
                  "`US <name> --from-test-report`, then TS and EX at the recorded threshold", "drop the offer",
                  "`pipeline-result-latest.json` in his sidecar folder"):
        assert token in resume, token
    architecture = _read(ARCHITECTURE)
    for text in (_paragraph(architecture, "**Chained runs**"), _paragraph(architecture, "Pipeline-facing workflows")):
        for token in ("`pipeline-journal.json`", "`_bmad-output/.skf-run/`", "`pipeline-result-latest.json`"):
            assert token in text, token
    assert "Audit Skill does the same" not in architecture
    agents = _read(AGENTS)
    menu = _paragraph(agents, "Ferris shows his menu as a numbered table")
    assert "A code, alias or chain you give with the invocation" in menu and "runs at once" in menu
    memory = _slice(agents, "**Memory:**", "[Getting Started")
    for token in ("a journal in its own run folder under `_bmad-output/.skf-run/`", "drop the offer",
                  "`--headless` (or `-H`)", '"Nothing to run"'):
        assert token in memory, token


def test_headless_docs_name_every_workflow_whose_line_is_the_last():
    """#593: Test Skill, Campaign and Export Skill bind the line the shared health check displays last, as setup's
    envelope is."""
    assert "it displays that line verbatim as its very last line" in _read(SRC / "shared" / "health-check.md")
    assert "bind `{result_envelope_line}`" in _read(TEST_SKILL / "references" / "report.md")
    assert "bound `{result_envelope_line}`" in _read(SRC / "skf-campaign" / "references" / "health-check.md")
    export = SRC / "skf-export-skill" / "references"
    assert "When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here" in (
        _read(export / "summary.md"))
    assert "summary.md §6 bound `{result_envelope_line}` to the `SKF_EXPORT_RESULT_JSON` line" in (
        _read(export / "health-check.md"))
    setup = _slice(_read(WORKFLOWS), "**Exception: `/skf-setup` headless", "**Exception: `/skf-quick-skill` headless")
    final = _paragraph(setup, "Setup is not the only workflow whose result line is the run's final message")
    for token in ("`SKF_TEST_RESULT_JSON`", "`SKF_CAMPAIGN_RESULT_JSON`", "displays it last",
                  "Export Skill (a `--dry-run` too)", "`SKF_EXPORT_RESULT_JSON`",
                  "(under `--no-health-check`, Test Skill displays it itself as its last line)"):
        assert token in final, token
    bypass = _paragraph(_read(TEST_SKILL / "references" / "report.md"), "**`--no-health-check` flag bypass.**")
    assert "display `{result_envelope_line}` verbatim as the run's last line" in bypass


def test_quick_skill_documents_the_registry_lookup_and_the_hints():
    """#582, #594: a package name asks every registry, a headless run keeps the first pick, and the hint flags.

    resolve-target.md runs the ambiguous-name and multi-language gates the section describes, and batch-mode.md
    refuses the hint flags with the halt the docs name.
    """
    resolve = _read(QUICK / "references" / "resolve-target.md")
    for token in ("asks every deterministic registry (npm, PyPI, crates.io)",
                  "a JavaScript, TypeScript, Python or Rust hint makes the resolver ask that language's registry alone",
                  "the first registry, in the order npm, PyPI, crates.io, that gives a GitHub repository",
                  "keep the chain's pick and never halt", "`also_found_in`",
                  "Select: [C] Continue with 1 · [2] to [n] Use that language · [A] Abort",
                  "headless mode auto-proceeds with the helper's pick", "set `language` to `markdown`"):
        assert token in resolve, token
    assert "exit code 3" in _slice(resolve, "- **IF A**: HARD HALT with **exit code", ")")
    assert "has no registry API" in _read(QUICK / "references" / "ecosystem-check.md")
    before = _slice(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    halt = re.search(r"HARD HALT with \*\*exit code (\d+) \(([a-z-]+)\)\*\*", before)
    assert halt and "`--language-hint` and `--scope-hint` are single-target flags too" in before
    section = _quick_section()
    lookup = _paragraph(section, "**Package names:**")
    for token in ("every registry of npm, PyPI and crates.io",
                  "a JavaScript, TypeScript, Python or Rust language hint asks only that language's registry",
                  "lists every candidate and asks which project to build",
                  "keeps the first registry's pick (npm, then PyPI, then crates.io)", "`also_found_in` warning",
                  "its GitHub URL, its registry page URL or a language hint (`language=` on a batch line)"):
        assert token in lookup, token
    assert "Ecosystem check (skipped until agentskills.io offers a registry API)" in section
    overrides = _slice(section, "**Per-target overrides**", "**Safety:**")
    for flag in ("--language-hint", "--scope-hint"):
        [row] = [line for line in overrides.splitlines() if line.startswith(f"- `{flag} ")]
        assert row.endswith("Single-target runs only."), row
    refusal = _paragraph(overrides, "`--description` and `--exports` do not combine with `--batch`")
    assert (f"`--language-hint` and `--scope-hint` are refused with `--batch` too (exit `{halt.group(1)}`, "
            f"`{halt.group(2)}`)") in refusal
    languages = _paragraph(section, "**Languages:**")
    for token in ("`[C]` to keep the first", "`[2]` to `[n]` to use that one", "`[A]` to abort (exit `3`)",
                  "A headless run keeps the first and records the choice"):
        assert token in languages, token
    shape = _paragraph(section, "**Skills modules:**")
    assert "`--scope-hint <path>`" in shape and "the language `markdown`" in shape


def test_brief_skill_documents_package_targets_and_headless_scope_defaults():
    """#582, #594: the target prompt takes a package or its registry page; a headless scope type takes a default."""
    gather = _read(SRC / "skf-brief-skill" / "references" / "gather-intent.md")
    for token in ("A **package name or registry page**", "its `target_version`, when not null, pre-fills "
                  "`target_version`", "Offer every candidate, numbered"):
        assert token in gather, token
    args = _read(SRC / "skf-brief-skill" / "references" / "headless-args.md")
    assert "takes the scope type's headless default and names it in the envelope's `warnings`" in args
    target = _paragraph(_section("Brief Skill (BS)"), "**Target:**")
    for token in ("a package name or its registry page", "`requests==2.31.0`", "npmjs.com, pypi.org or crates.io",
                  "lists every candidate", "pre-fills `target_version`", "still needs a URL or a path"):
        assert token in target, token
    item = _slice(_read(WORKFLOWS), "1. **Pre-supplied inputs replace prompts.**", "2. **Structured exit-code map.**")
    for scope_type in ("full-library", "public-api", "component-library", "specific-modules"):
        assert f"`{scope_type}` " in item, scope_type
    for token in ("`warn: headless boundary default <type>: ...`", "falls back to full-library",
                  "`scope.rationale`", "`scope_type=reference-app` without `include`",
                  "halt with `input-missing` (exit `2`)"):
        assert token in item, token


def test_create_skill_documents_the_brief_lookup_the_batch_and_its_result_line():
    """#594, #593: CS's brief lookup, its validated batch, and its result line on every brief and every halt."""
    load = _read(SRC / "skf-create-skill" / "references" / "load-brief.md")
    for token in ("**One brief:** load it", "**Several briefs:** interactive, list each one",
                  "exit code 2, `brief-missing`"):
        assert token in load, token
    batch = _read(SRC / "skf-create-skill" / "references" / "batch-mode.md")
    assert "`create-skill-batch-latest.json`" in batch and "the highest exit code among the briefs that failed" in batch
    schema = _schema("skf-create-skill-result-envelope.v1.json")
    codes = schema["properties"]["exit_code"]["enum"]
    assert codes == [0, 2, 3, 4, 5, 6]
    section = _section("Create Skill (CS)")
    which = _paragraph(section, "**Which brief:**")
    for token in ("loads the only brief in `forge_data_folder`", "an interactive run asks which one to compile",
                  "a headless run stops with exit `2` (`brief-missing`)"):
        assert token in which, token
    batch_doc = _paragraph(section, "**Batch mode:**")
    for token in ("folders of briefs", "Every brief is validated before the first one compiles",
                  "with the validator's first message", "an earlier brief of the batch already has",
                  "A HARD HALT ends only its own brief", "`create-skill-batch-latest.json`",
                  "the highest exit code among its briefs, `0` when every brief finished", "goes on where it stopped"):
        assert token in batch_doc, token
    assert "Ecosystem check" not in section and "Load brief → Extract" in section
    doc = _read(WORKFLOWS)
    envelopes = _paragraph(doc, "**Other workflows emit result envelopes too.**")
    assert "adding `--result-dir \"{forge_version}\"` once step 7 has created `{forge_version}`" in _read(
        SRC / "skf-create-skill" / "SKILL.md")
    for token in ("one `SKF_CREATE_SKILL_RESULT_JSON` line per finished brief on stdout",
                  "one on stderr at every HARD HALT, in every mode", "`create-skill-result-<timestamp>.json`",
                  "once the skill's version folder under `forge_data_folder` exists (every finished brief, and a halt "
                  "after step 7 creates it)"):
        assert token in envelopes, token
    assert "only when it halts" not in envelopes
    reading = _paragraph(doc, "**Reading the result lines.**")
    assert "AN, CS, SS" in reading and f"a CS halt has `{codes[1]}` to `{codes[-1]}`" in reading
    [row] = [line for line in doc.splitlines() if line.startswith("| CS | `SKF_CREATE_SKILL_RESULT_JSON`")]
    for field in ("status", "exit_code", "phase"):
        assert field in schema["properties"] and f"`{field}`" in row, field
    assert "halt_reason" in schema["properties"]["summary"]["properties"] and "`summary.halt_reason`" in row
    assert "only when it stops early" not in row


def test_stack_skill_documents_its_inputs_run_state_and_result_fields():
    """#594, #587, #593: SS's inputs, run folder, review, halts and result line are its invocation contract's."""
    refs = SRC / "skf-create-stack-skill" / "references"
    contract = _read(refs / "invocation-contract.md")
    rows = {line.split("|")[1].strip(): line for line in contract.splitlines() if line.startswith("| ")}
    names = re.findall(r"`([a-z_]+)`:", rows["**Inputs**"])
    assert names == ["project_path", "skills", "stack_name", "scope_overrides", "architecture_doc_path", "mode"]
    assert "deleted when the run finishes or the user cancels" in rows["**Outputs**"]
    assert "`unknown-verdict-token`" in rows["2"] and "`input-invalid`" in rows["2"]
    assert "`helper-missing`" in rows["3"]
    assert "with `-stack` appended when it does not already end in it" in _read(refs / "init.md")
    assert "display the full draft only when the user asks, never in a headless run" in _read(refs / "compile-stack.md")
    section = _section("Stack Skill (SS)")
    inputs = _paragraph(section, "**Inputs:**")
    for name in names:
        assert f"`{name}`" in inputs, name
    for token in ("`-stack` is appended when the name lacks it", "exit `2` (`input-invalid`)", "import-count helper"):
        assert token in inputs, token
    state = _paragraph(section, "**Run state:**")
    for token in ("`_bmad-output/.skf-run/`", "deleted when the run finishes or you cancel it",
                  "the full draft only when you ask, and never in a headless run"):
        assert token in state, token
    halts = _paragraph(section, "**Halts:**")
    assert "exit `3` (`helper-missing`)" in halts and "exit `2` (`unknown-verdict-token`)" in halts
    assert "the folder `stack_name` names (by default `<project>-stack`) when SKF generated it" in _paragraph(
        section, "**Safety:**")
    doc = _read(WORKFLOWS)
    assert "[`src/shared/scripts/schemas/skf-stack-result-envelope.v1.json`]" in _paragraph(
        doc, "**Other workflows emit result envelopes too.**")
    schema = _schema("skf-stack-result-envelope.v1.json")
    [row] = [line for line in doc.splitlines() if line.startswith("| SS | `SKF_STACK_RESULT_JSON`")]
    for field in ("mode", "stack_libraries", "skill_package", "quality_score", "run_id", "result_path",
                  "headless_decisions", "warnings", "exit_code", "halt_reason", "error"):
        assert field in schema["properties"] and f"`{field}`" in row, field
    assert "not a test-skill score" in schema["properties"]["quality_score"]["description"]
    assert "not a Test Skill score" in row


def test_analyze_source_documents_the_opening_question_the_archive_and_the_ref_flags():
    """#602, #594: one opening question, [D] in two menus, the archived report and the ref flags."""
    refs = SRC / "skf-analyze-source" / "references"
    init = _read(refs / "init.md")
    for token in ("ask at most one opening question",
                  "analyze-source-report-{project_name}-$(date -u +%Y%m%d-%H%M%S).md",
                  "`--target-ref <ref>` names one git tag or branch for every project path",
                  "`--target-refs` and `--target-ref` are mutually exclusive"):
        assert token in init, token
    assert "Interactive only" in _read(refs / "discover-additional-source.md")
    for menu in ("map-and-detect.md", "recommend.md"):
        assert "[D] Discover Additional Source" in _read(refs / menu), menu
    assert "A headless run defers nothing" in _read(refs / "identify-units.md")
    section = _section("Analyze Source (AN)")
    questions = _paragraph(section, "**Questions:**")
    for token in ("asks at most one opening question", "map-and-detect and recommend menus",
                  "`[D]` Discover Additional Source"):
        assert token in questions, token
    note = _paragraph(section, "**Note:**")
    for token in ("an unfinished analysis of the same target resumes", "`AN[auto]`", "of a different target",
                  "`analyze-source-report-<project>-<YYYYMMDD-HHmmss>.md`", "a fresh analysis starts"):
        assert token in note, token
    flags = _paragraph(_read(WORKFLOWS), "To run these without questions, pass their inputs as flags.")
    for token in ("Both hints apply to an `AN[auto]` run too", "defers the units outside `--intent-hint` before step 4",
                  "a headless run only ranks by it", "`--target-ref <ref>`", "`--target-refs <path:ref,...>`",
                  "which pins with `--pin`", "not with `--target-ref` or `[auto]`"):
        assert token in flags, token


def test_audit_section_documents_upstream_the_baseline_and_label_differences():
    """#588, #594 and the #556 pre-release docs drift fix: upstream, the baseline halts, the label table, the AS row."""
    schema = _schema("skf-audit-result-envelope.v1.json")
    for reason in ("no-baseline", "source-unreadable", "helper-missing"):
        assert reason in schema["properties"]["halt_reason"]["enum"], reason
    assert "upstream_moved is true" in schema["properties"]["next_workflow"]["description"]
    diff = " ".join(_read(SRC / "shared" / "scripts" / "skf-structural-diff.py").split())
    assert "label_changes" in diff and "so a difference in them is not drift" in diff
    section = _section("Audit Skill (AS)")
    upstream = _paragraph(section, "**Upstream:**")
    for token in ("`[C]` audit the newer ref", "a private tree of the run's own", "`[S]` stay on the baseline",
                  "`@Ferris US <name> --target-ref <ref>`", "`[X]` stop", "`upstream_drift_choice=S` or `X`",
                  "The `dirty_worktree_choice` and `force` inputs are gone"):
        assert token in upstream, token
    baseline = _paragraph(section, "**Baseline:**")
    for token in ("stops with `no-baseline` (exit `3`) in every mode", "`@Ferris TS`", "`@Ferris CS`",
                  "a changed document is graded HIGH", "`source-unreadable` (exit `3`)", "`doc_fetch_failed`",
                  "`doc_not_hashed`", "`helper-missing` (exit `3`)",
                  "The `degraded` input and the `severity_rules_path` setting are gone"):
        assert token in baseline, token
    labels = _paragraph(section, "**Provenance labels:**")
    for token in ("follow the tool that read it", "T1 to T1-low", "**Provenance label differences (not drift)**",
                  "not counted in Total Drift Items"):
        assert token in labels, token
    assert "Code-mode stacks are audited library by library" in section
    report = _read(SRC / "skf-audit-skill" / "references" / "report.md")
    assert "The skill matches the source at `{audit_ref}`" in report
    assert "`audit_ref` is `baseline_ref` when the audit stayed on the baseline, `upstream_ref` when the operator " \
           "chose `[C]`" in report
    output = _paragraph(section, "**Output:**")
    assert "`@Ferris US <name> --target-ref <upstream_ref>`" in output and "whatever the drift score" in output
    assert "CLEAN means the skill matches the source at the ref the audit read: the ref it was built from, or the " \
           "newer ref `[C]` audits" in output
    assert "the source it was built from;" not in output
    assert "ready to export" not in output
    [row] = [line for line in _read(WORKFLOWS).splitlines() if line.startswith("| AS | `SKF_AUDIT_RESULT_JSON`")]
    for field in ("drift_score", "next_workflow", "upstream_moved", "upstream_ref"):
        assert field in schema["properties"] and f"`{field}`" in row, field
    assert "`update-skill` whenever upstream moved" in row and "`--target-ref`" in row


def test_test_skill_documents_its_flags_and_where_automators_read_the_exit_code():
    """#593, #594: the flags and the skill-name halt are the contract's, and the exit code is read from the line."""
    contract = _read(TEST_SKILL / "references" / "invocation-contract.md")
    for token in ("`--no-health-check` (skip the health check that ends the run)",
                  "`--discovery-catalog=all` (widen the discovery catalog to the skills in "
                  "`{project-root}/.claude/skills/` and `{project-root}/_bmad/agents/`)",
                  "a headless run without it halts `input-missing`",
                  "A skill run cannot set the process exit status of the agent that runs it",
                  "the result envelope is the run's last line",
                  "`.skf-test-report-{skill_name}-{run_id}.md` until report.md §4c's checks pass",
                  "`skf-test-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name, `-2`, `-3` appended"):
        assert token in contract, token
    section = _section("Test Skill (TS)")
    flags = _slice(section, "**Flags:**", "**Skill name:**")
    for flag in ("--no-health-check", "--discovery-catalog=all"):
        assert f"- `{flag}` " in flags, flag
    assert "halts `input-missing`" in _paragraph(section, "**Skill name:**")
    exits = _paragraph(section, "**Verdicts and exit codes")
    for token in ("A skill run cannot set the exit status of the agent that runs it",
                  "read `exit_code` from the `SKF_TEST_RESULT_JSON` line, or from `skf-test-skill-result-latest.json`",
                  "is the run's last line"):
        assert token in exits, token
    assert "then exits `2`" not in exits
    architecture = _read(ARCHITECTURE)
    tree = _slice(architecture, "## Workspace Artifacts", "### Pipeline Result Contracts")
    [report] = [line for line in tree.splitlines() if "├── test-report-{skill-name}-{run_id}.md" in line]
    assert "as .skf-test-report-{skill-name}-{run_id}.md, renamed once its checks pass" in report
    contracts = _paragraph(architecture, "Pipeline-facing workflows")
    assert "`skf-test-skill-result-{YYYYMMDD-HHmmss}.json` (UTC, with `-2` appended" in contracts
    assert "skf-test-skill-result-{run_id}.json" not in architecture


def test_verify_stack_output_says_when_the_latest_copy_is_written():
    """#587: the -latest copy is published only once the finished report passes its check, the delta baseline too."""
    helper = " ".join(_read(SRC / "skf-verify-stack" / "scripts" / "skf-previous-report.py").split())
    assert "which passes the feasibility-report check report.md §1 runs before it publishes a report" in helper
    section = _section("Verify Stack (VS)")
    for token in ("writes the `-latest.md` copy only once the finished report passes its check",
                  "a halted run leaves the previous `-latest` in place",
                  "the newest earlier report that finished and passed that check"):
        assert token in section, token


def test_refine_architecture_documents_the_promotion_and_its_exit_codes():
    """#599, #600: the draft promoted on [C], the RA markers, the dismissed record, and the exit-3 and -4 causes."""
    reasons = _schema("skf-refine-architecture-result-envelope.v1.json")["properties"]["halt_reason"]["enum"]
    for reason in ("resolution-failure", "preservation-failed", "recovery-failed"):
        assert reason in reasons, reason
    preservation = _read(RA_REFS.parent / "scripts" / "skf-check-preservation.py")
    assert "<!-- RA:BEGIN" in preservation and "<!-- RA:END -->" in preservation
    section = _ra_section()
    assert "`[R]` walks through each refinement with its evidence, before you approve with `[C]`" in section
    output = _paragraph(section, "**Output:**")
    for token in ("only when you approve the review with `[C]`",
                  "`refined-architecture-<project>-<YYYYMMDD-HHmmss>.md`", "`<!-- RA:BEGIN ... -->`",
                  "`<!-- RA:END -->`", "text you moved outside the markers stays", "`.ra-dismissed-<project>.json`",
                  "`out_of_scope_skills`", "does not repeat the summary's count table",
                  "a headless run reports the counts in its result line"):
        assert token in output, token
    [line] = [line for line in _read(WORKFLOWS).splitlines()
              if line.startswith("- **`/skf-refine-architecture` (RA)**")]
    for token in ("`scripts/skf-check-preservation.py` cannot start",
                  "lack one of their six tables or break a tier rule (phase `init:rules`)", "phase `init:inventory`",
                  "phase `init:feasibility-validator`", "phase `gap-analysis:comention`", "`preservation-failed`",
                  "a record of the draft's build or promotion is missing",
                  "src/skf-refine-architecture/references/exit-codes.md"):
        assert token in line, token
    for gone in ("`## Refinement Summary`", "SKILL.md) §"):
        assert gone not in line, gone


def test_rename_docs_name_the_run_lock_and_the_interrupted_rename():
    """#588: the RS line names the run lock and its remedy; Safety names the recovery and the official flag."""
    contract = _read(SRC / "skf-rename-skill" / "references" / "invocation-contract.md")
    for token in ("`{forge_data_folder}/.skf-rename-{old_name}.lock`", "60 minutes after it was taken or renewed",
                  "`--acknowledge-official`", "A supplied name answers its question in either mode"):
        assert token in contract, token
    select = _read(SRC / "skf-rename-skill" / "references" / "select.md")
    assert "interrupted_after_rekey" in select and "guarded-delete" in select
    lock = _read(SRC / "shared" / "scripts" / "skf-run-lock.py")
    assert "if no run is active, delete {path}" in lock and "or wait until {stale_at}" in lock
    assert "step 2 §1 (this run's lock went stale while it waited at a step 1 gate) → `halted-for-concurrent-run`" \
        in _read(SRC / "skf-rename-skill" / "references" / "exit-codes.md")
    [line] = [line for line in _read(WORKFLOWS).splitlines() if line.startswith("- **`/skf-rename-skill` (RS)**")]
    for token in ("`halted-for-concurrent-run` while another rename of the same skill holds its run lock",
                  "or when this run's own lock went stale while it waited at a prompt",
                  "When this run's own lock went stale at a prompt, nothing was changed: run the rename again.",
                  "`.skf-rename-<name>.lock` in `forge_data_folder`", "60 minutes after it was taken or renewed",
                  "delete the lock file the message names, or wait until the time it gives",
                  "src/skf-rename-skill/references/invocation-contract.md) § \"Result Contract (Headless)\""):
        assert token in line, token
    assert "src/skf-rename-skill/SKILL.md" not in line
    safety = _paragraph(_section("Rename Skill (RS)"), "**Safety:**")
    for token in ("stops with `source-authority-blocked` unless you pass `--acknowledge-official`",
                  "Names given with the invocation", "ask only for a name that is missing or invalid",
                  "`name-collision` (exit `5`)", "lists the old folders left on disk",
                  "`skf-skill-inventory.py guarded-delete`", "`@Ferris EX` rebuilds the context files",
                  "Rename does not rename a copy `npx skills add` installed in the IDE skill folder a context "
                  "file's managed section points at",
                  "the report names each one it finds with its reinstall step, and the run's warnings, in the "
                  "envelope and the result file, carry `installed-copy-not-renamed` for each.",
                  "No check runs when `snippet_skill_root_override` is set."):
        assert token in safety, token
    # The warning the docs name is the one step 2 records.
    assert '--warning "installed-copy-not-renamed: {path}"' in _read(
        SRC / "skf-rename-skill" / "references" / "execute.md")


def test_export_docs_name_the_context_file_flag_and_the_snippet_root():
    """#594, #600: --context-file and the snippet-root rules are the invocation contract's."""
    contract = _read(SRC / "skf-export-skill" / "references" / "invocation-contract.md")
    for token in ("`--context-file <file>`", "any other value halts with exit code 3, `resolution-failure`",
                  "headless: [I], the IDE skill folder", "when only that folder holds the skills"):
        assert token in contract, token
    section = _section("Export Skill (EX)")
    [flag] = [line for line in section.splitlines() if line.startswith("- `--context-file <file>`")]
    assert "`CLAUDE.md`, `AGENTS.md` or `.cursorrules`" in flag and "exit `3` (`resolution-failure`)" in flag
    good = _paragraph(section, "**Good to know:**")
    for token in ("`load-skill.snippet-root-layout`",
                  "keeps the earlier root for that run when only that folder holds the skills",
                  "`snippet_skill_root_override: skills/`", "before its first prompt"):
        assert token in good, token


def test_settings_list_names_only_settings_that_take_effect():
    """#596: each setting the list names is a key of that workflow's customize.toml, and a removed one says so."""
    settings = _slice(_read(WORKFLOWS), "Useful settings in specific workflows:", "\n---\n")
    for skill, keys in SETTINGS_TAKING_EFFECT.items():
        bundled = _settings(skill)
        for key in keys:
            assert key in bundled and re.search(rf"`{key}[` ]", settings), (skill, key)
    for skill, keys in SETTINGS_REMOVED.items():
        bundled = _settings(skill)
        for key in keys:
            assert key not in bundled, (skill, key)
    assert "`default_mode`" not in _read(WORKFLOWS)
    for token in ("`scoring_rules_path` and `output_formats_path` are gone",
                  "Verify Stack's report always lands in `forge_data_folder`",
                  "any non-empty value blocks a headless purge (exit `6`, `headless-purge-forbidden`)",
                  'An override file that fails to parse, the team one or your personal one, stops the '
                  'customization script: the run warns as above and ignores both override files, which leaves '
                  'the guard off, so write the value quoted, such as `"true"`.',
                  'Write it as two lines, `[workflow]` then `forbid_purge_in_headless = "true"`.',
                  "`--acknowledge-official`", "the TOML boolean `true`", "the six house-style tables"):
        assert token in settings, token
    rules = _headings(RA_REFS / "refinement-rules.md")
    for table in RA_RULES_TABLES:
        assert table in rules and table in settings, table


# --------------------------------------------------------------------------
# Customizing a workflow and chaining codes: the resolver warning, the `!`
# facts drop, the on_complete call forms and the chain's first input
# --------------------------------------------------------------------------

DEFAULT_FACT = "file:{project-root}/**/project-context.md"
RESOLVER_WARNING = "`[activation/warn] customization_resolver_unavailable: <reason>`"
# The workflows whose on_complete is not called with --result-path, and what their customize.toml says instead.
HOOK_FORMS = {
    "skf-campaign": "<on_complete> --report-path=",
    "skf-create-stack-skill": "Command invoked once a run finishes",
    "skf-setup": "An instruction the agent carries out",
    "skf-verify-stack": "Instruction executed when the workflow reaches its terminal stage",
}
CHAIN_HALT = "`<CODE> needs <input> before the pipeline can start: give it as <CODE>[<input>]`"
CHAIN_HALT_EXAMPLE = "`QS needs a target before the pipeline can start: give it as QS[<target>]`"


def _workflow_skills() -> list[str]:
    """Every workflow skill folder under src/, Ferris (an agent) left out."""
    return sorted(p.parent.name for p in SRC.glob("skf-*/SKILL.md") if p.parent.name != "skf-forger")


def _comment_above(text: str, key: str) -> str:
    """The `#` comment block above `key = ` in a TOML file, as one line of words."""
    lines = text.splitlines()
    [i] = [n for n, line in enumerate(lines) if line.startswith(f"{key} = ")]
    j = i - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    words = []
    while j >= 0 and lines[j].startswith("#"):
        words.append(lines[j].lstrip("#").strip())
        j -= 1
    return " ".join(word for word in reversed(words) if word)


def test_customizing_section_and_chain_docs_follow_the_activation():
    """#595, #596, #594: the resolver warning, the `!` facts drop, the hook call and a chain's first input.

    The resolver blocks and the customize.toml facts are pinned where they live; this checks the docs, the two
    exceptions they name (Campaign's decision log, interactive Export) and that each on_complete comment names
    the call the docs give. Ferris's chain ask is documented with the example and halt reason its stage-6c
    package fixes.
    """
    assert "in the decision log" in _read(SRC / "skf-campaign" / "SKILL.md")
    assert "an interactive run only prints it" in _read(SRC / "skf-export-skill" / "SKILL.md")
    doc = _read(WORKFLOWS)
    customizing = _slice(doc, "## Customizing a Workflow", "Settings every workflow has:")
    # The resolver reads the `[workflow]` table only, the first table of every bundled file.
    opening = _paragraph(customizing, "Every workflow ships a `customize.toml`")
    assert ("Start the file with a `[workflow]` line, as the bundled file does: a setting above it is ignored "
            "without a warning.") in opening
    for skill in _workflow_skills():
        tables = re.findall(r"^\[[^\]]+\]", _read(SRC / skill / "customize.toml"), flags=re.M)
        assert tables[:1] == ["[workflow]"], skill
    resolver = _paragraph(customizing, "These overrides are read by BMAD Method's customization script")
    for token in ("Every workflow, and Ferris, runs that script through `uv` when it starts", RESOLVER_WARNING,
                  "uses the bundled defaults, ignoring `_bmad/custom/`",
                  "adds a warning naming `customization_resolver_unavailable` and its reason to the run's warnings",
                  "Campaign logs it in its decision log", "an interactive Export Skill run only prints it",
                  "In a project with SKF alone, that script is missing",
                  "`customization_resolver_unavailable: not found`"):
        assert token in resolver, token
    forger = _paragraph(customizing, "Ferris reads `_bmad/custom/skf-forger.toml`")
    # Ferris resolves `--key agent`: his override opens with `[agent]`, not the `[workflow]` the opening names.
    assert "under an `[agent]` line, as his bundled file does (a `[workflow]` table there is ignored)" in forger
    tables = re.findall(r"^\[[^\]]+\]", _read(SRC / "skf-forger" / "customize.toml"), flags=re.M)
    assert tables[:1] == ["[agent]"], tables
    assert "--key agent" in _read(SRC / "skf-forger" / "SKILL.md")
    agent = tomllib.loads(_read(SRC / "skf-forger" / "customize.toml"))["agent"]
    arrays = sorted(key for key, value in agent.items() if isinstance(value, list))
    assert arrays == ["activation_steps_append", "activation_steps_prepend", "persistent_facts"], arrays
    for token in [f"`{key}`" for key in arrays] + ["`_bmad/custom/skf-forger.user.toml`",
                                                   "roster values stay as shipped", "he has no `on_complete`",
                                                   "the warning line opens his greeting"]:
        assert token in forger, token
    assert "on_complete" not in agent
    architecture = _read(ARCHITECTURE)
    [row] = [line for line in architecture.splitlines() if line.startswith("| `customize.toml`")]
    [loads] = [line for line in architecture.splitlines() if line.startswith("3. **Workflow loads**")]
    for text in (row, loads):
        for token in ("through `uv`", "`customization_resolver_unavailable`", "bundled settings",
                      "an interactive Export Skill run only prints it"):
            assert token in text, token
    assert "as Ferris does for his own settings when he starts" in loads

    settings = _slice(doc, "Settings every workflow has:", "Useful settings in specific workflows:")
    [facts] = [line for line in settings.splitlines() if line.startswith("- `persistent_facts`:")]
    assert _settings("skf-setup")["persistent_facts"] == []
    for token in ("Every workflow except Setup Forge loads any `project-context.md`",
                  "an entry that starts with `!` drops each earlier entry it names and loads nothing itself",
                  f'add `persistent_facts = ["!{DEFAULT_FACT}"]` under `[workflow]` in '
                  "`_bmad/custom/<skill-name>.toml`",
                  "Every workflow that loads the default honours such an entry", "Campaign's kickoff loader"):
        assert token in facts, token
    assert "Brief, Create, Update and Rename Skill" not in facts

    skills = _workflow_skills()
    assert len(skills) == 15, skills
    for skill in skills:
        hook = _comment_above(_read(SRC / skill / "customize.toml"), "on_complete")
        assert hook, skill
        if skill in HOOK_FORMS:
            assert HOOK_FORMS[skill] in hook and "--result-path=" not in hook, skill
        else:
            assert "--result-path=" in hook, skill
    quick = _comment_above(_read(QUICK / "customize.toml"), "on_complete")
    assert "<on_complete> --result-path=<skill package>/quick-skill-result-latest.json" in quick
    assert "skipped when the emitter wrote no result file, or not that -latest copy" in quick
    assert "skipped when the emitter wrote no result file" in _comment_above(
        _read(SRC / "skf-rename-skill" / "customize.toml"), "on_complete")
    [on_complete] = [line for line in settings.splitlines() if line.startswith("- `on_complete`:")]
    for token in ("Every workflow except Campaign, Stack Skill, Verify Stack and Setup Forge (Quick Skill included)",
                  "`--result-path=<result file>`", "the hook is skipped when the emitter wrote no result file",
                  "`--result-path=<skill package>/quick-skill-result-latest.json`",
                  "the skill package is that file's folder", "or did not write that `-latest` copy",
                  "Campaign passes `--report-path=<report>`", "Stack Skill runs the command with no argument",
                  "Setup Forge and Verify Stack carry it out as an instruction",
                  "A failing command never fails the workflow"):
        assert token in on_complete, token

    aliases = _paragraph(_read(AGENTS), "Ferris can run several workflows in one command.")
    for token in ("such as `QS[cocoindex] TS EX`", "every step runs in headless mode",
                  "When the first code has no target and its input is not among the arguments",
                  "runs the chain as `QS[<input>] TS EX`", "stops before any workflow runs", CHAIN_HALT,
                  CHAIN_HALT_EXAMPLE, "SF and SS take no input"):
        assert token in aliases, token
    assert "such as `QS TS EX`" not in aliases
    chain = _paragraph(_slice(doc, "### Pipeline Aliases", "### How It Works"), "An alias given without its argument")
    for token in ("A chain of codes does the same", "runs the chain as `QS[<input>] TS EX`", CHAIN_HALT,
                  CHAIN_HALT_EXAMPLE, "SF and SS take no input"):
        assert token in chain, token
    syntax = _slice(doc, "### Syntax", "### Pipeline Aliases")
    codes = re.findall(r"^\| `@Ferris ([A-Z]{2})(\[[^\]]+\])?", syntax, re.M)
    assert codes and all(bracket for _, bracket in codes), codes
    [arrows] = [line for line in _slice(doc, "### How It Works", "### Examples").splitlines()
                if line.startswith("- Codes can be separated by spaces or by arrows")]
    assert "`AN[https://github.com/honojs/hono] -> CS -> TS -> EX`" in arrows
    chained = _paragraph(architecture, "**Chained runs**")
    for token in ("(for example `QS[cocoindex] TS EX`)", "Ferris asks for it before the chain starts",
                  "a headless run halts before any workflow runs"):
        assert token in chained, token
    assert "`BS CS TS EX`" not in chained and "Only the first workflow's input" not in chained


PARSE_PIPELINE = SRC / "skf-forger" / "scripts" / "parse-pipeline.py"
CONTRACTS = SRC / "shared" / "references" / "pipeline-contracts.md"
CHAIN_TOKEN_RE = re.compile(r"^[A-Z]{2}(?:\[[^\]]*\])?$")


def _doc_chains(text: str) -> list[str]:
    """The chains of codes `text` shows in code spans, without `@Ferris ` and arrows."""
    chains = []
    for span in re.findall(r"`([^`]+)`", text):
        tokens = span.removeprefix("@Ferris ").replace("->", " ").split()
        if len(tokens) > 1 and all(CHAIN_TOKEN_RE.match(token) for token in tokens):
            chains.append(" ".join(tokens))
    return chains


def test_chain_docs_agree_with_the_parser():
    """#594: each chain the pipeline docs show runs as parse-pipeline.py parses it, and each first-input rule they
    state is the parser's: the ask and its halt reason, input only in brackets, SF passed over, BS through forge, RS
    and DS on their own, a taken bracket named, and a CS that never halts before it starts.
    """
    parser = _script(PARSE_PIPELINE)
    parse = parser.parse_pipeline
    doc = _read(WORKFLOWS)

    # Every example in a command table, or among the How It Works bullets, runs as given.
    for start, end in (("### Syntax", "### Pipeline Aliases"), ("### Examples", "## Headless Mode")):
        rows = re.findall(r"^\| `@Ferris ([^`]+)`", _slice(doc, start, end), re.M)
        assert rows, start
        for raw in rows:
            out = parse(raw)
            assert out["valid"] and out["first_input"] is None, (raw, out["unexpected_args"], out["first_input"])
    how = _slice(doc, "### How It Works", "### Examples")
    assert _doc_chains(how), how
    syntax = re.search(r"## Syntax\n.*?```\n(.*?)```", _read(CONTRACTS), re.S).group(1)
    examples = [line.split("  #")[0].strip() for line in syntax.splitlines() if line.strip()]
    assert len(examples) == 4 and all("  #" in line for line in syntax.splitlines() if line.strip()), syntax
    for raw in _doc_chains(how) + examples:
        out = parse(raw)
        assert out["valid"] and out["first_input"] is None, (raw, out["first_input"])

    # The chains the three paragraphs show: asked for an input, stopped on a taken bracket, or runnable as given.
    chain = _paragraph(_slice(doc, "### Pipeline Aliases", "### How It Works"), "An alias given without its argument")
    aliases = _paragraph(_read(AGENTS), "Ferris can run several workflows in one command.")
    chained = _paragraph(_read(ARCHITECTURE), "**Chained runs**")
    asked = {"QS TS EX": "QS[<target>] TS EX", "SF QS TS EX": "SF QS[<target>] TS EX",
             "BS CS TS EX": parser.FORGE_FORM}
    shown = set()
    for text in (chain, aliases, chained):
        for raw in _doc_chains(text):
            shown.add(raw)
            out = parse(raw)
            first = out["first_input"]
            assert out["valid"], raw
            if raw in asked:
                assert first["form"] == asked[raw] and first["halt_reason"], (raw, first)
            elif raw == "TS[min:80] EX":
                assert first["form"] is None and "its bracket already holds min:80" in first["halt_reason"], first
            else:
                assert first is None, (raw, first)
    assert {"QS TS EX", "SF QS TS EX", "BS CS TS EX", "TS[min:80] EX", "QS[cocoindex] TS EX"} <= shown, shown
    assert "`QS TS EX cognee`" in chain and parse("QS TS EX cognee")["unknown_codes"] == ["cognee"]

    # The rules they state, each decided by the parser.
    qs = parse("QS TS EX")["first_input"]
    assert f"`{qs['halt_reason']}`" == CHAIN_HALT_EXAMPLE
    assert parse("SS TS EX")["first_input"] is None
    targeted = parse("BS[https://github.com/x/y] CS TS EX")["first_input"]
    assert targeted["form"] == "forge https://github.com/x/y <skill-name>", targeted
    for raw in ("BS CS TS", "BS CS[cocoindex] TS EX", "BS[auto] CS TS EX", "RS[cocoindex] EX", "DS[cocoindex]",
                "QS[auto] TS EX", "AN[auto] CS TS EX", "AN[min:3] CS TS EX"):
        first = parse(raw)["first_input"]
        assert first["form"] is None and first["halt_reason"], (raw, first)
    assert parse("QS[min:80] TS EX")["first_input"]["form"] == "QS[<target>] TS EX"  # min:N ignored off AN and TS
    for raw in ("CS TS EX", "CS[min:80] TS EX"):
        cs = parse(raw)["first_input"]
        assert cs["form"] == "CS[<skill-name>] TS EX" and cs["halt_reason"] is None, (raw, cs)
    assert parse("CS[auto] TS EX")["first_input"] is None
    for raw in ("BS CS[min:5] TS EX", "BS CS TS EX[min:3]"):  # a min:N ignored off AN and TS keeps the forge ask
        assert parse(raw)["first_input"]["form"] == parser.FORGE_FORM, raw
    for text in (chain, aliases, chained):
        for token in ("SF", "asks for its skill name", "unless its bracket holds `auto`", "led by `CS` never halts",
                      "Create Skill", f"only as `{parser.FORGE_FORM}`", "the `forge` alias's codes", "`RS`", "`DS`",
                      "led by any other code but `CS` whose bracket already holds `auto`, or by AN or TS with a `min:N` in "
                      "its bracket"):
            assert token in text, token
    for text in (chain, aliases):
        for token in ("A chain of codes takes that input only in brackets", "Ferris looks past a leading SF",
                      "a chain that starts with SS runs as given", "with a halt reason that, for an input a bracket "
                      "gives, reads", "with at most a target in BS's bracket and no other bracket",
                      "A `min:N` on another code is ignored, so Ferris asks for that code's input"):
            assert token in text, token
    assert "so a chain that starts with either runs as given" not in chain
    assert "past a leading `SF`" in chained

    # An alias's missing argument halts; a target's form does not.
    assert parse("forge cognee")["missing_args"] == ["skill_name"] and parse("forge cognee cognee")["valid"]
    [halt] = [line for line in how.splitlines() if line.startswith("- **Safe halt on a missing input**")]
    for token in ("`forge cognee`, which gives a target but no skill name", "except a chain led by `CS`",
                  "`forge cognee cognee` starts Brief Skill"):
        assert token in halt, token
    assert "neither a URL nor a path), the pipeline halts" not in doc

    # The contract Ferris loads states the same limits.
    bracket = _slice(_read(CONTRACTS), "Only AN (a unit count) and TS (a test threshold) take `min:N`.", "\n")
    assert f"a chain led by BS gets its target and skill name only as `{parser.FORGE_FORM}`" in bracket
    assert "(CS, QS, US, etc.)" in bracket and set(parser.ON_THEIR_OWN) == {"RS", "DS"}


def test_docs_follow_the_tier_miss_the_audit_baseline_stop_and_the_drop_warnings():
    """#594, #599: a required-tier miss fails fast, an audit stops at its baseline only on doubt, a drop warns.

    Each docs line is checked against the contract it describes: setup's invocation contract, audit's init.md
    section 7 and exit-code table, and drop's `warnings` field rule.
    """
    contract = _read(SRC / "skf-setup" / "references" / "invocation-contract.md")
    for token in ("builds no ccc index that is due", "runs no registry hygiene, so it removes no QMD collection, "
                  "even under `--orphan-action=remove`"):
        assert token in contract, token
    doc = _read(WORKFLOWS)
    require = next(line for line in _section("Setup Forge (SF)").splitlines() if line.startswith("- `--require-tier="))
    for token in ("On a miss the workflow halts without running the health check. A miss also skips a due ccc index "
                  "build", "and the registry cleanup", "removes no QMD collection, even under `--orphan-action=remove`",
                  "Pipelines branch on the envelope's `status` field"):
        assert token in require, token

    init = _read(SRC / "skf-audit-skill" / "references" / "init.md")
    for token in ("When neither doubt below holds, go straight on", "`{provenance_age_days}` (§4) is above 90",
                  "**[X]** HALTs with **exit 6**, `halt_reason: \"user-cancelled\"`", "holds the baseline only",
                  "If `{headless_mode}`, continue with [C]"):
        assert token in init, token
    [six] = [row for row in _read(SRC / "skf-audit-skill" / "references" / "headless-contract.md").splitlines()
             if row.startswith("| 6 ")]
    assert "baseline confirm gate `[X]`" in six
    baseline = _paragraph(_section("Audit Skill (AS)"), "**Baseline:**")
    for token in ("An interactive audit shows its baseline summary and analysis plan and goes straight on",
                  "below the tier the skill was compiled at", "the provenance map is more than 90 days old",
                  "`[C]` continues", "`[X]` stops the run with exit `6` (`user-cancelled`)",
                  "which then holds the baseline only", "A headless run continues"):
        assert token in baseline, token

    rule = _read(SRC / "skf-drop-skill" / "references" / "invocation-contract.md")
    [warnings] = [line for line in rule.splitlines() if line.startswith("- `warnings`:")]
    [line] = [line for line in doc.splitlines() if line.startswith("- **`/skf-drop-skill` (DS)**")]
    for name in ("context_rebuild_failed", "active_link_dangling", "delete_failed", "verification_failed",
                 "customization_resolver_unavailable"):
        assert f"`{name}: " in warnings and f"`{name}`" in line, name
    assert "A `success` drop can still carry `warnings` that name what needs a manual fix" in line
    assert line.index("`warnings`") < line.index("Exit codes in")
